"""
routes/cycle.py — Cycle generation, undo, and override routes.

Provides:
- POST /cycle/generate — Generate next cycle (with auto-backup)
- POST /cycle/undo — Undo last generated cycle
- POST /cycle/override — Record an override on a sub-bed

See FEATURES_SPEC.md sections F2, F6, F8.
"""

from flask import Blueprint

cycle_bp = Blueprint('cycle', __name__, url_prefix='/cycle')

# Routes will be implemented in a future session.
