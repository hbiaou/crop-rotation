from database import get_db, update_setting
import sqlite3

conn = get_db()
try:
    conn.execute("DELETE FROM settings WHERE key='distribution_defaults'")
    conn.commit()
    print("Cleaned up distribution_defaults.")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
