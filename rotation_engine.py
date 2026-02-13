"""
rotation_engine.py — Core rotation algorithm for crop rotation planning.

This module implements:
- Category rotation: advancing each bed one step in the configured rotation sequence
- Smart crop assignment with 5-cycle lookback and distance-weighted scoring
- Distribution resolution: converting percentage targets to absolute bed counts

Algorithm details:
- Rotation sequence wraps: last category → first category
- Same-category repeat is forbidden
- Penalty table for variety cycling:
    1 cycle ago = -50, 2 = -30, 3 = -15, 4 = -5, 5 = -1
- Tie-breaking by bed ID ascending for deterministic assignment

See FEATURES_SPEC.md sections F2, F3, F4 for full specification.
"""

# Implementation will be added in a future session.
