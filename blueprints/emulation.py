import json
import base64
import os
import sqlite3
from flask import Blueprint, render_template, abort, url_for, current_app, flash, redirect

emulation_bp = Blueprint('emulation', __name__)

def get_db_connection():
    conn = sqlite3.connect(current_app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

@emulation_bp.route('/play_web_emulator/<int:game_id>')
def play_web_emulator(game_id):
    conn = get_db_connection()
    game = conn.execute('''
        SELECT 
            g.id, g.title, g.filepath, g.original_filename, g.system,
            s.emulator_core, s.aspect_ratio
        FROM games g
        JOIN systems s ON g.system = s.name
        WHERE g.id = ?
    ''', (game_id,)).fetchone()
    conn.close()

    if not game:
        abort(404)

    # --- FIX: Use _get_rom_paths_for_serving to get the correct filename to serve ---
    game_obj, _, _, filename_to_serve, _, is_web_playable = _get_rom_paths_for_serving(game_id)

    if not is_web_playable or not filename_to_serve:
        flash(f"Web emulation not available for this game. Ensure it's an unzipped, supported ROM file.", 'error')
        return redirect(url_for('library.game_detail', game_id=game_id))

    # --- FIX: Generate the rom_url using the dedicated 'web_rom_file' endpoint from run.py ---
    # This is the correct and secure way to serve the game file to the emulator.
    # It uses the route defined in run.py: @app.route('/roms/web/<int:game_id>/<string:filename>')
    rom_url = url_for('web_rom_file', game_id=game_id, filename=filename_to_serve, _external=True)
    
    game_details_for_js = {
        'id': game['id'],
        'title': game['title'],
        'system': game['system'],
        'rom_url': rom_url, # Pass the correct, secure URL to the template
        'emulator_core': game['emulator_core'],
        'emulator_aspect_ratio': game['aspect_ratio']
    }

    encoded_game_details = base64.b64encode(json.dumps(game_details_for_js).encode('utf-8')).decode('utf-8')

    return render_template('web_emulator.html',
                           game=game,
                           encoded_game_details=encoded_game_details)

@emulation_bp.route('/launch_game/<int:game_id>')
def launch_game(game_id):
    flash(f"Attempting to launch game {game_id} with desktop emulator (functionality not fully implemented).", 'info')
    return redirect(url_for('library.game_detail', game_id=game_id))

def _get_rom_paths_for_serving(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    conn.close()

    if not game:
        return None, None, None, None, None, False

    filepath = game['filepath']
    original_filename = game['original_filename']
    actual_file_to_serve = None
    is_web_playable = False
    filename_to_serve = None

    if os.path.isdir(filepath):
        found_rom = None
        common_rom_extensions = [
            '.nes', '.sfc', '.smc', '.gb', '.gbc', '.gba', '.n64', '.z64', '.v64',
            '.gen', '.md', '.sms', '.gg', '.ps1', '.iso', '.cue', '.chd', '.gdi', '.cdi'
        ]
        
        for ext in common_rom_extensions:
            for root, _, files in os.walk(filepath):
                for fname in files:
                    if os.path.splitext(fname)[1].lower() == ext:
                        found_rom = os.path.join(root, fname)
                        break
                if found_rom: break
        
        if found_rom:
            actual_file_to_serve = found_rom
            filename_to_serve = os.path.basename(found_rom)
            is_web_playable = True
        else:
            current_app.logger.warning(f"Could not find a suitable ROM file within directory {filepath} for game ID {game_id}")
            is_web_playable = False

    elif os.path.isfile(filepath):
        if filepath.lower().endswith('.zip'):
            current_app.logger.warning(f"Game ID {game_id}: Attempting to serve a .zip file for web emulation, which is not directly supported.")
            is_web_playable = False
            actual_file_to_serve = filepath
            filename_to_serve = os.path.basename(filepath)
        else:
            actual_file_to_serve = filepath
            filename_to_serve = os.path.basename(filepath)
            is_web_playable = True
    else:
        current_app.logger.error(f"Game ID {game_id}: Filepath {filepath} is neither a file nor a directory.")
        is_web_playable = False

    if not actual_file_to_serve:
        return game, None, None, None, original_filename, False

    directory_to_serve_from = os.path.dirname(actual_file_to_serve)
    
    if not os.path.commonpath([actual_file_to_serve, current_app.config['UPLOAD_FOLDER']]) == current_app.config['UPLOAD_FOLDER']:
        current_app.logger.error(f"Attempted to serve file outside UPLOAD_FOLDER: {directory_to_serve_from}")
        return game, None, None, None, original_filename, False

    return game, actual_file_to_serve, directory_to_serve_from, filename_to_serve, original_filename, is_web_playable
