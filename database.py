"""
database.py — SQLite schema creation, seed data, and database operations.

Creates all tables exactly as specified in FEATURES_SPEC.md section 4.
Uses WAL mode for concurrent read performance.
"""

import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'crop_rotation.db')


def get_db():
    """Get a database connection with WAL mode and foreign keys enabled."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables, views, and indexes if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()

    # Table: settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Table: gardens
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gardens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            garden_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            beds INTEGER NOT NULL,
            bed_length_m REAL NOT NULL,
            bed_width_m REAL NOT NULL DEFAULT 1.0,
            sub_beds_per_bed INTEGER NOT NULL,
            active_sub_beds INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table: sub_beds
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sub_beds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            garden_id INTEGER NOT NULL REFERENCES gardens(id),
            bed_number INTEGER NOT NULL,
            sub_bed_position INTEGER NOT NULL,
            is_reserve BOOLEAN DEFAULT 0,
            UNIQUE(garden_id, bed_number, sub_bed_position)
        )
    """)

    # Table: crops
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop_name TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL CHECK (category IN ('Feuille','Graine','Racine','Fruit','Couverture'))
        )
    """)

    # Table: rotation_sequence
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rotation_sequence (
            position INTEGER PRIMARY KEY,
            category TEXT UNIQUE NOT NULL CHECK (category IN ('Feuille','Graine','Racine','Fruit','Couverture'))
        )
    """)

    # Table: cycle_plans
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cycle_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sub_bed_id INTEGER NOT NULL REFERENCES sub_beds(id),
            garden_id INTEGER NOT NULL REFERENCES gardens(id),
            cycle TEXT NOT NULL,
            planned_category TEXT,
            planned_crop_id INTEGER REFERENCES crops(id),
            actual_category TEXT,
            actual_crop_id INTEGER REFERENCES crops(id),
            is_override BOOLEAN DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(sub_bed_id, cycle)
        )
    """)

    # Performance index
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cycle_plans_garden_cycle
        ON cycle_plans(garden_id, cycle)
    """)

    # Table: distribution_profiles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS distribution_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            garden_id INTEGER NOT NULL REFERENCES gardens(id),
            cycle TEXT NOT NULL,
            crop_id INTEGER NOT NULL REFERENCES crops(id),
            target_percentage REAL NOT NULL,
            UNIQUE(garden_id, cycle, crop_id)
        )
    """)

    # View: cycle_plans_view
    cursor.execute("DROP VIEW IF EXISTS cycle_plans_view")
    cursor.execute("""
        CREATE VIEW cycle_plans_view AS
        SELECT
            cp.*,
            sb.bed_number,
            sb.sub_bed_position,
            sb.is_reserve,
            g.garden_code,
            g.name AS garden_name,
            pc.crop_name AS planned_crop_name,
            ac.crop_name AS actual_crop_name
        FROM cycle_plans cp
        JOIN sub_beds sb ON cp.sub_bed_id = sb.id
        JOIN gardens g ON cp.garden_id = g.id
        LEFT JOIN crops pc ON cp.planned_crop_id = pc.id
        LEFT JOIN crops ac ON cp.actual_crop_id = ac.id
    """)

    conn.commit()
    conn.close()


def seed_defaults():
    """Populate default data if tables are empty. Idempotent — skips if data exists."""
    conn = get_db()
    cursor = conn.cursor()

    # --- Settings ---
    existing = cursor.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    if existing == 0:
        cursor.execute("INSERT INTO settings (key, value) VALUES ('cycles_per_year', '2')")

    # --- Rotation Sequence ---
    existing = cursor.execute("SELECT COUNT(*) FROM rotation_sequence").fetchone()[0]
    if existing == 0:
        sequence = [
            (1, 'Feuille'),
            (2, 'Graine'),
            (3, 'Racine'),
            (4, 'Fruit'),
            (5, 'Couverture'),
        ]
        cursor.executemany(
            "INSERT INTO rotation_sequence (position, category) VALUES (?, ?)",
            sequence
        )

    # --- Crops ---
    existing = cursor.execute("SELECT COUNT(*) FROM crops").fetchone()[0]
    if existing == 0:
        crops = [
            # Feuille
            ('Choux', 'Feuille'),
            ('Laitue', 'Feuille'),
            ('Crincrin', 'Feuille'),
            ('Amaranthe', 'Feuille'),
            # Graine
            ('Maïs', 'Graine'),
            ('Lentille', 'Graine'),
            ('Haricot-Vert', 'Graine'),
            ('Tournesol', 'Graine'),
            ('Sésame', 'Graine'),
            # Racine
            ('Carotte', 'Racine'),
            ('Oignon', 'Racine'),
            ('Patate', 'Racine'),
            ('Ail', 'Racine'),
            # Fruit
            ('Gombo', 'Fruit'),
            ('Piment', 'Fruit'),
            ('Tomate', 'Fruit'),
            ('Concombre', 'Fruit'),
            ('Pastèque', 'Fruit'),
            ('Fraise', 'Fruit'),
            # Couverture
            ('Crotalaria', 'Couverture'),
            ('Aeschynomene', 'Couverture'),
            ('Tithonia', 'Couverture'),
            ('Mucuna', 'Couverture'),
        ]
        cursor.executemany(
            "INSERT INTO crops (crop_name, category) VALUES (?, ?)",
            crops
        )

    # --- Gardens & Sub-beds ---
    existing = cursor.execute("SELECT COUNT(*) FROM gardens").fetchone()[0]
    if existing == 0:
        # G1: Grand Jardin — 28 beds × 4 sub-beds = 112 total, 110 active, 2 reserve
        cursor.execute("""
            INSERT INTO gardens (garden_code, name, beds, bed_length_m, bed_width_m, sub_beds_per_bed, active_sub_beds)
            VALUES ('G1', 'Grand Jardin', 28, 50.0, 1.0, 4, 110)
        """)
        g1_id = cursor.lastrowid

        # G2 — 23 beds × 2 sub-beds = 46 total, 45 active, 1 reserve
        cursor.execute("""
            INSERT INTO gardens (garden_code, name, beds, bed_length_m, bed_width_m, sub_beds_per_bed, active_sub_beds)
            VALUES ('G2', 'Petit Jardin', 23, 22.0, 1.0, 2, 45)
        """)
        g2_id = cursor.lastrowid

        # Create sub-beds for G1
        # Reserve: last bed (P28), last 2 sub-beds (S3, S4)
        for bed in range(1, 29):
            for pos in range(1, 5):
                is_reserve = 1 if (bed == 28 and pos >= 3) else 0
                cursor.execute(
                    "INSERT INTO sub_beds (garden_id, bed_number, sub_bed_position, is_reserve) VALUES (?, ?, ?, ?)",
                    (g1_id, bed, pos, is_reserve)
                )

        # Create sub-beds for G2
        # Reserve: last bed (P23), last sub-bed (S2)
        for bed in range(1, 24):
            for pos in range(1, 3):
                is_reserve = 1 if (bed == 23 and pos == 2) else 0
                cursor.execute(
                    "INSERT INTO sub_beds (garden_id, bed_number, sub_bed_position, is_reserve) VALUES (?, ?, ?, ?)",
                    (g2_id, bed, pos, is_reserve)
                )

    conn.commit()
    conn.close()


def get_gardens():
    """Retrieve all gardens."""
    conn = get_db()
    gardens = conn.execute("SELECT * FROM gardens ORDER BY garden_code").fetchall()
    conn.close()
    return gardens


def get_garden(garden_id):
    """Retrieve a single garden by ID."""
    conn = get_db()
    garden = conn.execute("SELECT * FROM gardens WHERE id = ?", (garden_id,)).fetchone()
    conn.close()
    return garden


def get_sub_beds(garden_id, active_only=False):
    """Retrieve sub-beds for a garden, optionally filtering to active only."""
    conn = get_db()
    if active_only:
        beds = conn.execute(
            "SELECT * FROM sub_beds WHERE garden_id = ? AND is_reserve = 0 ORDER BY bed_number, sub_bed_position",
            (garden_id,)
        ).fetchall()
    else:
        beds = conn.execute(
            "SELECT * FROM sub_beds WHERE garden_id = ? ORDER BY bed_number, sub_bed_position",
            (garden_id,)
        ).fetchall()
    conn.close()
    return beds


def get_cycles(garden_id=None):
    """Retrieve distinct cycles, optionally filtered by garden."""
    conn = get_db()
    if garden_id:
        cycles = conn.execute(
            "SELECT DISTINCT cycle FROM cycle_plans WHERE garden_id = ? ORDER BY cycle DESC",
            (garden_id,)
        ).fetchall()
    else:
        cycles = conn.execute(
            "SELECT DISTINCT cycle FROM cycle_plans ORDER BY cycle DESC"
        ).fetchall()
    conn.close()
    return [row['cycle'] for row in cycles]


def get_crops(category=None):
    """Retrieve crops, optionally filtered by category."""
    conn = get_db()
    if category:
        crops = conn.execute(
            "SELECT * FROM crops WHERE category = ? ORDER BY crop_name",
            (category,)
        ).fetchall()
    else:
        crops = conn.execute("SELECT * FROM crops ORDER BY category, crop_name").fetchall()
    conn.close()
    return crops


def get_setting(key, default=None):
    """Get a setting value by key."""
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return row['value']
    return default


def get_rotation_sequence():
    """Get the rotation sequence ordered by position."""
    conn = get_db()
    sequence = conn.execute(
        "SELECT * FROM rotation_sequence ORDER BY position"
    ).fetchall()
    conn.close()
    return sequence


def get_garden_stats(garden_id):
    """Get statistics for a garden (total beds, active, reserve counts)."""
    conn = get_db()
    garden = conn.execute("SELECT * FROM gardens WHERE id = ?", (garden_id,)).fetchone()
    if not garden:
        conn.close()
        return None

    total_sub_beds = conn.execute(
        "SELECT COUNT(*) FROM sub_beds WHERE garden_id = ?", (garden_id,)
    ).fetchone()[0]
    active_sub_beds = conn.execute(
        "SELECT COUNT(*) FROM sub_beds WHERE garden_id = ? AND is_reserve = 0", (garden_id,)
    ).fetchone()[0]
    reserve_sub_beds = conn.execute(
        "SELECT COUNT(*) FROM sub_beds WHERE garden_id = ? AND is_reserve = 1", (garden_id,)
    ).fetchone()[0]

    conn.close()
    return {
        'garden': garden,
        'total_sub_beds': total_sub_beds,
        'active_sub_beds': active_sub_beds,
        'reserve_sub_beds': reserve_sub_beds,
        'beds': garden['beds'],
    }


# ========================================
# Garden CRUD
# ========================================

def create_garden(garden_code, name, beds, bed_length_m, bed_width_m, sub_beds_per_bed):
    """Create a new garden and auto-generate its sub-beds. Returns garden_id or None."""
    conn = get_db()
    try:
        total = beds * sub_beds_per_bed
        conn.execute(
            """INSERT INTO gardens (garden_code, name, beds, bed_length_m, bed_width_m, sub_beds_per_bed, active_sub_beds)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (garden_code, name, beds, bed_length_m, bed_width_m, sub_beds_per_bed, total)
        )
        garden_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Auto-generate sub-beds (all active by default)
        for bed in range(1, beds + 1):
            for pos in range(1, sub_beds_per_bed + 1):
                conn.execute(
                    "INSERT INTO sub_beds (garden_id, bed_number, sub_bed_position, is_reserve) VALUES (?, ?, ?, 0)",
                    (garden_id, bed, pos)
                )
        conn.commit()
        return garden_id
    except sqlite3.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def update_garden(garden_id, name, beds, bed_length_m, bed_width_m, sub_beds_per_bed):
    """Update garden config and regenerate sub-beds if bed/sub-bed counts changed."""
    conn = get_db()
    try:
        old = conn.execute("SELECT * FROM gardens WHERE id = ?", (garden_id,)).fetchone()
        if not old:
            return False

        # Update garden record
        conn.execute(
            """UPDATE gardens SET name=?, beds=?, bed_length_m=?, bed_width_m=?, sub_beds_per_bed=?
               WHERE id=?""",
            (name, beds, bed_length_m, bed_width_m, sub_beds_per_bed, garden_id)
        )

        # If bed structure changed, regenerate sub-beds
        if old['beds'] != beds or old['sub_beds_per_bed'] != sub_beds_per_bed:
            # Delete sub-beds not referenced in cycle_plans
            conn.execute(
                """DELETE FROM sub_beds WHERE garden_id = ?
                   AND id NOT IN (SELECT DISTINCT sub_bed_id FROM cycle_plans)""",
                (garden_id,)
            )
            # Add missing sub-beds
            for bed in range(1, beds + 1):
                for pos in range(1, sub_beds_per_bed + 1):
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO sub_beds (garden_id, bed_number, sub_bed_position, is_reserve) VALUES (?, ?, ?, 0)",
                            (garden_id, bed, pos)
                        )
                    except sqlite3.IntegrityError:
                        pass

        # Recount active sub-beds
        _recount_active(conn, garden_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def delete_garden(garden_id):
    """Delete a garden. Only allowed if no cycle_plans reference it. Returns (success, error_msg)."""
    conn = get_db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM cycle_plans WHERE garden_id = ?", (garden_id,)
        ).fetchone()[0]
        if count > 0:
            return False, "Ce jardin est utilisé dans des cycles existants."

        conn.execute("DELETE FROM sub_beds WHERE garden_id = ?", (garden_id,))
        conn.execute("DELETE FROM gardens WHERE id = ?", (garden_id,))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def toggle_sub_bed_reserve(sub_bed_id, is_reserve):
    """Toggle a sub-bed's reserve status and recount garden active_sub_beds."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE sub_beds SET is_reserve = ? WHERE id = ?",
            (1 if is_reserve else 0, sub_bed_id)
        )
        # Get garden_id for recount
        sb = conn.execute("SELECT garden_id FROM sub_beds WHERE id = ?", (sub_bed_id,)).fetchone()
        if sb:
            _recount_active(conn, sb['garden_id'])
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def _recount_active(conn, garden_id):
    """Recalculate gardens.active_sub_beds from actual sub_beds table. Uses existing connection."""
    active = conn.execute(
        "SELECT COUNT(*) FROM sub_beds WHERE garden_id = ? AND is_reserve = 0",
        (garden_id,)
    ).fetchone()[0]
    conn.execute(
        "UPDATE gardens SET active_sub_beds = ? WHERE id = ?",
        (active, garden_id)
    )


# ========================================
# Crop CRUD
# ========================================

def create_crop(crop_name, category):
    """Create a new crop. Returns crop_id or None if name already exists."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO crops (crop_name, category) VALUES (?, ?)",
            (crop_name.strip(), category)
        )
        crop_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        return crop_id
    except sqlite3.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def delete_crop(crop_id):
    """Delete a crop. Only allowed if not used in cycle_plans. Returns (success, error_msg)."""
    conn = get_db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM cycle_plans WHERE planned_crop_id = ? OR actual_crop_id = ?",
            (crop_id, crop_id)
        ).fetchone()[0]
        if count > 0:
            return False, "Cette culture est utilisée dans un cycle existant et ne peut pas être supprimée."

        conn.execute("DELETE FROM crops WHERE id = ?", (crop_id,))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def update_crop_category(crop_id, new_category):
    """Reassign a crop to a different category."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE crops SET category = ? WHERE id = ?",
            (new_category, crop_id)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


# ========================================
# Rotation Sequence
# ========================================

def save_rotation_sequence(ordered_categories):
    """Replace the rotation sequence with new ordered list of categories."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM rotation_sequence")
        for i, category in enumerate(ordered_categories, start=1):
            conn.execute(
                "INSERT INTO rotation_sequence (position, category) VALUES (?, ?)",
                (i, category)
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


# ========================================
# Settings
# ========================================

def update_setting(key, value):
    """Insert or update a setting."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_categories():
    """Get the list of valid categories from rotation_sequence."""
    conn = get_db()
    cats = conn.execute(
        "SELECT category FROM rotation_sequence ORDER BY position"
    ).fetchall()
    conn.close()
    return [row['category'] for row in cats]


# ========================================
# Cycle Plans
# ========================================

def get_cycle_plans_for_garden_cycle(garden_id, cycle):
    """Get existing cycle_plans for a garden+cycle combination."""
    conn = get_db()
    plans = conn.execute(
        "SELECT * FROM cycle_plans WHERE garden_id = ? AND cycle = ?",
        (garden_id, cycle)
    ).fetchall()
    conn.close()
    return plans


def create_cycle_plans_batch(records):
    """Bulk-insert cycle_plans records. Each record is a dict with keys:
    sub_bed_id, garden_id, cycle, planned_category, planned_crop_id,
    actual_category, actual_crop_id, is_override.
    Returns True on success, False on failure.
    """
    conn = get_db()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO cycle_plans
               (sub_bed_id, garden_id, cycle, planned_category, planned_crop_id,
                actual_category, actual_crop_id, is_override)
               VALUES (:sub_bed_id, :garden_id, :cycle, :planned_category, :planned_crop_id,
                        :actual_category, :actual_crop_id, :is_override)""",
            records
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_latest_cycle(garden_id):
    """Get the most recent cycle string for a garden, or None."""
    conn = get_db()
    row = conn.execute(
        "SELECT DISTINCT cycle FROM cycle_plans WHERE garden_id = ? ORDER BY cycle DESC LIMIT 1",
        (garden_id,)
    ).fetchone()
    conn.close()
    return row['cycle'] if row else None


def get_distribution_profiles(garden_id, cycle):
    """Get distribution profiles for a garden+cycle.

    Returns list of dicts with crop_id, target_percentage, crop_name, category.
    """
    conn = get_db()
    rows = conn.execute(
        """SELECT dp.*, c.crop_name, c.category
           FROM distribution_profiles dp
           JOIN crops c ON dp.crop_id = c.id
           WHERE dp.garden_id = ? AND dp.cycle = ?
           ORDER BY c.category, c.crop_name""",
        (garden_id, cycle)
    ).fetchall()
    conn.close()
    return rows


def save_distribution_profiles(garden_id, cycle, profiles):
    """Save distribution profiles for a garden+cycle.

    Args:
        garden_id: Garden ID
        cycle: Cycle string
        profiles: list of (crop_id, target_percentage) tuples

    Returns:
        True on success, False on failure.
    """
    conn = get_db()
    try:
        # Delete existing profiles for this garden+cycle
        conn.execute(
            "DELETE FROM distribution_profiles WHERE garden_id = ? AND cycle = ?",
            (garden_id, cycle)
        )
        # Insert new profiles
        conn.executemany(
            """INSERT INTO distribution_profiles (garden_id, cycle, crop_id, target_percentage)
               VALUES (?, ?, ?, ?)""",
            [(garden_id, cycle, crop_id, pct) for crop_id, pct in profiles]
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_cycle_plans_view(garden_id, cycle):
    """Get cycle_plans with joined data for a garden+cycle.

    Returns list of rows with all cycle_plans_view columns.
    """
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM cycle_plans_view
           WHERE garden_id = ? AND cycle = ?
           ORDER BY bed_number, sub_bed_position""",
        (garden_id, cycle)
    ).fetchall()
    conn.close()
    return rows


def get_cycle_state(garden_id, cycle):
    """Check the state of a cycle (has data, has distribution, has crop assignments).

    Returns dict with keys: has_plans, has_actual_data, has_distribution, has_crop_assignments.
    """
    conn = get_db()
    try:
        # Check if cycle_plans exist
        plan_count = conn.execute(
            "SELECT COUNT(*) FROM cycle_plans WHERE garden_id = ? AND cycle = ?",
            (garden_id, cycle)
        ).fetchone()[0]

        # Check if any actual data exists
        actual_count = conn.execute(
            """SELECT COUNT(*) FROM cycle_plans
               WHERE garden_id = ? AND cycle = ?
                 AND (actual_category IS NOT NULL OR actual_crop_id IS NOT NULL)""",
            (garden_id, cycle)
        ).fetchone()[0]

        # Check if distribution profiles exist
        dist_count = conn.execute(
            "SELECT COUNT(*) FROM distribution_profiles WHERE garden_id = ? AND cycle = ?",
            (garden_id, cycle)
        ).fetchone()[0]

        # Check if crop assignments exist
        crop_count = conn.execute(
            """SELECT COUNT(*) FROM cycle_plans
               WHERE garden_id = ? AND cycle = ?
                 AND planned_crop_id IS NOT NULL""",
            (garden_id, cycle)
        ).fetchone()[0]

        return {
            'has_plans': plan_count > 0,
            'has_actual_data': actual_count > 0,
            'has_distribution': dist_count > 0,
            'has_crop_assignments': crop_count > 0,
        }
    finally:
        conn.close()
