import os
import json
import database
# Patch DB_PATH to use a test database
database.DB_PATH = os.path.join(os.getcwd(), 'verify_defaults.db')

from app import create_app  # noqa: E402
from database import get_db  # noqa: E402
from routes.settings import get_setting  # noqa: E402
from routes.distribution import _load_default_distribution  # noqa: E402

# Setup
db_path = os.path.join(os.getcwd(), 'verify_defaults.db')
if os.path.exists(db_path):
    os.remove(db_path)

app = create_app()
app.config['DATABASE'] = db_path
app.config['TESTING'] = True
app.config['SECRET_KEY'] = 'test' # Needed for flash

def run_test():
    # Debug
    print(f"Using DB: {database.DB_PATH}")
    conn = get_db()
    
    crops = conn.execute("SELECT id, crop_name FROM crops").fetchall()
    print("All crops:")
    for c in crops:
        print(f"{c['id']}: {c['crop_name']}")
    
    count = len(crops)
    print(f"Crop count: {count}")
    
    laitue = conn.execute("SELECT id FROM crops WHERE crop_name='Laitue'").fetchone()
    # Epinard is not in seed_defaults, use Choux
    choux = conn.execute("SELECT id FROM crops WHERE crop_name='Choux'").fetchone()
    
    if not laitue or not choux:
        print("FAILURE: Seed data missing Laitue or Choux")
        conn.close()
        return
        
    laitue_id = laitue[0]
    choux_id = choux[0]
    conn.close()
        
    print("--- Testing POST /settings/distribution/save ---")
    client = app.test_client()
    # Post data
    form_data = {
        f'crop_{laitue_id}': '80',
        f'crop_{choux_id}': '20'
    }
    resp = client.post('/settings/distribution/save', data=form_data, follow_redirects=True)
    if resp.status_code != 200:
        print(f"FAILURE: POST failed {resp.status_code}")
        return
        
    # Verify DB
    defaults_json = get_setting('distribution_defaults')
    print(f"DB Content: {defaults_json}")
    defaults = json.loads(defaults_json)
    
    if defaults.get('Feuille', {}).get('Laitue') != 80.0:
        print("FAILURE: Laitue default not 80.0")
    if defaults.get('Feuille', {}).get('Choux') != 20.0:
        print("FAILURE: Choux default not 20.0")
        
    # Verify _load_default_distribution (for any garden code)
    loaded = _load_default_distribution('TG')
    print(f"Loaded Logic: {loaded}")
    
    if loaded.get('Feuille', {}).get('Laitue') != 80.0:
            print("FAILURE: _load_default_distribution logic failed.")
    else:
            print("SUCCESS: Defaults saved and loaded via logic.")

if __name__ == '__main__':
    run_test()
