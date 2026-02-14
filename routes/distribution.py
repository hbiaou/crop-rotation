"""
routes/distribution.py — Distribution adjustment routes.

Provides:
- GET /distribution/<garden_id>/<cycle> — View/edit crop distribution percentages
- POST /distribution/<garden_id>/<cycle> — Save distribution and trigger crop assignment

See FEATURES_SPEC.md sections F3, F4.
"""

import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash

from database import (
    get_garden, get_crops, get_rotation_sequence,
    get_distribution_profiles, save_distribution_profiles, get_db
)
from rotation_engine import assign_crops

distribution_bp = Blueprint('distribution', __name__, url_prefix='/distribution')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_default_distribution(garden_code):
    """Load default distribution percentages from defaults.json for a garden.

    Returns a nested dict: {category: {crop_name: percentage}}
    """
    defaults_path = os.path.join(BASE_DIR, 'config', 'defaults.json')
    try:
        with open(defaults_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}

    dist_defaults = data.get('distribution_defaults', {})

    # Try exact code, then uppercase
    if garden_code in dist_defaults:
        return dist_defaults[garden_code]
    if garden_code.upper() in dist_defaults:
        return dist_defaults[garden_code.upper()]

    # Fallback to first available
    if dist_defaults:
        return next(iter(dist_defaults.values()))

    return {}


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

    # 2. If none, try previous cycle
    if not existing_profiles:
        conn = get_db()
        prev_cycle_row = conn.execute(
            """SELECT DISTINCT cycle FROM cycle_plans
               WHERE garden_id = ? AND cycle < ?
               ORDER BY cycle DESC LIMIT 1""",
            (garden_id, cycle)
        ).fetchone()
        conn.close()

        if prev_cycle_row:
            existing_profiles = get_distribution_profiles(garden_id, prev_cycle_row['cycle'])

    # 3. If still none, use defaults.json
    if not existing_profiles:
        defaults = _load_default_distribution(garden['garden_code'])
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
    """Save distribution percentages and trigger smart crop assignment."""
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

    # Trigger smart crop assignment
    ok, err = assign_crops(garden_id, cycle)
    if not ok:
        flash(f"Répartition enregistrée, mais erreur lors de l'affectation : {err}", "warning")
    else:
        flash("Répartition enregistrée et cultures affectées avec succès !", "success")

    return redirect(url_for('main.index', garden_id=garden_id, cycle=cycle))
