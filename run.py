import json
import base64
import os
import sqlite3
from datetime import datetime

from flask import Flask, flash, send_from_directory, request, jsonify, current_app, abort, url_for
from flask_cors import CORS

from config import Config
from utils import get_setting, set_setting 

from blueprints.library import library_bp
from blueprints.igdb import igdb_bp
from blueprints.settings import settings_bp
from blueprints.emulation import emulation_bp, _get_rom_paths_for_serving

basedir = os.path.abspath(os.path.dirname(__file__))

def create_app():
    app = Flask(__name__, template_folder=os.path.join(basedir, 'templates'))
    app.config.from_object(Config)

    # Securely configure CORS to only allow requests from your app's origin
    CORS(app, resources={r"/roms/web/*": {"origins": "http://127.0.0.1:5000"}})

    if not app.config['SECRET_KEY'] or app.config['SECRET_KEY'] == 'your_strong_unique_secret_key_here':
        print("CRITICAL WARNING: SECRET_KEY is not set or is default. Session-based features (like flash messages) will not be secure or may not work correctly.")
        print("Please update config.py with a strong, unique SECRET_KEY.")

    def init_db(app_instance):
        with app_instance.app_context():
            conn = sqlite3.connect(app_instance.config['DATABASE'])
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    system TEXT NOT NULL,
                    filepath TEXT NOT NULL UNIQUE,
                    cover_url TEXT,
                    last_played TEXT,
                    play_count INTEGER DEFAULT 0,
                    original_filename TEXT,
                    FOREIGN KEY (system) REFERENCES systems(name) ON DELETE CASCADE
                )
            ''')
            
            try:
                cursor.execute("SELECT original_filename FROM games LIMIT 1")
            except sqlite3.OperationalError:
                print("Adding 'original_filename' column to 'games' table...")
                cursor.execute("ALTER TABLE games ADD COLUMN original_filename TEXT")
                conn.commit()
                print("'original_filename' column added.")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS systems (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    emulator_core TEXT,
                    aspect_ratio TEXT
                )
            ''')
            
            try:
                cursor.execute("SELECT emulator_core FROM systems LIMIT 1")
            except sqlite3.OperationalError:
                print("Adding 'emulator_core' column to 'systems' table...")
                cursor.execute("ALTER TABLE systems ADD COLUMN emulator_core TEXT")
                conn.commit()
                print("'emulator_core' column added.")
            
            try:
                cursor.execute("SELECT aspect_ratio FROM systems LIMIT 1")
            except sqlite3.OperationalError:
                print("Adding 'aspect_ratio' column to 'systems' table...")
                cursor.execute("ALTER TABLE systems ADD COLUMN aspect_ratio TEXT")
                conn.commit()
                print("'aspect_ratio' column added.")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS emulator_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    system_name TEXT NOT NULL UNIQUE,
                    emulator_path TEXT NOT NULL,
                    FOREIGN KEY (system_name) REFERENCES systems(name) ON DELETE CASCADE
                )
            ''')
            
            # --- CONFIGURATION UPDATED ---
            # Using the core names for the files you were able to download.
            # Systems without available cores are set to None, which will disable the web player for them.
            systems_to_ensure = [
                ('Nintendo Entertainment System', 'nestopia', '8/7'),
                ('Super Nintendo', 'snes9x', '4/3'),
                ('Game Boy', 'gambatte', '10/9'),
                ('Game Boy Color', 'gambatte', '10/9'),
                ('Game Boy Advance', 'mgba', '3/2'),
                ('Sega Genesis', 'genesis_plus_gx', '4/3'),
                # Cores for the systems below were not found, so web emulation is disabled (set to None)
                ('Nintendo 64', None, '4/3'),
                ('Nintendo DS', None, '4/3'),
                ('PlayStation 1', None, '4/3'),
                ('Arcade', None, '4/3'),
                ('Other', None, None)
            ]

            for name, core, aspect in systems_to_ensure:
                cursor.execute('''
                    INSERT OR REPLACE INTO systems (name, emulator_core, aspect_ratio)
                    VALUES (?, ?, ?)
                ''', (name, core, aspect))
            
            conn.commit()
            conn.close()

    init_db(app)

    app.register_blueprint(library_bp)
    app.register_blueprint(igdb_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(emulation_bp)

    @app.route('/roms/download/<int:game_id>/<string:original_filename>')
    def download_rom_file(game_id, original_filename):
        game_obj, actual_file_to_serve, directory_to_serve_from, filename_to_serve, stored_original_filename, _ = _get_rom_paths_for_serving(game_id)
        
        if not actual_file_to_serve:
            abort(404)

        return send_from_directory(
            directory_to_serve_from,
            filename_to_serve,
            as_attachment=True,
            download_name=stored_original_filename or original_filename
        )

    @app.route('/roms/web/<int:game_id>/<string:filename>')
    def web_rom_file(game_id, filename):
        game_obj, actual_file_to_serve, directory_to_serve_from, filename_to_serve, stored_original_filename, _ = _get_rom_paths_for_serving(game_id)
        
        if not actual_file_to_serve or filename_to_serve != filename:
            current_app.logger.error(f"Attempted to serve incorrect ROM file: requested={filename}, actual={filename_to_serve} for game_id={game_id}")
            abort(404)

        if not os.path.commonpath([directory_to_serve_from, current_app.config['UPLOAD_FOLDER']]) == current_app.config['UPLOAD_FOLDER']:
            current_app.logger.error(f"Security alert: Attempted to serve file outside UPLOAD_FOLDER: {directory_to_serve_from}")
            abort(403)

        return send_from_directory(
            directory_to_serve_from,
            filename_to_serve,
        )

    @app.route('/api/systems', methods=['GET'])
    def get_systems():
        conn = sqlite3.connect(current_app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT name FROM systems ORDER BY name")
        systems = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return jsonify(systems)

    @app.route('/api/settings/update_emulator_path', methods=['POST'])
    def update_emulator_path():
        data = request.get_json()
        system_name = data.get('system_name')
        emulator_path = data.get('emulator_path')

        if not system_name or not emulator_path:
            return jsonify({"error": "Missing 'system_name' or 'emulator_path' in request body."}), 400

        emulator_paths = get_setting('emulator_paths', {})
        emulator_paths[system_name] = emulator_path
        set_setting('emulator_paths', emulator_paths)

        print(f"Updated emulator path for {system_name}: {emulator_path}")
        return jsonify({"message": f"Emulator path for '{system_name}' updated successfully."}), 200

    @app.route('/api/games/check_exists', methods=['GET'])
    def check_game_exists():
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
        game_data = request.get_json()
        title = game_data.get('title')
        system = game_data.get('system')
        filepath = game_data.get('filepath')
        cover_url = game_data.get('cover_url')
        original_filename = game_data.get('original_filename')

        if not all([title, system, filepath]):
            return jsonify({"error": "Missing 'title', 'system', or 'filepath' in request body."}), 400

        conn = sqlite3.connect(current_app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO games (title, system, filepath, cover_url, last_played, play_count, original_filename) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (title, system, filepath, cover_url, None, 0, original_filename)
            )
            conn.commit()
            print(f"Successfully added game: {title} ({system}) at {filepath} (Original: {original_filename})")
            return jsonify({"message": "Game added successfully.", "game_id": cursor.lastrowid}), 201
        except sqlite3.IntegrityError:
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
        print("Placeholder: Triggering server-side metadata/cover scan.")
        return jsonify({"message": "Server metadata scan triggered (placeholder functionality)."}), 200

    if not app.config['IGDB_CLIENT_ID'] or not app.config['IGDB_CLIENT_SECRET'] or \
       app.config['IGDB_CLIENT_ID'] == 'YOUR_IGDB_CLIENT_ID' or \
       app.config['IGDB_CLIENT_SECRET'] == 'YOUR_IGDB_CLIENT_SECRET':
        print("WARNING: IGDB Client ID or Client Secret is not set or default. IGDB features will not work.")
        print("Please register an application on Twitch Developers (dev.twitch.tv) to get your credentials.")
        print("Then update config.py with your Client ID and Client Secret.")
    else:
        pass

    @app.context_processor
    def inject_global_vars():
        return {
            'get_setting': get_setting,
            'themes': app.config['THEMES'],
            'datetime': datetime
        }

    return app

if __name__ == '__main__':
    app = create_app()
    
    with app.app_context():
        _ = get_setting('dummy_key_to_ensure_settings_file_exists', None) 

    app.run(debug=True)
