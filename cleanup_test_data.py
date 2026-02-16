from database import get_db

conn = get_db()
try:
    conn.execute("DELETE FROM settings WHERE key='distribution_defaults'")
    conn.commit()
    print("Cleaned up distribution_defaults.")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
