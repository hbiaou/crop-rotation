
import os
import sys
import sqlite3
import json
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db, get_db, create_garden, create_crop, create_cycle_plans_batch, get_cycle_plans_for_garden_cycle, get_latest_cycle
from rotation_engine import generate_next_cycle, assign_crops
from utils.snapshots import save_snapshot

TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_rotation.sqlite')

def setup_test_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    # Override DB path in database.py temporarily or just mock get_db
    # Since database.py uses a global DB_PATH, we can monkeypatch it
    import database
    database.DB_PATH = TEST_DB
    init_db()

def verify_rotation():
    print("=== Verifying Rotation Engine ===")
    setup_test_db()

    # 1. Create Garden
    print("Creating garden...")
    garden_id = create_garden('T1', 'Test Garden', 10, 20, 1, 2) # 10 beds, 2 sub/bed = 20 sub-beds

    # 2. Create Crops
    print("Creating crops...")
    crops = [
        ('Choux', 'Feuille'),
        ('Maïs', 'Graine'),
        ('Carotte', 'Racine'),
        ('Tomate', 'Fruit'),
        ('Haricot', 'Graine'), # Extra crop
    ]
    crop_ids = {}
    for name, cat in crops:
        crop_ids[name] = create_crop(name, cat)

    # 3. Simulate Bootstrap (Cycle 2025A)
    print("Simulating bootstrap (2025A)...")
    records = []
    # Beds 1-5: Feuille (Choux)
    # Beds 6-10: Graine (Maïs)
    # Sub-bed 20 is reserve
    for i in range(1, 21):
        is_reserve = (i == 20)
        # Update sub_bed is_reserve status
        conn = get_db()
        conn.execute("UPDATE sub_beds SET is_reserve = ? WHERE id = ?", (1 if is_reserve else 0, i))
        conn.commit()
        conn.close()

        if is_reserve:
            continue

        cat = 'Feuille' if i <= 10 else 'Graine'
        crop = crop_ids['Choux'] if i <= 10 else crop_ids['Maïs']
        
        records.append({
            'sub_bed_id': i,
            'garden_id': garden_id,
            'cycle': '2025A',
            'planned_category': cat,
            'planned_crop_id': crop,
            'actual_category': cat,
            'actual_crop_id': crop, # Actuals match plan
            'is_override': 0
        })
    
    create_cycle_plans_batch(records)

    # 4. Verify Snapshot
    print("Testing save_snapshot...")
    try:
        snap_file = save_snapshot(garden_id, '2025A')
    except Exception as e:
        print(f"snapshot exception: {e}")
        snap_file = None
        
    if snap_file:
        full_snap_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'history', snap_file)
        if os.path.exists(full_snap_path):
            print(f"[OK] Snapshot created: {full_snap_path}")
            with open(full_snap_path, 'r') as f:
                data = json.load(f)
                assert data['cycle'] == '2025A'
                assert len(data['beds']) == 19
        else:
             print(f"[FAIL] Snapshot returned {snap_file} but file not found at {full_snap_path}")
             return
    else:
        print(f"[FAIL] Snapshot failed. Returned: {snap_file}")
        # Debug why
        conn = get_db()
        plans = conn.execute("SELECT * FROM cycle_plans").fetchall()
        print(f"Debug: {len(plans)} plans in DB")
        for p in plans[:5]:
            print(dict(p))
        conn.close()
        return

    # 5. Generate Next Cycle (2025B)
    print("Testing generate_next_cycle...")
    # Seed rotation sequence mapping
    # Feuille -> Graine -> Racine -> Fruit -> Couverture
    # Need to save to rotation_sequence table
    from database import save_rotation_sequence
    seq = ['Feuille', 'Graine', 'Racine', 'Fruit', 'Couverture']
    save_rotation_sequence(seq)
    
    new_cycle, err = generate_next_cycle(garden_id)
    if err:
        print(f"[FAIL] Generation failed: {err}")
        return
    
    print(f"[OK] Generated cycle: {new_cycle}")
    assert new_cycle == '2025B'

    # Check plans
    plans = get_cycle_plans_for_garden_cycle(garden_id, '2025B')
    assert len(plans) == 19
    
    # Check rotation:
    # Old 1-10 (Feuille) -> Should be Graine
    # Old 11-19 (Graine) -> Should be Racine
    
    feuille_success = True
    graine_success = True
    
    for p in plans:
        sid = p['sub_bed_id']
        expected = 'Graine' if sid <= 10 else 'Racine'
        if p['planned_category'] != expected:
            print(f"❌ Rotation error for sub_bed {sid}: expected {expected}, got {p['planned_category']}")
            if sid <= 10: feuille_success = False
            else: graine_success = False
            
    if feuille_success and graine_success:
        print("[OK] Category rotation correct")

    # 6. Verify Reserve Exclusion
    # Sub-bed 20 should not be in plans
    res_plan = next((p for p in plans if p['sub_bed_id'] == 20), None)
    if res_plan:
        print("[FAIL] Reserve bed 20 included in plans!")
    else:
        print("[OK] Reserve bed excluded")

    # 7. Test Smart Assignment (assign_crops)
    print("Testing assign_crops...")
    # Assign crops for 2025B
    # Category Graine (beds 1-10): defaults say Maïs 50%, Haricot 50% ? 
    # Actually checking internal logic:
    # We didn't set distribution profiles, so assign_crops might fail or do nothing if profiles missing?
    # assign_crops requires distribution profiles OR defaults
    # Let's import save_distribution_profiles to set some targets
    from database import save_distribution_profiles
    
    # Target: 100% Maïs for Graine
    # Target: 100% Carotte for Racine
    save_distribution_profiles(garden_id, '2025B', [
        (crop_ids['Maïs'], 100),
        (crop_ids['Carotte'], 100)
    ])
    
    ok, msg = assign_crops(garden_id, '2025B')
    if not ok:
        print(f"[FAIL] Assignment failed: {msg}")
    else:
        print("[OK] Assignment successful")
        
    # Verify assignments
    plans = get_cycle_plans_for_garden_cycle(garden_id, '2025B')
    assigned_count = 0
    for p in plans:
        if p['planned_crop_id']:
            assigned_count += 1
            
    print(f"[OK] Assigned crops to {assigned_count}/19 beds")
    assert assigned_count == 19

    # Clean up
    conn = get_db()
    conn.close()
    os.remove(TEST_DB)
    # Remove snapshot?
    
    print("\n=== Verification Complete ===")

if __name__ == '__main__':
    verify_rotation()
