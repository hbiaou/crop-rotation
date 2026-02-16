import pytest
from app import create_app
import os
import tempfile

@pytest.fixture
def client():
    # Create a temporary file to isolate the database for each test session
    db_fd, db_path = tempfile.mkstemp()
    
    # Configure app for testing
    app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'SECRET_KEY': 'dev-key-for-testing'
    })

    with app.test_client() as client:
        with app.app_context():
            from database import init_db
            init_db()
        yield client

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)

def test_homepage_loads(client):
    """Test that the homepage loads successfully."""
    rv = client.get('/')
    assert rv.status_code == 200
    # Check for some expected content (e.g., partial text from the page)
    # The homepage usually contains "Crop Rotation" or specific navigation items
    # Adjust assertion based on actual content
    assert b'DOCTYPE html' in rv.data

def test_static_assets(client):
    """Test that static assets like CSS are accessible."""
    rv = client.get('/static/style.css')
    assert rv.status_code == 200

def test_settings_page(client):
    """Test that the settings page loads."""
    rv = client.get('/settings/')
    assert rv.status_code == 200
