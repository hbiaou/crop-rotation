"""
routes/distribution.py — Distribution adjustment routes.

Provides:
- GET /distribution/<cycle> — View/edit crop distribution percentages
- POST /distribution/confirm — Confirm distribution and trigger crop assignment

See FEATURES_SPEC.md sections F3, F4.
"""

from flask import Blueprint

distribution_bp = Blueprint('distribution', __name__, url_prefix='/distribution')

# Routes will be implemented in a future session.
