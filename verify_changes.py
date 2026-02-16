
from database import get_db, create_garden, delete_cycle_plans

def verify_family_column():
    print("Verifying 'family' column in 'crops' table...")
    conn = get_db()
    cursor = conn.cursor()
    try:
        columns = [i[1] for i in cursor.execute("PRAGMA table_info(crops)").fetchall()]
        if 'family' in columns:
            print("PASS: 'family' column exists.")
        else:
            print("FAIL: 'family' column missing.")
    except Exception as e:
        print(f"FAIL: Error checking column: {e}")
    finally:
        conn.close()

def verify_cycle_deletion():
    print("\nVerifying specific cycle deletion...")
    conn = get_db()
    
    # Setup test data
    garden_code = "TEST_G"
    name = "Test Garden"
    beds = 1
    length = 10
    width = 1
    sub_beds = 1
    
    try:
        # Create garden using helper (handles sub-beds and columns)
        # create_garden(garden_code, name, beds, bed_length_m, bed_width_m, sub_beds_per_bed)
        garden_id = create_garden(garden_code, name, beds, length, width, sub_beds)
        if not garden_id:
             print("FAIL: create_garden returned None")
             return
             
        # Get sub_bed_id
        sub_bed_id = conn.execute("SELECT id FROM sub_beds WHERE garden_id = ?", (garden_id,)).fetchone()[0]
        
        # Create plans for 2025A and 2025B
        conn.execute("INSERT INTO cycle_plans (sub_bed_id, garden_id, cycle, planned_category) VALUES (?, ?, ?, ?)", (sub_bed_id, garden_id, "2025A", "Feuille"))
        conn.execute("INSERT INTO cycle_plans (sub_bed_id, garden_id, cycle, planned_category) VALUES (?, ?, ?, ?)", (sub_bed_id, garden_id, "2025B", "Racine"))
        conn.commit()
        
        # Verify both exist
        count_a = conn.execute("SELECT COUNT(*) FROM cycle_plans WHERE garden_id = ? AND cycle = ?", (garden_id, "2025A")).fetchone()[0]
        count_b = conn.execute("SELECT COUNT(*) FROM cycle_plans WHERE garden_id = ? AND cycle = ?", (garden_id, "2025B")).fetchone()[0]
        
        if count_a == 1 and count_b == 1:
            print("PASS: Test cycles created.")
        else:
            print(f"FAIL: Test cycles creation failed. 2025A: {count_a}, 2025B: {count_b}")
            return

        # Delete 2025B
        print("Deleting cycle 2025B...")
        delete_cycle_plans(garden_id, "2025B")
        
        # Verify 2025A remains, 2025B gone
        count_a_after = conn.execute("SELECT COUNT(*) FROM cycle_plans WHERE garden_id = ? AND cycle = ?", (garden_id, "2025A")).fetchone()[0]
        count_b_after = conn.execute("SELECT COUNT(*) FROM cycle_plans WHERE garden_id = ? AND cycle = ?", (garden_id, "2025B")).fetchone()[0]
        
        if count_a_after == 1 and count_b_after == 0:
            print("PASS: Cycle 2025B deleted, 2025A preserved.")
        else:
            print(f"FAIL: Deletion verification failed. 2025A: {count_a_after}, 2025B: {count_b_after}")

    except Exception as e:
        print(f"FAIL: Error during test: {e}")
    finally:
        # Cleanup
        try:
            conn.execute("DELETE FROM gardens WHERE id = ?", (garden_id,))
            conn.execute("DELETE FROM sub_beds WHERE garden_id = ?", (garden_id,))
            conn.execute("DELETE FROM cycle_plans WHERE garden_id = ?", (garden_id,))
            conn.commit()
        except Exception:
            pass
        conn.close()

if __name__ == "__main__":
    verify_family_column()
    verify_cycle_deletion()
