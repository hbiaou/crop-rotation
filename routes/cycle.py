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
import math
from datetime import datetime
from collections import OrderedDict

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from database import (
    get_garden, get_sub_beds, get_crops, get_setting, get_rotation_sequence,
    get_cycle_plans_for_garden_cycle, create_cycle_plans_batch, update_setting,
    get_categories, get_garden_stats
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


def _load_distribution_defaults():
    """Load default distribution percentages from config/defaults.json."""
    defaults_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'defaults.json'
    )
    try:
        with open(defaults_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('distribution_defaults', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _compute_auto_distribution(garden_id):
    """Compute automatic category+crop distribution for a garden's active sub-beds.

    Algorithm:
    1. Get active sub-beds, rotation sequence, crops, and distribution defaults
    2. Divide sub-beds evenly across categories (remainder goes to first category)
    3. Within each category, distribute crops proportionally using default percentages
    4. Return dict: {sub_bed_id: {'category': str, 'crop_id': int|None}}
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

    # Load distribution defaults
    dist_defaults = _load_distribution_defaults()
    garden_code = garden['garden_code']
    garden_defaults = dist_defaults.get(garden_code, {})

    total_beds = len(active_beds)
    num_categories = len(categories)
    beds_per_category = total_beds // num_categories
    remainder = total_beds % num_categories

    # Assign categories to beds
    result = {}
    bed_index = 0

    for cat_idx, category in enumerate(categories):
        # First category gets remainder beds
        count = beds_per_category + (remainder if cat_idx == 0 else 0)
        cat_beds = active_beds[bed_index:bed_index + count]
        bed_index += count

        # Get crop distribution for this category
        cat_crops = crops_by_cat.get(category, [])
        cat_defaults = garden_defaults.get(category, {})

        if not cat_crops:
            # No crops for this category — assign category only
            for bed in cat_beds:
                result[bed['id']] = {'category': category, 'crop_id': None}
            continue

        # Calculate crop counts from percentages
        crop_assignments = []
        total_pct = sum(cat_defaults.get(c['crop_name'], 0) for c in cat_crops)

        if total_pct > 0:
            # Use percentage-based distribution
            remaining_beds = len(cat_beds)
            for i, crop in enumerate(cat_crops):
                pct = cat_defaults.get(crop['crop_name'], 0)
                if pct == 0:
                    continue
                if i == len(cat_crops) - 1 or remaining_beds <= 0:
                    # Last crop gets remainder
                    crop_count = remaining_beds
                else:
                    crop_count = max(0, round(pct / total_pct * len(cat_beds)))
                    crop_count = min(crop_count, remaining_beds)
                remaining_beds -= crop_count
                crop_assignments.append((crop, crop_count))

            # If any beds left unassigned, give to last crop
            if remaining_beds > 0 and crop_assignments:
                last = crop_assignments[-1]
                crop_assignments[-1] = (last[0], last[1] + remaining_beds)
        else:
            # Equal distribution if no defaults
            per_crop = len(cat_beds) // len(cat_crops)
            leftover = len(cat_beds) % len(cat_crops)
            for i, crop in enumerate(cat_crops):
                extra = 1 if i < leftover else 0
                crop_assignments.append((crop, per_crop + extra))

        # Assign crops to beds
        assign_idx = 0
        for crop, count in crop_assignments:
            for _ in range(count):
                if assign_idx < len(cat_beds):
                    bed = cat_beds[assign_idx]
                    result[bed['id']] = {
                        'category': category,
                        'crop_id': crop['id']
                    }
                    assign_idx += 1

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

@cycle_bp.route('/generate/<int:garden_id>', methods=['POST'])
def generate_cycle(garden_id):
    """Generate the next cycle for a garden.

    Steps:
    1. Save snapshot of current cycle's actuals
    2. Generate next cycle (category rotation)
    3. Redirect to distribution page for the new cycle
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
        return redirect(url_for('cycle.bootstrap_form', garden_id=garden_id))

    # Step 1: Save snapshot of current cycle actuals
    snapshot_file = save_snapshot(garden_id, current_cycle)
    if snapshot_file:
        flash(f"Snapshot sauvegardé : {snapshot_file}", "info")

    # Step 2: Generate next cycle
    new_cycle, error = generate_next_cycle(garden_id)
    if error:
        flash(f"Erreur lors de la génération : {error}", "error")
        return redirect(url_for('main.index', garden_id=garden_id))

    flash(f"Cycle {new_cycle} généré avec succès ! Ajustez la répartition ci-dessous.", "success")

    # Step 3: Redirect to distribution page
    return redirect(url_for('distribution.distribution_page',
                            garden_id=garden_id, cycle=new_cycle))

