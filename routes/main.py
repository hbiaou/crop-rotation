"""
routes/main.py — Homepage and cycle selection routes.

Provides:
- GET / — Homepage with garden selector, cycle selector, action buttons, garden stats
"""

from flask import Blueprint, render_template, request
from database import get_gardens, get_cycles, get_garden_stats, get_cycle_state

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

    return render_template(
        'index.html',
        gardens=gardens,
        selected_garden_id=selected_garden_id,
        cycles=cycles,
        selected_cycle=selected_cycle,
        has_cycles=has_cycles,
        stats=stats,
        cycle_state=cycle_state,
    )
