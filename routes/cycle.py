"""
routes/cycle.py — Cycle generation, bootstrap, undo, and override routes.

Provides:
- GET  /bootstrap/<garden_id>         — Bootstrap form (initial data entry)
- POST /bootstrap/<garden_id>         — Save bootstrap data
- GET  /api/crops/<category>          — JSON: crops for a category
- POST /bootstrap/<garden_id>/auto-distribute — JSON: auto-distribution
- POST /cycle/generate                — Generate next cycle (future session)
- POST /cycle/undo                    — Undo last generated cycle (future session)
- POST /cycle/override                — Record an override (future session)

See FEATURES_SPEC.md sections F1, F2, F6, F8.
"""

import json
import os
import re
import random
from datetime import datetime
from collections import OrderedDict

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from database import (
    get_garden, get_sub_beds, get_crops, get_setting, get_rotation_sequence,
    get_cycle_plans_for_garden_cycle, create_cycle_plans_batch, update_setting,
    get_categories, get_garden_stats, get_latest_cycle,
    delete_cycle_plans, delete_distribution_profiles
)

cycle_bp = Blueprint('cycle', __name__)


# ========================================
# Helpers
# ========================================

def compute_current_cycle():
    """Compute the current cycle identifier based on date and cycles_per_year setting.

    Rules from FEATURES_SPEC.md section 2.3:
    - 1/year: "YYYY"
    - 2/year: Jan-Jun = "YYYYA", Jul-Dec = "YYYYB"
    - 3/year: Jan-Apr = "YYYYA", May-Aug = "YYYYB", Sep-Dec = "YYYYC"
    - 4/year: Q1-Q4 = "YYYYQ1" ... "YYYYQ4"
    """
    now = datetime.now()
    year = now.year
    month = now.month
    cycles_per_year = int(get_setting('cycles_per_year', '2'))

    if cycles_per_year == 1:
        return str(year)
    elif cycles_per_year == 2:
        suffix = 'A' if month <= 6 else 'B'
        return f"{year}{suffix}"
    elif cycles_per_year == 3:
        if month <= 4:
            suffix = 'A'
        elif month <= 8:
            suffix = 'B'
        else:
            suffix = 'C'
        return f"{year}{suffix}"
    elif cycles_per_year == 4:
        quarter = (month - 1) // 3 + 1
        return f"{year}Q{quarter}"
    else:
        return f"{year}A"




def _compute_auto_distribution(garden_id):
    """Compute automatic category+crop distribution for a garden's active sub-beds.

    Algorithm (bed-first with bed-to-bed category cycling):
    1. Traverse beds in order: P1 → P2 → ... → Pn
    2. For each bed, fill sub-beds S1 → S2 → S3 → S4 in order
    3. Each bed has a PRIMARY category that advances through the rotation sequence
    4. Quotas determine how many sub-beds each category/crop gets
    5. Spillover mid-bed when quota exhausted; no consecutive bed-starts repeat category/crop
       unless forced by quota boundary conditions

    Returns dict: {sub_bed_id: {'category': str, 'crop_id': int|None}}
    """
    from database import get_garden
    garden = get_garden(garden_id)
    if not garden:
        return {}

    active_beds = get_sub_beds(garden_id, active_only=True)
    rotation_seq = get_rotation_sequence()
    categories = [r['category'] for r in rotation_seq]
    all_crops = get_crops()

    if not categories or not active_beds:
        return {}

    # Group crops by category
    crops_by_cat = {}
    for crop in all_crops:
        cat = crop['category']
        if cat not in crops_by_cat:
            crops_by_cat[cat] = []
        crops_by_cat[cat].append({'id': crop['id'], 'crop_name': crop['crop_name']})

    # Load distribution defaults (garden-specific or equal-split fallback)
    from routes.distribution import _load_default_distribution
    garden_defaults = _load_default_distribution(garden_id)

    total_sub_beds = len(active_beds)
    num_categories = len(categories)

    # ── Step 1: Group sub-beds by bed_number (ordered) ──
    beds_grouped = OrderedDict()
    for sb in active_beds:
        bn = sb['bed_number']
        if bn not in beds_grouped:
            beds_grouped[bn] = []
        beds_grouped[bn].append(sb)

    # ── Step 2: Calculate category quotas (sub-bed counts) ──
    category_quota = {}
    base_count = total_sub_beds // num_categories
    cat_remainder = total_sub_beds % num_categories
    for i, cat in enumerate(categories):
        category_quota[cat] = base_count + (1 if i < cat_remainder else 0)

    # ── Step 3: Calculate crop quotas within each category ──
    crop_quota = {}  # {crop_id: remaining_quota}
    crop_order_by_cat = {}  # {category: [crop_id, ...]} in deterministic order

    for category in categories:
        cat_crops = crops_by_cat.get(category, [])
        cat_defaults = garden_defaults.get(category, {})
        cat_total = category_quota[category]

        if not cat_crops:
            crop_order_by_cat[category] = []
            continue

        # Calculate crop counts from percentages
        total_pct = sum(cat_defaults.get(c['crop_name'], 0) for c in cat_crops)
        crop_counts = []

        if total_pct > 0:
            remaining = cat_total
            for i, crop in enumerate(cat_crops):
                pct = cat_defaults.get(crop['crop_name'], 0)
                if pct == 0:
                    continue
                if i == len(cat_crops) - 1 or remaining <= 0:
                    count = remaining
                else:
                    count = max(0, round(pct / total_pct * cat_total))
                    count = min(count, remaining)
                remaining -= count
                crop_counts.append((crop['id'], count))
                crop_quota[crop['id']] = count

            # Remainder to last crop
            if remaining > 0 and crop_counts:
                last_id, last_count = crop_counts[-1]
                crop_quota[last_id] = last_count + remaining
                crop_counts[-1] = (last_id, last_count + remaining)
        else:
            # Equal distribution if no defaults
            per_crop = cat_total // len(cat_crops)
            leftover = cat_total % len(cat_crops)
            for i, crop in enumerate(cat_crops):
                extra = 1 if i < leftover else 0
                crop_counts.append((crop['id'], per_crop + extra))
                crop_quota[crop['id']] = per_crop + extra

        # Store deterministic crop order for this category
        crop_order_by_cat[category] = [cid for cid, _ in crop_counts if crop_quota.get(cid, 0) > 0]

    # ── Step 4: Bed-first allocation with bed-to-bed category cycling ──
    result = {}

    # Randomize starting category offset (only randomization allowed)
    start_offset = random.randint(0, num_categories - 1)

    # Track current position in category sequence (for primary category assignment)
    primary_cat_index = start_offset

    # Track the crop used to start the previous bed (for avoiding consecutive repeats)
    prev_bed_starter_crop = None

    # Track current category and crop pointers for spillover continuity
    current_cat_index = start_offset
    current_crop_index_by_cat = {cat: 0 for cat in categories}

    def get_next_category_with_quota(from_index):
        """Find next category with remaining quota, cycling through sequence."""
        for offset in range(num_categories):
            idx = (from_index + offset) % num_categories
            cat = categories[idx]
            if category_quota[cat] > 0:
                return idx, cat
        return None, None

    def get_next_crop_with_quota(category, start_idx=0, avoid_crop=None):
        """Find next crop with remaining quota in this category, optionally avoiding a specific crop."""
        crop_ids = crop_order_by_cat.get(category, [])
        if not crop_ids:
            return None

        # First pass: find a crop with quota that's not the avoided one
        for offset in range(len(crop_ids)):
            idx = (start_idx + offset) % len(crop_ids)
            crop_id = crop_ids[idx]
            if crop_quota.get(crop_id, 0) > 0 and crop_id != avoid_crop:
                return crop_id

        # Second pass: if we must use avoided crop (only option left)
        for offset in range(len(crop_ids)):
            idx = (start_idx + offset) % len(crop_ids)
            crop_id = crop_ids[idx]
            if crop_quota.get(crop_id, 0) > 0:
                return crop_id

        return None

    for bed_idx, bed_number in enumerate(beds_grouped):
        sub_beds_list = beds_grouped[bed_number]

        # Determine primary category for this bed (advances each bed)
        primary_cat_index, primary_cat = get_next_category_with_quota(primary_cat_index)
        if primary_cat is None:
            # No more quota anywhere - shouldn't happen with correct quotas
            break

        # For the first sub-bed (S1), set the primary category
        is_first_sub_bed = True

        for sb in sub_beds_list:
            sb_id = sb['id']

            if is_first_sub_bed:
                # Use the primary category for this bed's first sub-bed
                current_cat_index = primary_cat_index
                is_first_sub_bed = False

                # Advance primary category for next bed
                primary_cat_index = (primary_cat_index + 1) % num_categories

            # Find current category with quota
            cat_idx, category = get_next_category_with_quota(current_cat_index)
            if category is None:
                break  # No more quota

            # Find crop for this sub-bed
            crop_start_idx = current_crop_index_by_cat.get(category, 0)

            # For bed starters (S1), avoid repeating previous bed's starter crop if possible
            avoid_crop = prev_bed_starter_crop if sb['sub_bed_position'] == 1 else None
            crop_id = get_next_crop_with_quota(category, crop_start_idx, avoid_crop)

            # Assign to result
            result[sb_id] = {
                'category': category,
                'crop_id': crop_id
            }

            # Track bed starter crop
            if sb['sub_bed_position'] == 1:
                prev_bed_starter_crop = crop_id

            # Decrement quotas
            category_quota[category] -= 1
            if crop_id is not None:
                crop_quota[crop_id] -= 1

                # If this crop's quota is exhausted, advance crop index
                if crop_quota[crop_id] <= 0:
                    crop_ids = crop_order_by_cat.get(category, [])
                    if crop_ids:
                        current_idx = crop_ids.index(crop_id) if crop_id in crop_ids else 0
                        current_crop_index_by_cat[category] = (current_idx + 1) % len(crop_ids)

            # If category quota exhausted, spillover to next category
            if category_quota[category] <= 0:
                current_cat_index = (cat_idx + 1) % num_categories

    return result


# ========================================
# Bootstrap Routes
# ========================================

@cycle_bp.route('/bootstrap/<int:garden_id>')
def bootstrap(garden_id):
    """Display bootstrap form for initial data entry."""
    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", "error")
        return redirect(url_for('main.index'))

    # Get active sub-beds grouped by bed number
    active_beds = get_sub_beds(garden_id, active_only=True)

    # Group by bed_number
    beds_grouped = OrderedDict()
    for sb in active_beds:
        bed_num = sb['bed_number']
        if bed_num not in beds_grouped:
            beds_grouped[bed_num] = []
        beds_grouped[bed_num].append(sb)

    # Get all crops organized by category
    all_crops = get_crops()
    crops_by_category = {}
    for crop in all_crops:
        cat = crop['category']
        if cat not in crops_by_category:
            crops_by_category[cat] = []
        crops_by_category[cat].append({'id': crop['id'], 'name': crop['crop_name']})

    # Get categories from rotation sequence
    categories = get_categories()

    # Compute current cycle
    current_cycle = compute_current_cycle()

    # Check for existing data
    existing_plans = get_cycle_plans_for_garden_cycle(garden_id, current_cycle)
    has_existing = len(existing_plans) > 0

    # Stats
    stats = get_garden_stats(garden_id)

    return render_template(
        'bootstrap.html',
        garden=garden,
        beds_grouped=beds_grouped,
        crops_by_category=crops_by_category,
        categories=categories,
        current_cycle=current_cycle,
        has_existing=has_existing,
        total_sub_beds=len(active_beds),
        stats=stats,
        crops_json=json.dumps(crops_by_category),
    )


@cycle_bp.route('/bootstrap/<int:garden_id>', methods=['POST'])
def bootstrap_save(garden_id):
    """Save bootstrap data — create cycle_plans for all active sub-beds."""
    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", "error")
        return redirect(url_for('main.index'))

    # Get cycle from form or compute default
    cycle_input = request.form.get('cycle', '').strip().upper()
    current_cycle = ""
    
    if cycle_input:
        # Basic format validation: 4 digits + suffix
        if not re.match(r'^\d{4}[A-Za-z0-9]+$', cycle_input):
            flash("Format du cycle invalide. Utilisez 'YYYY' suivi d'un suffixe (ex: 2025B).", "error")
            return redirect(url_for('cycle.bootstrap', garden_id=garden_id))
        current_cycle = cycle_input
    else:
        current_cycle = compute_current_cycle()
    active_beds = get_sub_beds(garden_id, active_only=True)

    # Collect form data
    records = []
    errors = []

    for sb in active_beds:
        sb_id = sb['id']
        category = request.form.get(f'category_{sb_id}', '').strip()
        crop_id_str = request.form.get(f'crop_{sb_id}', '').strip()

        if not category:
            errors.append(sb_id)
            continue

        crop_id = int(crop_id_str) if crop_id_str else None

        records.append({
            'sub_bed_id': sb_id,
            'garden_id': garden_id,
            'cycle': current_cycle,
            'planned_category': category,
            'planned_crop_id': crop_id,
            'actual_category': category,
            'actual_crop_id': crop_id,
            'is_override': 0,
        })

    if errors:
        flash(f"Chaque sous-planche doit avoir une catégorie. {len(errors)} sous-planche(s) sans catégorie.", "error")
        return redirect(url_for('cycle.bootstrap', garden_id=garden_id))

    # Save all records
    success = create_cycle_plans_batch(records)
    if not success:
        flash("Erreur lors de l'enregistrement.", "error")
        return redirect(url_for('cycle.bootstrap', garden_id=garden_id))

    # Update current_cycle setting
    update_setting('current_cycle', current_cycle)

    flash(f"Démarrage enregistré avec succès pour le cycle {current_cycle}.", "success")
    return redirect(url_for('main.index'))


# ========================================
# API Endpoints
# ========================================

@cycle_bp.route('/api/crops/<category>')
def api_crops_by_category(category):
    """Return crops for a given category as JSON."""
    crops = get_crops(category)
    return jsonify([
        {'id': c['id'], 'crop_name': c['crop_name']}
        for c in crops
    ])


@cycle_bp.route('/bootstrap/<int:garden_id>/auto-distribute', methods=['POST'])
def api_auto_distribute(garden_id):
    """Compute and return auto-distribution as JSON."""
    result = _compute_auto_distribution(garden_id)
    # Convert keys to strings for JSON
    return jsonify({str(k): v for k, v in result.items()})


# ========================================
# Cycle Generation
# ========================================

def _auto_apply_distribution(garden_id, cycle):
    """Auto-apply default distribution percentages and assign crops for a new cycle.

    Steps:
    1. Load garden-specific defaults (or equal-split fallback)
    2. Resolve crop names → crop IDs
    3. Save as distribution_profiles for this garden+cycle
    4. Run assign_crops() to fill planned_crop_id
    """
    from routes.distribution import _load_default_distribution
    from database import save_distribution_profiles
    from rotation_engine import assign_crops

    # Load defaults for this specific garden
    defaults = _load_default_distribution(garden_id)
    if not defaults:
        return

    # Resolve crop names to IDs
    all_crops = get_crops()
    crop_name_to_id = {c['crop_name']: c['id'] for c in all_crops}

    profiles = []  # list of (crop_id, percentage)
    for category, crop_pcts in defaults.items():
        for crop_name, pct in crop_pcts.items():
            crop_id = crop_name_to_id.get(crop_name)
            if crop_id and pct > 0:
                profiles.append((crop_id, pct))

    if not profiles:
        return

    # Save distribution profiles for this cycle
    save_distribution_profiles(garden_id, cycle, profiles)

    # Run smart crop assignment
    assign_crops(garden_id, cycle)


@cycle_bp.route('/generate/<int:garden_id>', methods=['POST'])
def generate_cycle(garden_id):
    """Generate the next cycle for a garden.

    Steps:
    1. Save snapshot of current cycle's actuals
    2. Generate next cycle (category rotation)
    3. Auto-apply default distribution and assign crops
    4. Redirect to distribution page for the new cycle
    """
    from utils.snapshots import save_snapshot
    from rotation_engine import generate_next_cycle
    from database import get_latest_cycle

    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", "error")
        return redirect(url_for('main.index'))

    # Get current cycle
    current_cycle = get_latest_cycle(garden_id)
    if not current_cycle:
        flash("Aucun cycle existant. Veuillez d'abord effectuer le démarrage.", "warning")
        return redirect(url_for('cycle.bootstrap', garden_id=garden_id))

    # Step 1: Save snapshot of current cycle actuals
    snapshot_file = save_snapshot(garden_id, current_cycle)
    if snapshot_file:
        flash(f"Snapshot sauvegardé : {snapshot_file}", "info")

    # Step 2: Generate next cycle
    new_cycle, error = generate_next_cycle(garden_id)
    if error:
        flash(f"Erreur lors de la génération : {error}", "error")
        return redirect(url_for('main.index', garden_id=garden_id))

    # Step 3: Auto-apply default distribution and assign crops
    _auto_apply_distribution(garden_id, new_cycle)

    flash(f"Cycle {new_cycle} généré avec succès ! Ajustez la répartition ci-dessous.", "success")

    # Step 4: Redirect to distribution page
    return redirect(url_for('distribution.distribution_page',
                            garden_id=garden_id, cycle=new_cycle, new=1))


# ========================================
# Undo Generate (F8)
# ========================================

@cycle_bp.route('/undo/<int:garden_id>', methods=['POST'])
def undo_cycle(garden_id):
    """Undo the most recent cycle generation for a garden.

    Steps:
    1. Find the latest cycle for this garden.
    2. Delete cycle_plans and distribution_profiles for that cycle.
    3. Revert current_cycle setting to the previous cycle.
    4. Redirect to homepage.

    See FEATURES_SPEC.md section F8.
    """

    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", "error")
        return redirect(url_for('main.index'))

    # Get the latest cycle
    latest_cycle = get_latest_cycle(garden_id)
    if not latest_cycle:
        flash("Aucun cycle à annuler.", "warning")
        return redirect(url_for('main.index', garden_id=garden_id))

    # Delete cycle_plans for this cycle
    delete_cycle_plans(garden_id, latest_cycle)

    # Delete distribution_profiles for this cycle
    delete_distribution_profiles(garden_id, latest_cycle)

    # Determine the previous cycle (now-latest after deletion)
    prev_cycle = get_latest_cycle(garden_id)
    if prev_cycle:
        update_setting('current_cycle', prev_cycle)

    flash(f"Génération du cycle {latest_cycle} annulée avec succès.", "success")
    return redirect(url_for('main.index', garden_id=garden_id))


# ========================================
# Finalize Cycle (F12)
# ========================================

@cycle_bp.route('/finalize/<int:garden_id>/<cycle>', methods=['POST'])
def finalize_cycle(garden_id, cycle):
    """Finalize a cycle by saving a JSON snapshot of actual planting data.

    See FEATURES_SPEC.md section F12.
    """
    from utils.snapshots import save_snapshot

    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", "error")
        return redirect(url_for('main.index'))

    filename = save_snapshot(garden_id, cycle)
    if filename:
        flash(f"Cycle finalisé. Snapshot sauvegardé : {filename}", "success")
    else:
        flash("Erreur lors de la sauvegarde du snapshot.", "error")

    return redirect(url_for('main.map_view', garden_id=garden_id, cycle=cycle))
