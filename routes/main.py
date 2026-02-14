"""
routes/main.py — Homepage, map view, override, and print view routes.

Provides:
- GET / — Homepage with garden selector, cycle selector, action buttons, garden stats
- GET /map/<garden_id>/<cycle> — Color-coded map visualization
- POST /map/<garden_id>/<cycle>/override — Record override on a sub-bed
- GET /api/crops/<category> — JSON list of crops for a category
- GET /print/<garden_id>/<cycle> — Print-optimized map view
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from database import (
    get_gardens, get_cycles, get_garden_stats, get_cycle_state,
    get_garden, get_map_data, get_crops, get_categories,
    update_cycle_plan_override, has_overrides
)
from utils.backup import list_backups

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Homepage — garden selector, cycle selector, action buttons, stats."""
    gardens = get_gardens()

    # Default to first garden if none selected
    selected_garden_id = request.args.get('garden_id', type=int)
    if not selected_garden_id and gardens:
        selected_garden_id = gardens[0]['id']

    # Get cycles for selected garden
    cycles = []
    stats = None
    cycle_state = None
    if selected_garden_id:
        cycles = get_cycles(selected_garden_id)
        stats = get_garden_stats(selected_garden_id)

    selected_cycle = request.args.get('cycle', '')
    if not selected_cycle and cycles:
        selected_cycle = cycles[0]

    has_cycles = len(cycles) > 0

    # Get cycle state for the selected cycle
    if selected_garden_id and selected_cycle:
        cycle_state = get_cycle_state(selected_garden_id, selected_cycle)

    # Get last backup date
    backups = list_backups()
    last_backup = backups[0] if backups else None

    return render_template(
        'index.html',
        gardens=gardens,
        selected_garden_id=selected_garden_id,
        cycles=cycles,
        selected_cycle=selected_cycle,
        has_cycles=has_cycles,
        stats=stats,
        cycle_state=cycle_state,
        last_backup=last_backup,
    )


@main_bp.route('/map/<int:garden_id>/<cycle>')
def map_view(garden_id, cycle):
    """Map visualization — horizontal striped chart with category colors."""
    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", "error")
        return redirect(url_for('main.index'))

    map_data = get_map_data(garden_id, cycle)
    if not map_data or not map_data['beds']:
        flash("Aucune donnée pour ce cycle.", "warning")
        return redirect(url_for('main.index'))

    # Cycle navigation
    all_cycles = get_cycles(garden_id)
    current_idx = all_cycles.index(cycle) if cycle in all_cycles else 0
    prev_cycle = all_cycles[current_idx + 1] if current_idx + 1 < len(all_cycles) else None
    next_cycle = all_cycles[current_idx - 1] if current_idx - 1 >= 0 else None

    # All crops grouped by category for the override modal
    categories = get_categories()
    crops_by_category = {}
    for cat in categories:
        crops_by_category[cat] = [
            {'id': c['id'], 'name': c['crop_name']}
            for c in get_crops(cat)
        ]

    # Sub-bed count (columns) from garden config
    sub_beds_per_bed = garden['sub_beds_per_bed']

    # Check if this cycle has overrides (for undo warning)
    cycle_has_overrides = has_overrides(garden_id, cycle)

    return render_template(
        'map_view.html',
        garden=garden,
        cycle=cycle,
        map_data=map_data,
        sub_beds_per_bed=sub_beds_per_bed,
        categories=categories,
        crops_by_category=crops_by_category,
        prev_cycle=prev_cycle,
        next_cycle=next_cycle,
        has_overrides=cycle_has_overrides,
    )


@main_bp.route('/map/<int:garden_id>/<cycle>/override', methods=['POST'])
def map_override(garden_id, cycle):
    """Record an override on a sub-bed."""
    plan_id = request.form.get('plan_id', type=int)
    actual_category = request.form.get('actual_category', '').strip()
    actual_crop_id = request.form.get('actual_crop_id', type=int)
    notes = request.form.get('notes', '').strip() or None

    if not plan_id or not actual_category:
        flash("Données de remplacement invalides.", "error")
        return redirect(url_for('main.map_view', garden_id=garden_id, cycle=cycle))

    success = update_cycle_plan_override(plan_id, actual_category, actual_crop_id, notes)
    if success:
        flash("Remplacement enregistré avec succès.", "success")
    else:
        flash("Erreur lors de l'enregistrement du remplacement.", "error")

    return redirect(url_for('main.map_view', garden_id=garden_id, cycle=cycle))


@main_bp.route('/api/crops/<category>')
def api_crops_by_category(category):
    """JSON API — get crops filtered by category."""
    crops = get_crops(category)
    return jsonify([
        {'id': c['id'], 'name': c['crop_name']}
        for c in crops
    ])


@main_bp.route('/print/<int:garden_id>/<cycle>')
def print_view(garden_id, cycle):
    """Print-optimized map view."""
    garden = get_garden(garden_id)
    if not garden:
        flash("Jardin introuvable.", "error")
        return redirect(url_for('main.index'))

    map_data = get_map_data(garden_id, cycle)
    if not map_data or not map_data['beds']:
        flash("Aucune donnée pour ce cycle.", "warning")
        return redirect(url_for('main.index'))

    categories = get_categories()
    sub_beds_per_bed = garden['sub_beds_per_bed']

    from datetime import date
    today = date.today().strftime('%d/%m/%Y')

    return render_template(
        'print_map.html',
        garden=garden,
        cycle=cycle,
        map_data=map_data,
        sub_beds_per_bed=sub_beds_per_bed,
        categories=categories,
        print_date=today,
    )
