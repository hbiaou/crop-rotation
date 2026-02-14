"""
utils/snapshots.py — JSON snapshot generation for finalized cycle maps.

Saves actual planting data to history/ as JSON files.
Format: {garden_code}_{cycle}_actual.json
Contains: garden info, date, and array of bed/sub-bed/category/crop/notes.

See FEATURES_SPEC.md section F12 for full specification.
"""

import os
import json
from datetime import datetime
from database import get_db, get_garden

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_DIR = os.path.join(BASE_DIR, 'history')


def save_snapshot(garden_id, cycle):
    """
    Save actual planting data for a cycle as a JSON file.

    Only saves actual data (actual_category, actual_crop). Skips sub-beds
    with no actual data. Reserve sub-beds are excluded.

    Args:
        garden_id: Garden ID
        cycle: Cycle string (e.g., "2026A")

    Returns:
        Filename of the saved snapshot, or None if no actual data to save.
    """
    os.makedirs(HISTORY_DIR, exist_ok=True)

    garden = get_garden(garden_id)
    if not garden:
        return None

    conn = get_db()
    try:
        # Query actual data from cycle_plans_view
        rows = conn.execute(
            """SELECT cp.sub_bed_id, sb.bed_number, sb.sub_bed_position,
                      sb.is_reserve, cp.actual_category, cp.actual_crop_id,
                      cp.is_override, cp.notes,
                      c.crop_name AS actual_crop_name
               FROM cycle_plans cp
               JOIN sub_beds sb ON cp.sub_bed_id = sb.id
               LEFT JOIN crops c ON cp.actual_crop_id = c.id
               WHERE cp.garden_id = ? AND cp.cycle = ?
                 AND sb.is_reserve = 0
               ORDER BY sb.bed_number, sb.sub_bed_position""",
            (garden_id, cycle)
        ).fetchall()

        # Filter to only rows with actual data
        beds_data = []
        for row in rows:
            if row['actual_category'] is None and row['actual_crop_id'] is None:
                continue

            beds_data.append({
                'bed': row['bed_number'],
                'sub_bed': row['sub_bed_position'],
                'category': row['actual_category'],
                'crop': row['actual_crop_name'],
                'was_override': bool(row['is_override']),
                'notes': row['notes'],
            })

        if not beds_data:
            return None

        snapshot = {
            'garden_code': garden['garden_code'],
            'garden_name': garden['name'],
            'cycle': cycle,
            'finalized_at': datetime.now().isoformat(timespec='seconds'),
            'beds': beds_data,
        }

        filename = f"{garden['garden_code']}_{cycle}_actual.json"
        filepath = os.path.join(HISTORY_DIR, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

        return filename

    except Exception:
        return None
    finally:
        conn.close()
