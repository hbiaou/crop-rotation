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

from database import init_db, seed_defaults
from routes.main import main_bp
from routes.cycle import cycle_bp
from routes.distribution import distribution_bp
from routes.settings import settings_bp
from routes.export import export_bp


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.secret_key = 'crop-rotation-local-app-secret-key'

    # Ensure data and backup directories exist
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(base_dir, 'data'), exist_ok=True)
    os.makedirs(os.path.join(base_dir, 'backups'), exist_ok=True)
    os.makedirs(os.path.join(base_dir, 'history'), exist_ok=True)

    # Initialize database and seed defaults
    init_db()
    seed_defaults()

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(cycle_bp)
    app.register_blueprint(distribution_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(export_bp)

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
    app.run(host='localhost', port=5000, debug=True)
