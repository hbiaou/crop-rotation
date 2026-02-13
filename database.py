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
