"""
routes/distribution.py — Distribution adjustment routes.

Provides:
- GET /distribution/<garden_id>/<cycle> — View/edit crop distribution percentages
- POST /distribution/<garden_id>/<cycle> — Save distribution as defaults for future cycles

See FEATURES_SPEC.md sections F3, F4.
"""

import json
from flask import Blueprint, render_template, request, redirect, url_for, flash

from database import (
    get_garden, get_crops, get_rotation_sequence,
    get_distribution_profiles, save_distribution_profiles, get_db,
    get_setting, update_setting
)

distribution_bp = Blueprint('distribution', __name__, url_prefix='/distribution')


def _load_default_distribution(garden_id):
    """Load default distribution percentages for a specific garden.

    Priority:
    1. Database settings table (key: distribution_defaults_<garden_id>)
    2. Equal split across all enabled crops per category

    Args:
        garden_id: The garden ID to load defaults for.

    Returns:
        dict: {category: {crop_name: percentage}}
    """
    from database import get_categories

    # 1. Try garden-specific DB defaults
    db_defaults_json = get_setting(f'distribution_defaults_{garden_id}')
    if db_defaults_json:
        try:
            defaults = json.loads(db_defaults_json)
            if defaults:  # Non-empty
                return defaults
        except json.JSONDecodeError:
            pass

    # 2. Fallback: equal split across enabled crops per category
    all_crops = get_crops()
    categories = get_categories()

    defaults = {}
    for cat in categories:
        cat_crops = [c for c in all_crops if c['category'] == cat]
        if not cat_crops:
            continue
        # Equal percentage for each crop, rounded to nearest integer
        n = len(cat_crops)
        base_pct = 100 // n
        remainder = 100 % n
        cat_dist = {}
        for i, crop in enumerate(cat_crops):
            cat_dist[crop['crop_name']] = base_pct + (1 if i < remainder else 0)
        defaults[cat] = cat_dist

    return defaults


@distribution_bp.route('/<int:garden_id>/<cycle>')
def distribution_page(garden_id, cycle):
    """Distribution adjustment page — show categories with crop percentage sliders."""
    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", "error")
        return redirect(url_for('main.index'))

    # Get rotation sequence for category ordering
    rotation_seq = get_rotation_sequence()
    categories = [r['category'] for r in rotation_seq]

    # Get all crops grouped by category
    all_crops = get_crops()
    crops_by_category = {}
    for crop in all_crops:
        cat = crop['category']
        if cat not in crops_by_category:
            crops_by_category[cat] = []
        crops_by_category[cat].append(dict(crop))

    # Count beds per category for this cycle
    conn = get_db()
    beds_per_category = {}
    for cat in categories:
        count = conn.execute(
            """SELECT COUNT(*) FROM cycle_plans cp
               JOIN sub_beds sb ON cp.sub_bed_id = sb.id
               WHERE cp.garden_id = ? AND cp.cycle = ?
                 AND cp.planned_category = ? AND sb.is_reserve = 0""",
            (garden_id, cycle, cat)
        ).fetchone()[0]
        beds_per_category[cat] = count
    conn.close()

    # Load existing distribution or fallback
    # 1. Check current cycle profiles
    existing_profiles = get_distribution_profiles(garden_id, cycle)

    # 2. If none, try defaults (DB or equal-split fallback)
    defaults = {}
    if not existing_profiles:
        defaults = _load_default_distribution(garden_id)

    # 4. Build profile map
    if not existing_profiles:
        # Use defaults
        # defaults is a dict like {category: {crop_name: percentage}}
        # Flatten into crop_id → percentage map
        profile_map = {}
        for crop in all_crops:
            cat = crop['category']
            crop_name = crop['crop_name']
            if cat in defaults and crop_name in defaults[cat]:
                profile_map[crop['id']] = defaults[cat][crop_name]

        # Build category data with defaults
        category_data = []
        for cat in categories:
            cat_crops = crops_by_category.get(cat, [])
            crop_list = []
            for crop in cat_crops:
                pct = profile_map.get(crop['id'], 0)
                crop_list.append({
                    'crop_id': crop['id'],
                    'crop_name': crop['crop_name'],
                    'percentage': pct,
                })
            category_data.append({
                'category': cat,
                'total_beds': beds_per_category.get(cat, 0),
                'crops': crop_list,
            })
    else:
        # Build from existing profiles
        profile_map = {p['crop_id']: p['target_percentage'] for p in existing_profiles}

        category_data = []
        for cat in categories:
            cat_crops = crops_by_category.get(cat, [])
            crop_list = []
            for crop in cat_crops:
                pct = profile_map.get(crop['id'], 0)
                crop_list.append({
                    'crop_id': crop['id'],
                    'crop_name': crop['crop_name'],
                    'percentage': pct,
                })
            category_data.append({
                'category': cat,
                'total_beds': beds_per_category.get(cat, 0),
                'crops': crop_list,
            })

    return render_template('distribution.html',
                           garden=garden,
                           cycle=cycle,
                           category_data=category_data)


@distribution_bp.route('/<int:garden_id>/<cycle>', methods=['POST'])
def save_distribution(garden_id, cycle):
    """Save distribution percentages as defaults for future cycle generation.

    Note: This does NOT reassign crops on the current cycle. Distribution
    percentages are saved and will be used when generating the next cycle.
    """
    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", "error")
        return redirect(url_for('main.index'))

    # Parse form data: crop_{crop_id} = percentage
    profiles = []
    for key, value in request.form.items():
        if key.startswith('crop_'):
            crop_id = int(key.replace('crop_', ''))
            try:
                pct = float(value)
            except ValueError:
                pct = 0.0
            if pct > 0:
                profiles.append((crop_id, pct))

    # Save distribution profiles
    success = save_distribution_profiles(garden_id, cycle, profiles)
    if not success:
        flash("Erreur lors de l'enregistrement de la répartition.", "error")
        return redirect(url_for('distribution.distribution_page',
                                garden_id=garden_id, cycle=cycle))

    # Save as garden defaults for future cycles
    _save_as_garden_defaults(garden_id, profiles)

    flash("Répartition enregistrée ! Elle sera appliquée lors de la génération du prochain cycle.", "success")

    return redirect(url_for('main.index', garden_id=garden_id, cycle=cycle))


def _save_as_garden_defaults(garden_id, profiles):
    """Save distribution profiles as garden defaults for future cycle generation.

    Args:
        garden_id: Garden ID
        profiles: List of (crop_id, percentage) tuples
    """
    # Build crop_id -> crop info lookup
    all_crops = get_crops()
    crop_lookup = {c['id']: c for c in all_crops}

    # Convert to {category: {crop_name: percentage}} format
    defaults = {}
    for crop_id, pct in profiles:
        crop = crop_lookup.get(crop_id)
        if crop:
            cat = crop['category']
            if cat not in defaults:
                defaults[cat] = {}
            defaults[cat][crop['crop_name']] = pct

    # Save to settings
    update_setting(f'distribution_defaults_{garden_id}', json.dumps(defaults))
