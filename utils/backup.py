"""
utils/backup.py — Database backup and restore operations.

Copies the .db file to backups/ with timestamped filenames.
Backup triggers: before cycle generation, on export, manual from Settings.
Format: crop_rotation_YYYYMMDD_HHMMSS_{reason}.db

See FEATURES_SPEC.md section 6 (Backup Strategy) for full specification.
"""

import os
import shutil
from datetime import datetime

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'crop_rotation.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')


def backup_db(reason='manual'):
    """
    Copy the current database to backups/ with a timestamped filename.

    Args:
        reason: Short tag for the backup trigger (e.g., 'manual', 'pre_generate', 'export').

    Returns:
        The filename of the created backup, or None on failure.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    if not os.path.exists(DB_PATH):
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Sanitize reason string
    safe_reason = reason.replace(' ', '_').replace('/', '_')[:30]
    filename = f'crop_rotation_{timestamp}_{safe_reason}.db'
    dest = os.path.join(BACKUP_DIR, filename)

    try:
        shutil.copy2(DB_PATH, dest)
        return filename
    except Exception:
        return None


def list_backups():
    """
    List all backup files in the backups/ directory.

    Returns:
        List of dicts with keys: filename, timestamp, size_bytes, size_display, reason.
        Sorted by timestamp descending (newest first).
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    backups = []
    for f in os.listdir(BACKUP_DIR):
        if f.startswith('crop_rotation_') and f.endswith('.db'):
            filepath = os.path.join(BACKUP_DIR, f)
            stat = os.stat(filepath)
            size_bytes = stat.st_size

            # Parse timestamp and reason from filename
            # Format: crop_rotation_YYYYMMDD_HHMMSS_reason.db
            parts = f.replace('.db', '').split('_')
            timestamp_str = ''
            reason = ''
            if len(parts) >= 4:
                # parts: ['crop', 'rotation', 'YYYYMMDD', 'HHMMSS', 'reason', ...]
                date_part = parts[2]  # YYYYMMDD
                time_part = parts[3]  # HHMMSS
                timestamp_str = f'{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}'
                reason = '_'.join(parts[4:]) if len(parts) > 4 else ''

            # Human-readable size
            if size_bytes < 1024:
                size_display = f'{size_bytes} o'
            elif size_bytes < 1024 * 1024:
                size_display = f'{size_bytes / 1024:.1f} Ko'
            else:
                size_display = f'{size_bytes / (1024 * 1024):.1f} Mo'

            backups.append({
                'filename': f,
                'timestamp': timestamp_str,
                'size_bytes': size_bytes,
                'size_display': size_display,
                'reason': reason,
            })

    # Sort newest first
    backups.sort(key=lambda b: b['filename'], reverse=True)
    return backups


def restore_db(filename):
    """
    Replace the current database with a backup file.

    DANGEROUS: This overwrites the current database entirely.

    Args:
        filename: Name of the backup file in backups/ directory.

    Returns:
        True on success, False on failure.
    """
    backup_path = os.path.join(BACKUP_DIR, filename)

    if not os.path.exists(backup_path):
        return False

    # Validate it's a real backup file (basic safety check)
    if not filename.startswith('crop_rotation_') or not filename.endswith('.db'):
        return False

    try:
        shutil.copy2(backup_path, DB_PATH)
        return True
    except Exception:
        return False
