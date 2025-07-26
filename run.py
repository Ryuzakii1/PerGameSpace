import os
import sqlite3
from datetime import datetime

from flask import Flask, flash, send_from_directory # <--- ADDED send_from_directory HERE

from config import Config
from utils import get_setting, set_setting

from blueprints.library import library_bp
from blueprints.igdb import igdb_bp
from blueprints.settings import settings_bp

# Get the base directory of the application
basedir = os.path.abspath(os.path.dirname(__file__))

# --- Application Factory Function ---
def create_app():
    # Explicitly tell Flask where to find templates
    app = Flask(__name__, template_folder=os.path.join(basedir, 'templates'))
    
    # Load configuration from Config class
    app.config.from_object(Config)

    # Ensure the SECRET_KEY is set for session management (flash messages)
    if not app.config['SECRET_KEY'] or app.config['SECRET_KEY'] == 'your_strong_unique_secret_key_here':
        print("CRITICAL WARNING: SECRET_KEY is not set or is default. Session-based features (like flash messages) will not be secure or may not work correctly.")
        print("Please update config.py with a strong, unique SECRET_KEY.")

    # --- Database Initialization ---
    def init_db(app_instance):
        with app_instance.app_context():
            conn = sqlite3.connect(app_instance.config['DATABASE'])
            conn.row_factory = sqlite3.Row
            conn.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    system TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    cover_url TEXT,
                    last_played TEXT,
                    play_count INTEGER DEFAULT 0
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS systems (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                )
            ''')
            conn.commit()
            conn.close()

    init_db(app) # Call init_db during app creation

    # --- Register Blueprints ---
    app.register_blueprint(library_bp)
    app.register_blueprint(igdb_bp)
    app.register_blueprint(settings_bp)

    # --- NEW: Configure Flask to serve the UPLOAD_FOLDER contents as static files ---
    # This makes files in UPLOAD_FOLDER accessible via /roms/<filename> URL
    # We use app.add_url_rule and a separate route function for security and clarity
    app.add_url_rule(
        '/roms/<path:filename>',
        endpoint='roms_file', # A unique name for this endpoint
        build_only=True,     # Means it won't be automatically registered as a route
    )

    @app.route('/roms/<path:filename>')
    def serve_rom(filename):
        # send_from_directory safely serves files from a specified directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    # --- END NEW ---

    # --- Initial Checks/Setup (e.g., IGDB token check) ---
    # These print to console, not flash, as no request context exists yet.
    if not app.config['IGDB_CLIENT_ID'] or not app.config['IGDB_CLIENT_SECRET'] or \
       app.config['IGDB_CLIENT_ID'] == 'YOUR_IGDB_CLIENT_ID' or \
       app.config['IGDB_CLIENT_SECRET'] == 'YOUR_IGDB_CLIENT_SECRET':
        print("WARNING: IGDB Client ID or Client Secret is not set or default. IGDB features will not work.")
        print("Please register an application on Twitch Developers (dev.twitch.tv) to get your credentials.")
        print("Then update config.py with your Client ID and Client Secret.")
    else:
        pass

    # --- Context Processors (for global variables in templates) ---
    @app.context_processor
    def inject_global_vars():
        return {
            'get_setting': get_setting,
            'themes': app.config['THEMES'],
            'datetime': datetime
        }

    return app

# --- How to Run Your Application ---
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True) # Run in debug mode for development