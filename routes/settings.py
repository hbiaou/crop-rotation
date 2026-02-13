"""
routes/settings.py — Settings and administration routes.

Provides:
- GET /settings — Settings page
- POST /settings/garden — Add/edit garden configuration
- POST /settings/crop — Add/edit/delete crops
- POST /settings/rotation — Update rotation sequence
- POST /settings/cycles — Update cycles per year

See FEATURES_SPEC.md sections F10, F11.
"""

from flask import Blueprint

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

# Routes will be implemented in a future session.
