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
                    cover_url TEXT,
                    genre TEXT,
                    release_year INTEGER,
                    developer TEXT,
                    publisher TEXT,
                    description TEXT,
                    play_status TEXT, -- Added play_status column
                    last_played TEXT,
                    play_count INTEGER DEFAULT 0,
                    original_filename TEXT,
                    FOREIGN KEY (system) REFERENCES systems(name) ON DELETE CASCADE
                )
            ''')
            
            # --- Check for all new columns ---
            columns = [
                ("play_status", "TEXT"), ("description", "TEXT"), ("publisher", "TEXT"),
                ("developer", "TEXT"), ("release_year", "INTEGER"), ("genre", "TEXT"),
                ("original_filename", "TEXT")
            ]
            for col, col_type in columns:
                try:
                    cursor.execute(f"SELECT {col} FROM games LIMIT 1")
                except sqlite3.OperationalError:
                    print(f"Adding '{col}' column to 'games' table...")
                    cursor.execute(f"ALTER TABLE games ADD COLUMN {col} {col_type}")
                    conn.commit()
                    print(f"'{col}' column added.")
            
            # (The rest of the init_db function is unchanged)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS systems (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                    emulator_core TEXT, aspect_ratio TEXT
                )''')
            systems_to_ensure = [
                ('Nintendo Entertainment System', 'nestopia', '8/7'), ('Super Nintendo', 'snes9x', '4/3'),
                ('Game Boy', 'gambatte', '10/9'), ('Game Boy Color', 'gambatte', '10/9'),
                ('Game Boy Advance', 'mgba', '3/2'), ('Sega Genesis', 'genesis_plus_gx', '4/3'),
                ('Nintendo 64', None, '4/3'), ('Nintendo DS', None, '4/3'),
                ('PlayStation 1', None, '4/3'), ('Arcade', None, '4/3'), ('Other', None, None)
            ]
            for name, core, aspect in systems_to_ensure:
                cursor.execute('INSERT OR IGNORE INTO systems (name, emulator_core, aspect_ratio) VALUES (?, ?, ?)', (name, core, aspect))
            conn.commit()
            conn.close()

    init_db(app)

    app.register_blueprint(navigation_bp)
    app.register_blueprint(library_bp, url_prefix='/game')
    app.register_blueprint(igdb_bp, url_prefix='/igdb')
    app.register_blueprint(settings_bp)
    app.register_blueprint(emulation_bp, url_prefix='/emulation')

    @app.context_processor
    def inject_global_vars():
        return {'get_setting': get_setting, 'themes': app.config.get('THEMES', []), 'datetime': datetime}
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)