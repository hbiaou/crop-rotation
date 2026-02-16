"""
rotation_engine.py — Core rotation algorithm for crop rotation planning.

This module implements:
- Category rotation: advancing each bed one step in the configured rotation sequence
- Smart crop assignment with 5-cycle lookback and distance-weighted scoring
- Distribution resolution: converting percentage targets to absolute bed counts
- Family and species-level rotation penalties for disease management

Algorithm details:
- Rotation sequence wraps: last category → first category
- Same-category repeat is forbidden
- Penalty tables for rotation (same crop > same species > same family):
    - Same crop: 1 cycle ago = -50, 2 = -30, 3 = -15, 4 = -5, 5 = -1
    - Same species: 1 cycle ago = -35, 2 = -20, 3 = -10, 4 = -3
    - Same family: 1 cycle ago = -20, 2 = -10, 3 = -5
- Diversity bonus: +2 per past cycle with a different crop in same category
"""

from collections import defaultdict
from database import (
    get_db, get_setting
)
from utils.backup import backup_db


# Penalty table: cycles ago → penalty (same exact crop)
PENALTY_TABLE = {1: -50, 2: -30, 3: -15, 4: -5, 5: -1}

# Species-level penalty: same species but different variety (e.g., hot pepper after sweet pepper)
SPECIES_PENALTY_TABLE = {1: -35, 2: -20, 3: -10, 4: -3}

# Family-level penalty: same family (e.g., tomato after pepper - both Solanaceae)
FAMILY_PENALTY_TABLE = {1: -20, 2: -10, 3: -5}

DIVERSITY_BONUS = 2
LOOKBACK_CYCLES = 5


def compute_next_cycle_id(prev_cycle, cycles_per_year):
    """
    Compute the next cycle identifier from the previous one.

    Handles 4 formats:
    - 1 cycle/year:  "2026" → "2027"
    - 2 cycles/year: "2026A" → "2026B", "2026B" → "2027A"
    - 3 cycles/year: "2026A" → "2026B" → "2026C" → "2027A"
    - 4 cycles/year: "2026Q1" → "2026Q2" → ... → "2026Q4" → "2027Q1"

    Args:
        prev_cycle: Previous cycle string (e.g., "2026A")
        cycles_per_year: Number of cycles per year (1-4)

    Returns:
        Next cycle string.
    """
    cycles_per_year = int(cycles_per_year)

    if cycles_per_year == 1:
        # Format: "YYYY"
        year = int(prev_cycle[:4])
        return str(year + 1)

    elif cycles_per_year == 2:
        # Format: "YYYYA" / "YYYYB"
        year = int(prev_cycle[:4])
        suffix = prev_cycle[4:]
        if suffix == 'A':
            return f"{year}B"
        else:
            return f"{year + 1}A"

    elif cycles_per_year == 3:
        # Format: "YYYYA" / "YYYYB" / "YYYYC"
        year = int(prev_cycle[:4])
        suffix = prev_cycle[4:]
        if suffix == 'A':
            return f"{year}B"
        elif suffix == 'B':
            return f"{year}C"
        else:
            return f"{year + 1}A"

    elif cycles_per_year == 4:
        # Format: "YYYYQ1" ... "YYYYQ4"
        year = int(prev_cycle[:4])
        quarter = int(prev_cycle[5:])  # after "Q"
        if quarter < 4:
            return f"{year}Q{quarter + 1}"
        else:
            return f"{year + 1}Q1"

    else:
        raise ValueError(f"Unsupported cycles_per_year: {cycles_per_year}")


def generate_next_cycle(garden_id):
    """
    Generate the next cycle for a garden by rotating categories.

    Steps:
    1. Auto-backup before any changes
    2. Read latest cycle's cycle_plans for this garden
    3. For each active sub-bed: determine effective category (actual if set, else planned)
    4. Look up rotation_sequence for the NEXT category
    5. Compute new cycle identifier
    6. Insert new cycle_plans with planned_category set
    7. Skip reserve sub-beds entirely
    8. Update settings.current_cycle

    Args:
        garden_id: ID of the garden to generate for.

    Returns:
        (new_cycle_id, None) on success, or (None, error_message) on failure.
    """
    # Step 1: Auto-backup
    backup_db('pre_generate')

    # Step 2: Read latest cycle
    conn = get_db()
    try:
        latest_cycle_row = conn.execute(
            "SELECT DISTINCT cycle FROM cycle_plans WHERE garden_id = ? ORDER BY cycle DESC LIMIT 1",
            (garden_id,)
        ).fetchone()

        if not latest_cycle_row:
            return None, "Aucun cycle précédent trouvé. Veuillez d'abord effectuer le démarrage."

        prev_cycle = latest_cycle_row['cycle']

        # Read previous cycle plans (via view for crop names)
        prev_plans = conn.execute(
            """SELECT cp.*, sb.bed_number, sb.sub_bed_position, sb.is_reserve
               FROM cycle_plans cp
               JOIN sub_beds sb ON cp.sub_bed_id = sb.id
               WHERE cp.garden_id = ? AND cp.cycle = ?
               ORDER BY sb.bed_number, sb.sub_bed_position""",
            (garden_id, prev_cycle)
        ).fetchall()

        if not prev_plans:
            return None, "Le cycle précédent ne contient pas de données."

        # Step 3 & 4: Build rotation map
        rotation_seq = conn.execute(
            "SELECT * FROM rotation_sequence ORDER BY position"
        ).fetchall()

        if not rotation_seq:
            return None, "La séquence de rotation n'est pas configurée."

        # Build next-category lookup: category → next category
        categories = [r['category'] for r in rotation_seq]
        next_category_map = {}
        for i, cat in enumerate(categories):
            next_cat = categories[(i + 1) % len(categories)]
            next_category_map[cat] = next_cat

        # Step 5: Compute new cycle ID
        cycles_per_year = get_setting('cycles_per_year', '2')
        new_cycle = compute_next_cycle_id(prev_cycle, cycles_per_year)

        # Check if new cycle already exists
        existing = conn.execute(
            "SELECT COUNT(*) FROM cycle_plans WHERE garden_id = ? AND cycle = ?",
            (garden_id, new_cycle)
        ).fetchone()[0]
        if existing > 0:
            return None, f"Le cycle {new_cycle} existe déjà pour ce jardin."

        # Step 6: Create new cycle_plans
        new_records = []
        for plan in prev_plans:
            # Step 7: Skip reserve sub-beds
            if plan['is_reserve']:
                continue

            # Effective category: actual if set, else planned
            effective_cat = plan['actual_category'] or plan['planned_category']

            if effective_cat and effective_cat in next_category_map:
                next_cat = next_category_map[effective_cat]
            else:
                # Fallback: use first category if unknown
                next_cat = categories[0] if categories else None

            new_records.append((
                plan['sub_bed_id'],
                garden_id,
                new_cycle,
                next_cat,     # planned_category
                None,         # planned_crop_id (filled by distribution)
                None,         # actual_category
                None,         # actual_crop_id
                0,            # is_override
            ))

        # Bulk insert
        conn.executemany(
            """INSERT INTO cycle_plans
               (sub_bed_id, garden_id, cycle, planned_category, planned_crop_id,
                actual_category, actual_crop_id, is_override)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            new_records
        )

        # Step 8: Update current_cycle setting
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('current_cycle', ?)",
            (new_cycle,)
        )

        conn.commit()
        return new_cycle, None

    except Exception as e:
        conn.rollback()
        return None, f"Erreur lors de la génération : {str(e)}"
    finally:
        conn.close()


def resolve_distribution(percentages, total_beds):
    """
    Convert percentage targets to absolute bed counts.

    Uses floor rounding and adjusts the last crop to make the sum exact.

    Args:
        percentages: list of (crop_id, percentage) tuples, ordered as in defaults
        total_beds: total number of beds in this category

    Returns:
        list of (crop_id, bed_count) tuples
    """
    import math

    if not percentages or total_beds == 0:
        return [(cid, 0) for cid, _ in percentages]

    # Calculate raw counts using floor
    result = []
    allocated = 0
    for crop_id, pct in percentages:
        count = math.floor(pct * total_beds / 100.0)
        result.append([crop_id, count])
        allocated += count

    # Distribute remainder to the crops with largest fractional parts
    remainder = total_beds - allocated
    if remainder > 0:
        # Calculate fractional parts
        fractions = []
        for i, (crop_id, pct) in enumerate(percentages):
            raw = pct * total_beds / 100.0
            frac = raw - math.floor(raw)
            fractions.append((frac, i))
        fractions.sort(reverse=True)

        for j in range(min(remainder, len(fractions))):
            idx = fractions[j][1]
            result[idx][1] += 1

    return [(crop_id, count) for crop_id, count in result]


def assign_crops(garden_id, cycle):
    """
    Smart crop assignment using 5-cycle lookback scoring with family/species penalties.

    Algorithm per FEATURES_SPEC.md section F4:
    - For each category: get beds in category, crops with resolved target counts
    - For each crop (sorted by target count desc):
      - Score each unassigned bed using penalty tables + diversity bonus
      - Penalties apply at three levels: same crop > same species > same family
      - Assign best-scoring beds to this crop
    - Tie-break: bed ID ascending (deterministic)
    - Update planned_crop_id in cycle_plans

    Args:
        garden_id: Garden ID
        cycle: Cycle string to assign crops for

    Returns:
        (True, None) on success, or (False, error_message) on failure.
    """
    conn = get_db()
    try:
        # Load rotation sequence for category ordering
        rotation_seq = conn.execute(
            "SELECT category FROM rotation_sequence ORDER BY position"
        ).fetchall()
        categories = [r['category'] for r in rotation_seq]

        # Load distribution profiles for this garden+cycle
        profiles = conn.execute(
            """SELECT dp.crop_id, dp.target_percentage, c.category, c.crop_name
               FROM distribution_profiles dp
               JOIN crops c ON dp.crop_id = c.id
               WHERE dp.garden_id = ? AND dp.cycle = ?
               ORDER BY c.category, dp.target_percentage DESC""",
            (garden_id, cycle)
        ).fetchall()

        # Load cycle_plans for this cycle (the beds we need to assign crops to)
        plans = conn.execute(
            """SELECT cp.id as plan_id, cp.sub_bed_id, cp.planned_category,
                      sb.bed_number, sb.sub_bed_position
               FROM cycle_plans cp
               JOIN sub_beds sb ON cp.sub_bed_id = sb.id
               WHERE cp.garden_id = ? AND cp.cycle = ? AND sb.is_reserve = 0
               ORDER BY sb.bed_number, sb.sub_bed_position""",
            (garden_id, cycle)
        ).fetchall()

        # Get all distinct cycles for this garden, ordered desc, for history lookback
        all_cycles = conn.execute(
            "SELECT DISTINCT cycle FROM cycle_plans WHERE garden_id = ? ORDER BY cycle DESC",
            (garden_id,)
        ).fetchall()
        all_cycle_list = [r['cycle'] for r in all_cycles]

        # Find the index of the current cycle, lookback from the PREVIOUS cycles
        if cycle in all_cycle_list:
            cycle_idx = all_cycle_list.index(cycle)
            past_cycles = all_cycle_list[cycle_idx + 1:cycle_idx + 1 + LOOKBACK_CYCLES]
        else:
            past_cycles = all_cycle_list[:LOOKBACK_CYCLES]

        # Load crop family and species information for rotation penalties
        # Join crops with plants table to get family and base_species
        crop_taxonomy = conn.execute("""
            SELECT c.id as crop_id, c.family as crop_family,
                   p.family as plant_family, p.base_species_norm
            FROM crops c
            LEFT JOIN plants p ON c.plant_id = p.id
        """).fetchall()

        # Build lookup dictionaries for family and species
        crop_to_family = {}
        crop_to_species = {}
        crops_by_family = defaultdict(set)
        crops_by_species = defaultdict(set)

        for row in crop_taxonomy:
            crop_id = row['crop_id']
            # Prefer plant family over crop family if available
            family = row['plant_family'] or row['crop_family'] or ''
            species = row['base_species_norm'] or ''

            crop_to_family[crop_id] = family
            crop_to_species[crop_id] = species

            if family:
                crops_by_family[family].add(crop_id)
            if species:
                crops_by_species[species].add(crop_id)

        # Process each category
        for category in categories:
            # Get beds in this category for the current cycle
            cat_beds = [p for p in plans if p['planned_category'] == category]
            if not cat_beds:
                continue

            # CRITICAL FIX: Reset all beds in this category to have NO planned_crop_id first.
            # This ensures that that if a crop's target count is reduced to 0, it doesn't keep old assignments.
            for bed in cat_beds:
                conn.execute(
                    "UPDATE cycle_plans SET planned_crop_id = NULL WHERE id = ?",
                    (bed['plan_id'],)
                )

            total_beds_in_cat = len(cat_beds)

            # Get crops and their target percentages for this category
            cat_profiles = [p for p in profiles if p['category'] == category]
            if not cat_profiles:
                continue

            # Resolve percentages to bed counts
            pct_list = [(p['crop_id'], p['target_percentage']) for p in cat_profiles]
            resolved = resolve_distribution(pct_list, total_beds_in_cat)

            # Build crop info with resolved counts, sorted by count desc
            crop_targets = []
            for (crop_id, bed_count), profile in zip(resolved, cat_profiles):
                crop_targets.append({
                    'crop_id': crop_id,
                    'crop_name': profile['crop_name'],
                    'target_count': bed_count,
                })
            crop_targets.sort(key=lambda x: x['target_count'], reverse=True)

            # Load history for beds in this category
            # For each past cycle, get what crop was in each sub_bed
            bed_history = {}  # sub_bed_id → list of (cycles_ago, crop_id, category)
            for i, past_cycle in enumerate(past_cycles):
                cycles_ago = i + 1
                history_rows = conn.execute(
                    """SELECT sub_bed_id,
                              COALESCE(actual_crop_id, planned_crop_id) as crop_id,
                              COALESCE(actual_category, planned_category) as category
                       FROM cycle_plans
                       WHERE garden_id = ? AND cycle = ?""",
                    (garden_id, past_cycle)
                ).fetchall()
                for row in history_rows:
                    sid = row['sub_bed_id']
                    if sid not in bed_history:
                        bed_history[sid] = []
                    bed_history[sid].append({
                        'cycles_ago': cycles_ago,
                        'crop_id': row['crop_id'],
                        'category': row['category'],
                    })

            # Assign crops to beds
            
            assigned_bed_ids = set()

            for crop_info in crop_targets:
                crop_id = crop_info['crop_id']
                target_count = crop_info['target_count']

                if target_count <= 0:
                    continue

                # Get family and species for current crop
                current_family = crop_to_family.get(crop_id, '')
                current_species = crop_to_species.get(crop_id, '')

                # Get sets of crops in same family/species (excluding current crop)
                same_family_crops = crops_by_family.get(current_family, set()) - {crop_id} if current_family else set()
                same_species_crops = crops_by_species.get(current_species, set()) - {crop_id} if current_species else set()

                # Score each unassigned bed
                scored_beds = []
                for bed in cat_beds:
                    sid = bed['sub_bed_id']
                    if sid in assigned_bed_ids:
                        continue

                    history = bed_history.get(sid, [])
                    # Filter history to entries where the bed was in this same category
                    cat_history = [h for h in history if h['category'] == category]

                    if not cat_history:
                        score = 0  # Neutral for beds with no history in this category
                    else:
                        score = 0
                        for h in cat_history:
                            past_crop_id = h['crop_id']
                            cycles_ago = h['cycles_ago']

                            if past_crop_id == crop_id:
                                # Same exact crop: heaviest penalty
                                score += PENALTY_TABLE.get(cycles_ago, 0)
                            elif past_crop_id in same_species_crops:
                                # Same species, different variety (e.g., hot pepper after sweet pepper)
                                score += SPECIES_PENALTY_TABLE.get(cycles_ago, 0)
                            elif past_crop_id in same_family_crops:
                                # Same family (e.g., tomato after pepper - both Solanaceae)
                                score += FAMILY_PENALTY_TABLE.get(cycles_ago, 0)
                            else:
                                # Different family: diversity bonus
                                score += DIVERSITY_BONUS

                    scored_beds.append((score, sid, bed['plan_id']))

                # Sort by score descending, then by sub_bed_id ascending (tie-break)
                scored_beds.sort(key=lambda x: (-x[0], x[1]))

                # Assign the top-scoring beds
                for j in range(min(target_count, len(scored_beds))):
                    _, sid, plan_id = scored_beds[j]
                    conn.execute(
                        "UPDATE cycle_plans SET planned_crop_id = ? WHERE id = ?",
                        (crop_id, plan_id)
                    )
                    assigned_bed_ids.add(sid)

        conn.commit()
        return True, None

    except Exception as e:
        conn.rollback()
        return False, f"Erreur lors de l'affectation des cultures : {str(e)}"
    finally:
        conn.close()
