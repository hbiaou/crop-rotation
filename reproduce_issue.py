import os
import sqlite3
import shutil
from app import create_app
from database import init_db, get_db, save_distribution_profiles
from rotation_engine import generate_next_cycle, assign_crops
from routes.distribution import save_distribution

# Setup
db_path = os.path.join(os.getcwd(), 'reproduce.db')
if os.path.exists(db_path):
    os.remove(db_path)

app = create_app()
app.config['DATABASE'] = db_path

# Helper to inspect results
def inspect_results(garden_id, cycle):
    with app.app_context():
        conn = get_db()
        rows = conn.execute("""
            SELECT cp.id, cp.planned_crop_id, c.crop_name, dp.target_percentage
            FROM cycle_plans cp
            LEFT JOIN crops c ON cp.planned_crop_id = c.id
            LEFT JOIN distribution_profiles dp ON cp.planned_crop_id = dp.crop_id AND dp.garden_id = cp.garden_id AND dp.cycle = cp.cycle
            WHERE cp.garden_id = ? AND cp.cycle = ?
        """, (garden_id, cycle)).fetchall()
        
        print(f"\n--- Inspection for {cycle} ---")
        counts = {}
        for r in rows:
            name = r['crop_name'] if r['crop_name'] else 'None'
            counts[name] = counts.get(name, 0) + 1
            # print(f"Plan {r['id']}: {name} (Target: {r['target_percentage']}%)")
            
        print(f"Counts: {counts}")
        return counts

def run_test():
    with app.app_context():
        # Clean slate
        conn = get_db()
        conn.execute("DROP TABLE IF EXISTS cycle_plans")
        conn.execute("DROP TABLE IF EXISTS distribution_profiles")
        conn.execute("DROP TABLE IF EXISTS sub_beds")
        conn.execute("DROP TABLE IF EXISTS beds")
        conn.execute("DROP TABLE IF EXISTS gardens")
        conn.execute("DROP TABLE IF EXISTS crops")
        conn.execute("DROP TABLE IF EXISTS rotation_sequence")
        conn.execute("DROP TABLE IF EXISTS settings")
        conn.commit()
        conn.close()

        init_db()
        conn = get_db()
        
        # 1. Create Garden
        conn.execute("""
            INSERT INTO gardens (name, garden_code, beds, bed_length_m, sub_beds_per_bed, active_sub_beds)
            VALUES ('Test Garden', 'TG', 100, 20.0, 1, 100)
        """)
        garden_id = conn.execute("SELECT id FROM gardens WHERE garden_code='TG'").fetchone()[0]
        
        # 2. Add Beds (100 beds to make percentages obvious)
        for i in range(1, 101):
            conn.execute("INSERT INTO sub_beds (garden_id, bed_number, sub_bed_position, is_reserve) VALUES (?, ?, 1, 0)", (garden_id, i))
        
        # 3. Seed Rotation Sequence
        # Valid: 'Feuille','Graine','Racine','Fruit','Couverture'
        rotation = ['Racine', 'Feuille', 'Fruit', 'Graine', 'Couverture']
        for i, cat in enumerate(rotation):
            conn.execute("INSERT INTO rotation_sequence (position, category) VALUES (?, ?)", (i+1, cat))

        # 4. Add Crops (Category: Feuille)
        # We need to make sure we use crop IDs that exist.
        # Let's use 'Laitue' and 'Epinard' which should be seeded by init_db/seed_defaults or we add them.
        # Check if they exist
        laitue = conn.execute("SELECT id FROM crops WHERE crop_name='Laitue'").fetchone()
        epinard = conn.execute("SELECT id FROM crops WHERE crop_name='Epinard'").fetchone()
        
        if not laitue or not epinard:
            # Add them if not present (though seed_defaults should handle it)
            conn.execute("INSERT OR IGNORE INTO crops (crop_name, category) VALUES ('Laitue', 'Feuille')")
            conn.execute("INSERT OR IGNORE INTO crops (crop_name, category) VALUES ('Epinard', 'Feuille')")
            laitue_id = conn.execute("SELECT id FROM crops WHERE crop_name='Laitue'").fetchone()[0]
            epinard_id = conn.execute("SELECT id FROM crops WHERE crop_name='Epinard'").fetchone()[0]
        else:
            laitue_id = laitue[0]
            epinard_id = epinard[0]

        conn.commit()
        
        # 4. Bootstrap Previous Cycle (2024A)
        # We need previous cycle plans to generate next one.
        # Let's say previous was 'Racine' so next is 'Feuille' (as per rotation above).
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('current_cycle', '2024A')")
        sub_beds = conn.execute("SELECT id FROM sub_beds").fetchall()
        for sb in sub_beds:
            conn.execute("""
                INSERT INTO cycle_plans (sub_bed_id, garden_id, cycle, planned_category, is_override)
                VALUES (?, ?, '2024A', 'Racine', 0)
            """, (sb['id'], garden_id))
        conn.commit()
        
        print("--- Setup Complete ---")
        
        # 5. Generate 2024B (Feuille)
        new_cycle, err = generate_next_cycle(garden_id)
        if not new_cycle:
            print(f"Generation failed: {err}")
            return
            
        print(f"--- Generated {new_cycle} ---")
        
        # 6. Apply 50/50 Distribution
        print("\n--- Applying 50/50 ---")
        profiles = [
            (laitue_id, 50.0),
            (epinard_id, 50.0)
        ]
        save_distribution_profiles(garden_id, new_cycle, profiles)
        assign_crops(garden_id, new_cycle)
        
        c1 = inspect_results(garden_id, new_cycle)
        if c1.get('Laitue') != 50 or c1.get('Epinard') != 50:
            print("FAILURE: 50/50 failed.")
        
        # 7. Apply 20/80 Distribution
        print("\n--- Applying 20/80 ---")
        profiles_2 = [
            (laitue_id, 20.0),
            (epinard_id, 80.0)
        ]
        save_distribution_profiles(garden_id, new_cycle, profiles_2)
        assign_crops(garden_id, new_cycle)
        
        c2 = inspect_results(garden_id, new_cycle)
        if c2.get('Laitue') != 20 or c2.get('Epinard') != 80:
             print(f"FAILURE: 20/80 failed. Got {c2}")
        else:
             print("SUCCESS: 20/80 applied correctly.")

if __name__ == '__main__':
    run_test()
