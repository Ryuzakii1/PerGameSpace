import json
import base64
import os
import sqlite3
from flask import Blueprint, render_template, abort, url_for, current_app, flash, redirect
from pathlib import Path

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

    # Check if the game is web playable and get the correct filename
    game_obj, actual_file_to_serve, directory_to_serve_from, filename_to_serve, original_filename, is_web_playable = _get_rom_paths_for_serving(game_id)

    if not is_web_playable or not filename_to_serve:
        flash(f"Web emulation not available for this game. Ensure it's an unzipped, supported ROM file.", 'error')
        return redirect(url_for('library.game_detail', game_id=game_id))

    # Generate the rom_url using the dedicated 'web_rom_file' endpoint
    rom_url = url_for('web_rom_file', game_id=game_id, filename=filename_to_serve, _external=True)
    
    game_details_for_js = {
        'id': game['id'],
        'title': game['title'],
        'system': game['system'],
        'rom_url': rom_url,
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
    """
    Enhanced ROM path detection for better web emulator support.
    Returns: (game_obj, actual_file_to_serve, directory_to_serve_from, filename_to_serve, original_filename, is_web_playable)
    """
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

    # Define supported ROM extensions for web emulation
    web_supported_extensions = {
        '.nes', '.sfc', '.smc', '.gb', '.gbc', '.gba', 
        '.gen', '.md', '.sms', '.gg', '.bin'
    }

    try:
        if os.path.isdir(filepath):
            # Search for ROM files in the directory
            current_app.logger.info(f"Searching for ROM files in directory: {filepath}")
            found_rom = None
            
            for root, _, files in os.walk(filepath):
                for fname in files:
                    file_ext = os.path.splitext(fname)[1].lower()
                    if file_ext in web_supported_extensions:
                        found_rom = os.path.join(root, fname)
                        current_app.logger.info(f"Found supported ROM: {found_rom}")
                        break
                if found_rom:
                    break
            
            if found_rom:
                actual_file_to_serve = found_rom
                filename_to_serve = os.path.basename(found_rom)
                is_web_playable = True
                current_app.logger.info(f"Directory scan successful - ROM: {filename_to_serve}")
            else:
                current_app.logger.warning(f"No supported ROM file found in directory {filepath}")
                is_web_playable = False

        elif os.path.isfile(filepath):
            file_ext = os.path.splitext(filepath)[1].lower()
            
            if file_ext == '.zip':
                current_app.logger.warning(f"Game ID {game_id}: ZIP files are not supported for web emulation")
                is_web_playable = False
                actual_file_to_serve = filepath
                filename_to_serve = os.path.basename(filepath)
            elif file_ext in web_supported_extensions:
                actual_file_to_serve = filepath
                filename_to_serve = os.path.basename(filepath)
                is_web_playable = True
                current_app.logger.info(f"Direct file is web playable: {filename_to_serve}")
            else:
                current_app.logger.warning(f"Unsupported file extension for web emulation: {file_ext}")
                actual_file_to_serve = filepath
                filename_to_serve = os.path.basename(filepath)
                is_web_playable = False
        else:
            current_app.logger.error(f"Game ID {game_id}: Filepath {filepath} does not exist")
            is_web_playable = False

    except Exception as e:
        current_app.logger.error(f"Error processing ROM path for game {game_id}: {e}")
        is_web_playable = False

    if not actual_file_to_serve:
        return game, None, None, None, original_filename, False

    # Security check: ensure file is within upload folder
    try:
        upload_folder_path = Path(current_app.config['UPLOAD_FOLDER']).resolve()
        actual_file_path = Path(actual_file_to_serve).resolve()
        
        if upload_folder_path not in actual_file_path.parents and upload_folder_path != actual_file_path.parent:
            current_app.logger.error(f"Security violation: File outside upload folder: {actual_file_to_serve}")
            return game, None, None, None, original_filename, False
    except Exception as e:
        current_app.logger.error(f"Error checking file security for {actual_file_to_serve}: {e}")
        return game, None, None, None, original_filename, False

    directory_to_serve_from = os.path.dirname(actual_file_to_serve)
    
    current_app.logger.info(f"ROM path resolution complete - Game: {game_id}, Playable: {is_web_playable}, File: {filename_to_serve}")
    
    return game, actual_file_to_serve, directory_to_serve_from, filename_to_serve, original_filename, is_web_playable