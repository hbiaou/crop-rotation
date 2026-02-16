import requests
import re
import sys

BASE_URL = "http://localhost:5000"

def get_csrf_token(session):
    """Fetch CSRF token from the settings page."""
    response = session.get(f"{BASE_URL}/settings/")
    if response.status_code != 200:
        print(f"Failed to fetch settings page. Status: {response.status_code}")
        return None
    
    # Extract CSRF token using regex
    match = re.search(r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', response.text)
    if match:
        return match.group(1)
    
    # Try searching for meta tag as fallback (if implemented)
    match = re.search(r'<meta name="csrf-token" content="([^"]+)">', response.text)
    if match:
        return match.group(1)
        
    print("Could not find CSRF token in response.")
    return None

def test_csrf_protection():
    session = requests.Session()
    
    print("1. Testing POST without CSRF token (Expect 400)...")
    # Using a garden ID that likely exists or doesn't matter for CSRF check
    # We just want to see the CSRF rejection
    response = session.post(f"{BASE_URL}/settings/garden/delete", data={'garden_id': 1})
    
    if response.status_code == 400:
        print("PASS: Request rejected with 400 Bad Request (CSRF missing).")
    else:
        print(f"FAIL: Expected 400, got {response.status_code}")
        print(f"Headers: {response.headers}")
        return False

    print("\n2. Testing POST with valid CSRF token...")
    token = get_csrf_token(session)
    if not token:
        print("FAIL: Could not retrieve CSRF token.")
        return False
    
    print(f"Got CSRF token: {token[:10]}...")
    
    # Attempt a safe operation (or one that fails gracefully)
    # We don't actually want to delete garden 1 if it's important.
    # Let's try adding a crop with invalid data or just verifying we get past the CSRF check.
    # If we get 200, 302, or 404 (garden not found) or even 500 (app error), it means CSRF passed.
    # If we get 400 again, CSRF failed.
    
    # Let's try to add a crop with a missing field, which should trigger validation error (200 with error message) or redirect.
    response = session.post(
        f"{BASE_URL}/settings/crop/add", 
        data={'csrf_token': token, 'crop_name': 'CSRF_TEST_CROP', 'category': 'Feuille'}
    )
    
    if response.status_code in [200, 302]:
        print(f"PASS: Request accepted (Status: {response.status_code}). CSRF token valid.")
        
        # Cleanup if it succeeded
        # Not easy to cleanup without ID, but crop name is distinct.
        # Ideally we check if it was added.
    elif response.status_code == 400:
        # Check if it's CSRF error or validation error
        if "The CSRF token is missing" in response.text or "The CSRF token is invalid" in response.text:
             print(f"FAIL: CSRF token rejected. Status: {response.status_code}")
             return False
        else:
             print(f"PASS: CSRF token accepted, but request failed validation (Status: 400).")
    else:
        print(f"PASS: CSRF token accepted (Status: {response.status_code}).")

    return True

if __name__ == "__main__":
    try:
        success = test_csrf_protection()
        if not success:
            sys.exit(1)
        print("\nCSRF Verification Successful!")
    except requests.exceptions.ConnectionError:
        print("\nERROR: Could not connect to localhost:5000. Is the server running?")
        sys.exit(1)
