import os
import sqlite3
from datetime import datetime
from flask import Flask, flash, send_from_directory, request, jsonify, current_app, abort, url_for
from flask_cors import CORS

from config import Config
from utils import get_setting, set_setting 

from blueprints.navigation import navigation_bp
from blueprints.library import library_bp
from blueprints.igdb import igdb_bp
from blueprints.settings import settings_bp
from blueprints.emulation import emulation_bp, _get_rom_paths_for_serving
from blueprints.fileman import fileman_bp

basedir = os.path.abspath(os.path.dirname(__file__))

def create_app():
    app = Flask(__name__, template_folder=os.path.join(basedir, 'templates'))
    app.config.from_object(Config)
    CORS(app, resources={r"/roms/web/*": {"origins": "http://127.0.0.1:5000"}})

    def init_db(app_instance):
        with app_instance.app_context():
            conn = sqlite3.connect(app_instance.config['DATABASE'])
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # --- Final 'games' table with ALL columns ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    system TEXT NOT NULL,
                    filepath TEXT NOT NULL UNIQUE,
                    cover_image_path TEXT,
                    genre TEXT,
                    release_year INTEGER,
                    developer TEXT,
                    publisher TEXT,
                    description TEXT,
                    play_status TEXT DEFAULT 'Not Played',
                    last_played TEXT,
                    play_count INTEGER DEFAULT 0,
                    original_filename TEXT,
                    FOREIGN KEY (system) REFERENCES systems(name) ON DELETE CASCADE
                )
            ''')
            
            # --- Check for new and missing columns and add them ---
            columns = [
                ("play_status", "TEXT DEFAULT 'Not Played'"), ("description", "TEXT"), ("publisher", "TEXT"),
                ("developer", "TEXT"), ("release_year", "INTEGER"), ("genre", "TEXT"),
                ("original_filename", "TEXT"), ("cover_image_path", "TEXT")
            ]
            for col, col_type in columns:
                try:
                    cursor.execute(f"SELECT {col} FROM games LIMIT 1")
                except sqlite3.OperationalError:
                    print(f"Adding '{col}' column to 'games' table...")
                    cursor.execute(f"ALTER TABLE games ADD COLUMN {col} {col_type}")
                    conn.commit()
                    print(f"'{col}' column added.")
            
            # Remove the old 'cover_url' column if it exists to prevent confusion
            try:
                cursor.execute("ALTER TABLE games DROP COLUMN cover_url")
                conn.commit()
                print("Old 'cover_url' column removed.")
            except sqlite3.OperationalError:
                pass
            
            # Create systems table with the new image_path column
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS systems (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    emulator_core TEXT,
                    aspect_ratio TEXT,
                    image_path TEXT
                )''')

            # Add image_path column if it doesn't exist
            try:
                cursor.execute("SELECT image_path FROM systems LIMIT 1")
            except sqlite3.OperationalError:
                print("Adding 'image_path' column to 'systems' table...")
                cursor.execute("ALTER TABLE systems ADD COLUMN image_path TEXT")
                conn.commit()
                print("'image_path' column added.")

            # Create emulator_configs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS emulator_configs (
                    emulator_name TEXT PRIMARY KEY,
                    emulator_path TEXT,
                    install_type TEXT
                )''')
            
            # This is your mapping of systems to image files
            systems_to_ensure = [
                ('Nintendo Entertainment System', 'nestopia', '8/7', 'nes.png'),
                ('Super Nintendo', 'snes9x', '4/3', 'snes.png'),
                ('Game Boy', 'gambatte', '10/9', 'gb.png'),
                ('Game Boy Color', 'gambatte', '10/9', 'gbc.png'),
                ('Game Boy Advance', 'mgba', '3/2', 'gba.png'),
                ('Sega Genesis', 'genesis_plus_gx', '4/3', 'sg.png'),
                ('Sega Master Drive', None, '4/3', 'smd.png'),
                ('Sega Saturn', None, '4/3', 'ss.png'),
                ('Sega Dreamcast', None, '4/3', 'sdc.png'),
                ('Nintendo 64', None, '4/3', 'n64.png'),
                ('Nintendo DS', None, '4/3', 'nds.png'),
                ('Nintendo Wii', None, '4/3', 'wii.png'),
                ('Nintendo GameCube', None, '4/3', 'ngc.png'),
                ('PlayStation 1', None, '4/3', 'ps1.png'),
                ('PlayStation 2', None, '4/3', 'ps2.png'),
                ('PlayStation 3', None, '4/3', 'ps4.png'),
                ('PlayStation Portable', None, '4/3', 'psp.png'),
                ('Xbox', None, '4/3', 'xbox.png'),
                ('Xbox 360', None, '4/3', '360.png'),
                ('Xbox One', None, '4/3', 'xb1.png'),
                ('Nintendo 3DS', None, '4/3', '3ds.png'),
                ('Arcade', None, '4/3', None),
                ('Other', None, None, None)
            ]
            
            for name, core, aspect, img_path in systems_to_ensure:
                cursor.execute('INSERT OR IGNORE INTO systems (name, emulator_core, aspect_ratio, image_path) VALUES (?, ?, ?, ?)', (name, core, aspect, img_path))
            conn.commit()
            conn.close()

    init_db(app)

    # Register blueprints with proper URL prefixes
    app.register_blueprint(navigation_bp)
    app.register_blueprint(library_bp, url_prefix='/game')
    app.register_blueprint(igdb_bp, url_prefix='/igdb')
    app.register_blueprint(settings_bp)
    app.register_blueprint(emulation_bp, url_prefix='/emulation')
    app.register_blueprint(fileman_bp, url_prefix='/files')

    # Add the web ROM serving route
    @app.route('/roms/web/<int:game_id>/<string:filename>')
    def web_rom_file(game_id, filename):
        """
        Serves ROM files for web emulation with proper security checks.
        """
        try:
            game_obj, actual_file_to_serve, directory_to_serve_from, filename_to_serve, original_filename, is_web_playable = _get_rom_paths_for_serving(game_id)
            
            if not game_obj:
                current_app.logger.error(f"Game ID {game_id} not found")
                abort(404)
            
            if not is_web_playable:
                current_app.logger.error(f"Game ID {game_id} is not web playable")
                abort(403)
            
            if not filename_to_serve or filename_to_serve != filename:
                current_app.logger.error(f"Filename mismatch for game ID {game_id}: expected {filename_to_serve}, got {filename}")
                abort(404)
            
            if not actual_file_to_serve or not os.path.exists(actual_file_to_serve):
                current_app.logger.error(f"ROM file not found: {actual_file_to_serve}")
                abort(404)
            
            if not os.path.commonpath([actual_file_to_serve, current_app.config['UPLOAD_FOLDER']]) == current_app.config['UPLOAD_FOLDER']:
                current_app.logger.error(f"Security violation: attempted to serve file outside upload folder: {actual_file_to_serve}")
                abort(403)
            
            current_app.logger.info(f"Serving ROM file for game ID {game_id}: {actual_file_to_serve}")
            
            return send_from_directory(
                directory_to_serve_from,
                os.path.basename(actual_file_to_serve),
                as_attachment=False,
                mimetype='application/octet-stream'
            )
            
        except Exception as e:
            current_app.logger.error(f"Error serving ROM file for game ID {game_id}: {e}")
            abort(500)

    @app.context_processor
    def inject_global_vars():
        return {'get_setting': get_setting, 'themes': app.config.get('THEMES', []), 'datetime': datetime}
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)