# scanner/core/game_scanner.py
import os
import sqlite3
import re
import zipfile
import shutil
from pathlib import Path
from .database import get_db_connection
from ..config import UPLOAD_FOLDER, EXTENSION_TO_SYSTEM

def clean_game_title(filename):
    """Cleans up a filename to create a more readable game title."""
    title = Path(filename).stem
    title = re.sub(r'\(.*?\)|\[.*?\]', '', title).strip()
    title = title.replace('_', ' ').replace('.', ' ')
    title = ' '.join(word.capitalize() for word in title.split())
    return title

def scan_directory(scan_path, log_callback):
    """Scans a directory and yields potential new games to be reviewed."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        existing_filepaths = {row['filepath'] for row in cursor.execute("SELECT filepath FROM games").fetchall()}
        conn.close()
    except Exception as e:
        log_callback(f"Database connection error during scan: {e}", "error")
        return

    for root, _, files in os.walk(scan_path):
        for file in files:
            file_path = Path(root) / file
            ext = file_path.suffix.lower()
            
            game_info = None
            if ext == '.zip':
                try:
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        rom_files = [f for f in zf.namelist() if Path(f).suffix.lower() in EXTENSION_TO_SYSTEM]
                        if rom_files:
                            rom_in_zip = rom_files[0]
                            rom_ext = Path(rom_in_zip).suffix.lower()
                            system = EXTENSION_TO_SYSTEM.get(rom_ext, "Other")
                            title = clean_game_title(rom_in_zip)
                            game_info = {'title': title, 'system': system, 'filepath': str(file_path), 'type': 'zip', 'rom_in_zip': rom_in_zip}
                except zipfile.BadZipFile:
                    log_callback(f"Warning: Bad ZIP file skipped: {file}", "warning")
            
            elif ext in EXTENSION_TO_SYSTEM:
                system = EXTENSION_TO_SYSTEM.get(ext, "Other")
                title = clean_game_title(file)
                game_info = {'title': title, 'system': system, 'filepath': str(file_path), 'type': 'file'}

            if game_info:
                final_path = game_info['filepath']
                if game_info['type'] == 'zip':
                    safe_system = "".join(c for c in game_info['system'] if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')
                    safe_title = Path(game_info['filepath']).stem
                    final_path = str(Path(UPLOAD_FOLDER) / safe_system / safe_title)
                
                if final_path not in existing_filepaths:
                    yield game_info

def import_games(games_to_import, import_mode, log_callback):
    """Imports a list of games into the database with the specified file operation."""
    conn = get_db_connection()
    if not conn:
        log_callback("Could not connect to database for import.", "error")
        return

    imported_count = 0
    for game in games_to_import:
        title, system, original_filepath = game['title'], game['system'], game['filepath']
        final_filepath, original_filename = original_filepath, Path(original_filepath).name
        
        try:
            if game['type'] == 'zip':
                log_callback(f"Processing ZIP: {original_filename}")
                safe_system = "".join(c for c in system if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')
                safe_title = Path(original_filepath).stem
                extract_path = Path(UPLOAD_FOLDER) / safe_system / safe_title
                log_callback(f"  -> Extracting to {extract_path}")
                os.makedirs(extract_path, exist_ok=True)
                with zipfile.ZipFile(original_filepath, 'r') as zf:
                    zf.extract(game['rom_in_zip'], extract_path)
                final_filepath = str(extract_path)
            
            elif game['type'] == 'file':
                if import_mode in ("copy", "move"):
                    log_callback(f"Processing File ({import_mode}): {original_filename}")
                    safe_system = "".join(c for c in system if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')
                    destination_dir = Path(UPLOAD_FOLDER) / safe_system
                    os.makedirs(destination_dir, exist_ok=True)
                    destination_path = destination_dir / original_filename
                    
                    log_callback(f"  -> {import_mode.capitalize()}ing to {destination_path}")
                    if import_mode == 'copy':
                        shutil.copy2(original_filepath, destination_path)
                    else: # move
                        shutil.move(original_filepath, destination_path)
                    final_filepath = str(destination_path)
                else: # reference
                    log_callback(f"Processing File (reference): {original_filepath}")
                    final_filepath = original_filepath

            log_callback(f"  -> Adding '{title}' to database...")
            conn.execute("INSERT INTO games (title, system, filepath, original_filename) VALUES (?, ?, ?, ?)", (title, system, final_filepath, original_filename))
            conn.commit()
            log_callback(f"  -> Successfully imported.")
            imported_count += 1
            yield {'filepath': original_filepath, 'success': True}

        except sqlite3.IntegrityError:
            log_callback(f"  -> ERROR: Game with this path already exists.", "error")
            yield {'filepath': original_filepath, 'success': False}
        except Exception as e:
            log_callback(f"  -> ERROR: An error occurred during import: {e}", "error")
            yield {'filepath': original_filepath, 'success': False}
    
    conn.close()
    log_callback(f"--- Import Complete: {imported_count} games added. ---")
