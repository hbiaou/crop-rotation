"""
app.py — Flask entry point for the crop rotation application.

Initializes the Flask app, registers all route blueprints,
calls init_db() and seed_defaults() on startup, and injects
i18n strings into template context.

Run: python app.py → localhost:5000
"""

import os
import json
from flask import Flask
from flask_wtf.csrf import CSRFProtect

from database import init_db, seed_defaults
from plant_database import init_plant_db
from routes.main import main_bp
from routes.cycle import cycle_bp
from routes.distribution import distribution_bp
from routes.settings import settings_bp
from routes.export import export_bp
from routes.plant_db import plant_db_bp


def create_app(test_config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.secret_key = 'crop-rotation-local-app-secret-key'
    app.config['WTF_CSRF_CHECK_DEFAULT'] = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    if test_config:
        app.config.update(test_config)

    csrf = CSRFProtect(app)

    # Ensure data and backup directories exist
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(base_dir, 'data'), exist_ok=True)
    os.makedirs(os.path.join(base_dir, 'backups'), exist_ok=True)
    os.makedirs(os.path.join(base_dir, 'history'), exist_ok=True)

    # Initialize database and seed defaults
    with app.app_context():
        init_db()
        seed_defaults()
        # Initialize separate plant database
        try:
            init_plant_db()
        except Exception as e:
            print(f"Warning: Could not initialize plant database: {e}")

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(cycle_bp)
    app.register_blueprint(distribution_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(plant_db_bp)

    # Load i18n strings
    i18n_path = os.path.join(base_dir, 'i18n', 'fr.json')
    with open(i18n_path, 'r', encoding='utf-8') as f:
        i18n = json.load(f)

    @app.context_processor
    def inject_i18n():
        """Inject French UI strings into all templates."""
        return {'i18n': i18n}

    return app


if __name__ == '__main__':
    app = create_app()
    # Debug mode: enabled by default for development (auto-reload on file changes)
    # Set FLASK_DEBUG=0 to disable for production
    debug = os.environ.get('FLASK_DEBUG', '1') != '0'
    app.run(host='localhost', port=5000, debug=debug)
