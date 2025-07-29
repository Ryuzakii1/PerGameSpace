import os
import sqlite3
import json 
from datetime import datetime

from flask import Flask, flash, send_from_directory, request, jsonify, current_app

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
    if not app.config['SECRET_KEY'] or app.config['SECRET_KEY'] == 'your_secret_key_here':
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
                    filepath TEXT NOT NULL UNIQUE,
                    cover_url TEXT,
                    last_played TEXT,
                    play_count INTEGER DEFAULT 0,
                    FOREIGN KEY (system) REFERENCES systems(name) ON DELETE CASCADE
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS systems (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS emulator_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    system_name TEXT NOT NULL UNIQUE,
                    emulator_path TEXT NOT NULL,
                    FOREIGN KEY (system_name) REFERENCES systems(name) ON DELETE CASCADE
                )
            ''')
            # Optional: Add some initial systems if they don't exist
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Nintendo Entertainment System')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Super Nintendo')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Game Boy')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Game Boy Color')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Game Boy Advance')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Nintendo 64')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Sega Genesis')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Nintendo DS')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('PlayStation 1')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Arcade')")
            conn.execute("INSERT OR IGNORE INTO systems (name) VALUES ('Other')") # Generic category
            conn.commit()
            conn.close()

    init_db(app) # Call init_db during app creation

    # --- Register Blueprints ---
    app.register_blueprint(library_bp)
    app.register_blueprint(igdb_bp)
    app.register_blueprint(settings_bp)

    # --- Configure Flask to serve the UPLOAD_FOLDER contents as static files ---
    app.add_url_rule(
        '/roms/<path:filename>',
        endpoint='roms_file',
        build_only=True,
    )

    @app.route('/roms/<path:filename>')
    def serve_rom(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # --- API Endpoints for Desktop Scanner GUI ---

    @app.route('/api/systems', methods=['GET'])
    def get_systems():
        """
        Returns a list of supported game systems from the database.
        This is crucial for the scanner_gui.py to populate its system dropdowns.
        """
        conn = sqlite3.connect(current_app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT name FROM systems ORDER BY name")
        systems = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return jsonify(systems)

    @app.route('/api/settings/update_emulator_path', methods=['POST'])
    def update_emulator_path():
        """
        Receives a system name and an emulator path from the desktop GUI
        and saves it to the settings.json file using existing utility functions.
        """
        data = request.get_json()
        system_name = data.get('system_name')
        emulator_path = data.get('emulator_path')

        if not system_name or not emulator_path:
            return jsonify({"error": "Missing 'system_name' or 'emulator_path' in request body."}), 400

        # Retrieve current emulator paths, defaulting to an empty dict if not set
        # Ensure the default is an empty dictionary if 'emulator_paths' is not found
        emulator_paths = get_setting('emulator_paths', {})
        
        # Update the specific emulator path
        emulator_paths[system_name] = emulator_path
        
        # Save the updated emulator paths back to settings.json
        set_setting('emulator_paths', emulator_paths)

        print(f"Updated emulator path for {system_name}: {emulator_path}")
        return jsonify({"message": f"Emulator path for '{system_name}' updated successfully."}), 200

    @app.route('/api/games/check_exists', methods=['GET'])
    def check_game_exists():
        """
        Checks if a game with the given file_path already exists in the database.
        """
        file_path = request.args.get('file_path')
        if not file_path:
            return jsonify({"error": "Missing 'file_path' parameter."}), 400

        conn = sqlite3.connect(current_app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT id FROM games WHERE filepath = ?", (file_path,))
        game = cursor.fetchone()
        conn.close()

        exists = game is not None
        print(f"Checking existence for {file_path}: {'Exists' if exists else 'Does not exist'}")
        return jsonify({"exists": exists}), 200

    @app.route('/api/games', methods=['POST'])
    def add_game():
        """
        Adds a new game to the database.
        Expected JSON data: {title, system, filepath, cover_url (optional)}
        """
        game_data = request.get_json()
        title = game_data.get('title')
        system = game_data.get('system')
        filepath = game_data.get('filepath')
        cover_url = game_data.get('cover_url') # This can be None

        if not all([title, system, filepath]):
            return jsonify({"error": "Missing 'title', 'system', or 'filepath' in request body."}), 400

        conn = sqlite3.connect(current_app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO games (title, system, filepath, cover_url, last_played, play_count) VALUES (?, ?, ?, ?, ?, ?)",
                (title, system, filepath, cover_url, None, 0) # last_played and play_count initialized
            )
            conn.commit()
            print(f"Successfully added game: {title} ({system}) at {filepath}")
            return jsonify({"message": "Game added successfully.", "game_id": cursor.lastrowid}), 201
        except sqlite3.IntegrityError:
            # This handles the UNIQUE constraint on filepath if a game is somehow added twice
            conn.rollback()
            return jsonify({"error": "Game with this filepath already exists."}), 409
        except Exception as e:
            conn.rollback()
            print(f"Error adding game: {e}")
            return jsonify({"error": f"Failed to add game: {str(e)}"}), 500
        finally:
            conn.close()

    @app.route('/scan_covers', methods=['GET'])
    def scan_covers():
        """Placeholder: Triggers a metadata/cover scan on the server."""
        print("Placeholder: Triggering server-side metadata/cover scan.")
        # In a real application, you might start a background task here
        # to fetch covers for newly added games or update existing ones.
        return jsonify({"message": "Server metadata scan triggered (placeholder functionality)."}), 200

    # --- Initial Checks/Setup (e.g., IGDB token check) ---
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
    
    # Ensure settings.json is initialized by utils.py if it doesn't exist
    with app.app_context():
        _ = get_setting('dummy_key_to_ensure_settings_file_exists', None) 

    app.run(debug=True) # Run in debug mode for development
