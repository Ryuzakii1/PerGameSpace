# scanner/core.py
# Contains ALL core logic for scanning, importing, and managing emulators.

import os
import sqlite3
import re
import zipfile
import shutil # For shutil.copy2, shutil.move, shutil.which, shutil.rmtree
import requests
import subprocess # For calling external 7z.exe
from pathlib import Path
import json
import time
import uuid # For generating unique filenames
from datetime import datetime
from flask import current_app # For accessing app context

# Try to import py7zr for .7z archives
try:
    import py7zr
except ImportError:
    py7zr = None # Set to None if not installed, handled gracefully

from .config import DATABASE_PATH, UPLOAD_FOLDER, COVERS_FOLDER, EMULATORS_FOLDER, EXTENSION_TO_SYSTEM, EMULATORS, Config
from utils import get_effective_path, get_setting

# --- Database Functions ---
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    if not os.path.exists(DATABASE_PATH):
        raise FileNotFoundError(f"Database not found at '{DATABASE_PATH}'.\nPlease run the main web app (run.py) once to create it.")
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def update_game_metadata_in_db(game_id, changes):
    """Updates a game's metadata in the database."""
    conn = get_db_connection()
    try:
        # Filter out fields with None values and construct the update query
        update_fields = [f"{key} = ?" for key in changes.keys() if changes[key] is not None]
        update_values = [value for value in changes.values() if value is not None]
        update_values.append(game_id)
        
        query = f"UPDATE games SET {', '.join(update_fields)} WHERE id = ?"
        conn.execute(query, tuple(update_values))
        conn.commit()
    except Exception as e:
        print(f"Error updating game metadata: {e}")
    finally:
        conn.close()

def get_all_games_from_db(system_name=None):
    """Fetches all games from the database, optionally filtered by system."""
    conn = get_db_connection()
    if system_name:
        games = conn.execute("SELECT * FROM games WHERE system = ? ORDER BY title", (system_name,)).fetchall()
    else:
        games = conn.execute("SELECT * FROM games ORDER BY title").fetchall()
    conn.close()
    return games

def delete_games_from_db(game_ids, log_callback):
    """
    Deletes games from the database and removes their associated files from disk.
    Handles both single files and folders.
    """
    if not game_ids:
        return
        
    conn = get_db_connection()
    if not conn:
        log_callback("Could not connect to database for deletion.", "error")
        return

    try:
        placeholders = ','.join('?' for _ in game_ids)
        # Fetch file and cover paths for deletion
        files_to_delete = conn.execute(f"SELECT filepath, cover_image_path FROM games WHERE id IN ({placeholders})", game_ids).fetchall()
        
        for file_entry in files_to_delete:
            # Delete the game file or directory from disk
            filepath = file_entry['filepath']
            if filepath and os.path.exists(filepath):
                if os.path.isdir(filepath):
                    shutil.rmtree(filepath)
                    log_callback(f"Deleted game directory: {filepath}")
                else:
                    os.remove(filepath)
                    log_callback(f"Deleted game file: {filepath}")
            
            # Delete the cover image if it exists
            cover_image_path = file_entry['cover_image_path']
            if cover_image_path:
                cover_path = os.path.join(COVERS_FOLDER, cover_image_path)
                if os.path.exists(cover_path):
                    os.remove(cover_path)
                    log_callback(f"Deleted cover image: {cover_path}")

        # Delete the records from the database
        conn.execute(f"DELETE FROM games WHERE id IN ({placeholders})", game_ids)
        conn.commit()
        log_callback(f"Successfully deleted {len(game_ids)} game(s) from the database.", "success")
        
    except Exception as e:
        log_callback(f"Error during game deletion: {e}", "error")
    finally:
        if conn:
            conn.close()

# --- Game Scanner Functions ---
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
                    log_callback(f"Processing File (reference): {original_filename}")
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

# --- IGDB Functions ---
def _get_igdb_token(client_id, client_secret, log_callback):
    """
    Retrieves and caches a Twitch/IGDB access token.
    Uses a cache file to avoid re-authenticating on every request.
    """
    token_file = Path(DATABASE_PATH).parent / 'igdb_token.json'
    
    # Check for an existing, non-expired token
    if token_file.exists():
        try:
            with open(token_file, 'r') as f:
                data = json.load(f)
            # Ensure token is not within 1 hour of expiration
            if data['expires_at'] > time.time():
                return data['access_token']
        except (json.JSONDecodeError, KeyError):
            pass # File is corrupt or invalid, proceed to request a new token

    log_callback(f"Requesting new IGDB access token...", "info")
    try:
        twitch_url = f'https://id.twitch.tv/oauth2/token?client_id={client_id}&client_secret={client_secret}&grant_type=client_credentials'
        response = requests.post(twitch_url, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        
        access_token = token_data['access_token']
        expires_in = token_data['expires_in']
        
        # Cache the new token with an expiration timestamp
        expires_at = time.time() + expires_in - 3600 # Subtract an hour to be safe
        with open(token_file, 'w') as f:
            json.dump({'access_token': access_token, 'expires_at': expires_at}, f)
        
        return access_token
    except Exception as e:
        log_callback(f"Error fetching IGDB access token: {e}", "error")
        return None

def _save_cover_image(game_id, image_data):
    """Helper to save image data to a file using a consistent naming scheme and returns the filename."""
    effective_covers_folder = get_effective_path(Config.CUSTOM_COVERS_FOLDER_SETTING_KEY, 'COVERS_FOLDER')
    if not effective_covers_folder:
        raise Exception("Covers folder not configured in settings.")
        
    os.makedirs(effective_covers_folder, exist_ok=True)
    
    # Use a unique filename to prevent conflicts
    filename = f"game_{game_id}_{int(time.time())}.jpg"
    filepath = os.path.join(effective_covers_folder, filename)
    
    with open(filepath, 'wb') as f:
        f.write(image_data)
        
    return filename

def _delete_old_cover(game_id, conn):
    """Deletes the old cover image file from the disk if it exists."""
    cursor = conn.cursor()
    cursor.execute("SELECT cover_image_path FROM games WHERE id = ?", (game_id,))
    result = cursor.fetchone()
    
    if result and result['cover_image_path']:
        old_cover_filename = result['cover_image_path']
        effective_covers_folder = get_effective_path(Config.CUSTOM_COVERS_FOLDER_SETTING_KEY, 'COVERS_FOLDER')
        old_cover_path = os.path.join(effective_covers_folder, old_cover_filename)
        
        if os.path.exists(old_cover_path):
            try:
                os.remove(old_cover_path)
                return True
            except Exception as e:
                current_app.logger.error(f"Failed to delete old cover art at {old_cover_path}: {e}")
                return False
    return False

def fetch_igdb_data(game_title, system_name, log_callback, client_id, client_secret):
    """
    Searches IGDB for game metadata based on title and system.
    Returns a dictionary of metadata and a list of cover image URLs.
    """
    # NOTE: This function is defined in igdb.py in the new structure
    pass

def download_and_set_cover_image(game_id, image_url, log_callback):
    """Downloads an image from a URL and updates the game's cover in the database."""
    conn = get_db_connection()
    if not conn:
        log_callback("Could not connect to database for cover update.", "error")
        raise Exception("Database connection failed.")
    
    try:
        # Delete the old cover before downloading the new one
        _delete_old_cover(game_id, conn)

        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        
        new_cover_filename = _save_cover_image(game_id, response.content)
        
        # CHANGED: Update 'cover_image_path' column, not 'cover_url'
        conn.execute("UPDATE games SET cover_image_path = ? WHERE id = ?", (new_cover_filename, game_id))
        conn.commit()
        log_callback(f"Updated cover for game {game_id} to {new_cover_filename}", "success")
        return new_cover_filename
        
    except Exception as e:
        log_callback(f"Error downloading or saving cover: {e}", "error")
        raise
    finally:
        if conn:
            conn.close()

def set_game_cover_image(game_id, temp_filepath):
    """Saves a custom uploaded cover image and updates the game's database record."""
    conn = get_db_connection()
    if not conn:
        raise Exception("Database connection failed.")
    
    try:
        # Delete the old cover before saving the new one
        _delete_old_cover(game_id, conn)

        with open(temp_filepath, 'rb') as f:
            image_data = f.read()

        new_cover_filename = _save_cover_image(game_id, image_data)

        # Update the database
        conn.execute('UPDATE games SET cover_image_path = ? WHERE id = ?', (new_cover_filename, game_id))
        conn.commit()
        return new_cover_filename
    except Exception as e:
        current_app.logger.error(f"Error setting custom cover for game ID {game_id}: {e}")
        raise
    finally:
        if conn:
            conn.close()


# --- Emulator Management Functions ---
# Helper function to find 7z.exe
def _find_7zip_executable():
    """Tries to find the 7z.exe command-line tool."""
    # Check if 7z.exe is in PATH
    seven_z_path = shutil.which("7z")
    if seven_z_path:
        return seven_z_path
    
    # Common installation paths for 7-Zip (Windows specific)
    program_files_x86 = os.environ.get('ProgramFiles(x86)')
    program_files = os.environ.get('ProgramFiles')

    possible_paths = []
    if program_files_x86:
        possible_paths.append(Path(program_files_x86) / '7-Zip' / '7z.exe')
    if program_files:
        possible_paths.append(Path(program_files) / '7-Zip' / '7z.exe')
    
    for p in possible_paths:
        if p.exists():
            return str(p)
            
    return None

def get_emulator_statuses():
    """
    Checks the database for configured paths for recommended emulators.
    Now uses emulator_name as the primary key for configuration.
    """
    statuses = {}
    conn = get_db_connection()
    if not conn: return {}
    
    # Fetch all configured emulators directly by their name key
    configured_emulators_db = {row['emulator_name']: {'path': row['emulator_path'], 'type': row['install_type']} 
                               for row in conn.execute("SELECT emulator_name, emulator_path, install_type FROM emulator_configs").fetchall()}
    conn.close()

    for name, data in EMULATORS.items(): # Iterating through EMULATORS (e.g., "RetroArch", "SNES9x", "mGBA", "VBA-M")
        status = "Not Installed"
        path = ""
        
        # Check if this specific emulator (by its name from EMULATORS dict) is configured
        if name in configured_emulators_db:
            emu_config = configured_emulators_db[name]
            if emu_config['type'] == 'local': # Only consider 'local' installations for desktop app
                path = emu_config['path']
                if os.path.exists(path):
                    status = "Installed"
                else:
                    status = "Path Invalid"
        
        statuses[name] = {"status": status, "path": path, "url": data['url'], "systems": data['systems']}
    return statuses

def save_emulator_path_to_db(emulator_name, emulator_path, install_type, log_callback):
    """Saves or updates an emulator's path in the database."""
    try:
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO emulator_configs (emulator_name, emulator_path, install_type) VALUES (?, ?, ?)", 
                      (emulator_name, emulator_path, install_type))
        conn.commit()
        conn.close()
        log_callback(f"Database: Saved '{emulator_name}' path: {emulator_path} (type: {install_type}).", "info")
    except Exception as e:
        log_callback(f"Database Error: Could not save path for '{emulator_name}': {e}", "error")
        raise # Re-raise the exception so the calling thread can handle it (e.g., in its finally block)


def download_and_setup_emulator(emu_name, progress_callback, log_callback):
    """Downloads, unzips/un7zips, and configures an emulator."""
    emu_data = EMULATORS.get(emu_name)
    if not emu_data:
        log_callback(f"Error: No configuration found for '{emu_name}'.", "error")
        return

    os.makedirs(EMULATORS_FOLDER, exist_ok=True)
    zip_filename = Path(emu_data['url']).name
    zip_path = EMULATORS_FOLDER / zip_filename
    
    try:
        log_callback(f"Downloading {emu_name} from {emu_data['url']}...")
        with requests.get(emu_data['url'], stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            bytes_downloaded = 0
            with open(zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    if total_size > 0:
                        progress = (bytes_downloaded / total_size) * 100
                        progress_callback(emu_name, f"Downloading... {progress:.1f}%")
        log_callback("Download complete.")
    except Exception as e:
        log_callback(f"Error downloading {emu_name}: {e}", "error")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise # Re-raise to be caught by _run_download's finally block in UI module

    extract_folder = EMULATORS_FOLDER / Path(zip_filename).stem
    
    try:
        log_callback(f"Extracting to {extract_folder}...")
        progress_callback(emu_name, "Extracting...")
        
        if zip_path.suffix.lower() == '.zip':
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_folder)
        elif zip_path.suffix.lower() == '.7z':
            extraction_successful = False
            # Try py7zr first if available
            if py7zr:
                try:
                    with py7zr.SevenZipFile(zip_path, mode='r') as zf:
                        zf.extractall(path=extract_folder)
                    extraction_successful = True
                except py7zr.exceptions.Bad7zFile as e:
                    # Specific error for unsupported filters like BCJ2
                    log_callback(f"Warning: py7zr could not extract (possibly unsupported filter like BCJ2): {e}. Attempting with external 7z.exe...", "warning")
                except Exception as e:
                    log_callback(f"Warning: py7zr extraction failed: {e}. Attempting with external 7z.exe...", "warning")

            if not extraction_successful:
                # Fallback to external 7z.exe
                seven_z_exe = _find_7zip_executable()
                if seven_z_exe:
                    log_callback(f"Using external 7z.exe found at: {seven_z_exe}", "info")
                    try:
                        # -y: assume Yes on all queries (overwrite existing)
                        # -o<output_dir>: set output directory
                        command = [seven_z_exe, 'x', str(zip_path), f'-o{extract_folder}', '-y']
                        result = subprocess.run(command, capture_output=True, text=True, check=True)
                        log_callback(f"7z.exe output:\n{result.stdout}")
                        if result.stderr:
                            log_callback(f"7z.exe errors:\n{result.stderr}", "warning")
                        extraction_successful = True
                    except subprocess.CalledProcessError as e:
                        log_callback(f"Error calling external 7z.exe: {e}\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}", "error")
                    except FileNotFoundError:
                        log_callback(f"Error: 7z.exe not found at '{seven_z_exe}'. Please ensure 7-Zip is installed and in your system PATH.", "error")
                else:
                    log_callback("Error: External 7z.exe not found. Cannot extract this .7z archive.", "error")
            
            if not extraction_successful:
                raise Exception("Failed to extract .7z archive using both py7zr and external 7z.exe.")

        else:
            log_callback(f"Error: Unsupported archive format '{zip_path.suffix}'. Only .zip and .7z are supported for automatic extraction.", "error")
            raise # Re-raise for error handling in calling function

        log_callback("Extraction complete.")
    except Exception as e:
        log_callback(f"Error extracting {emu_name}: {e}", "error")
        if os.path.exists(extract_folder) and os.path.isdir(extract_folder):
            import shutil
            shutil.rmtree(extract_folder)
        raise # Re-raise for error handling in calling function
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

    try:
        progress_callback(emu_name, "Configuring...")
        executable_path = None
        for root, _, files in os.walk(extract_folder):
            for file in files:
                if file.lower() == emu_data['executable_name'].lower():
                    executable_path = os.path.join(root, file)
                    break
            if executable_path: break
        
        if not executable_path:
            raise FileNotFoundError(f"Could not find '{emu_data['executable_name']}' in extracted files.")

        log_callback(f"Found executable: {executable_path}")
        # Use the centralized save_emulator_path_to_db function
        save_emulator_path_to_db(emu_name, executable_path, 'local', log_callback) 
        
        log_callback(f"Successfully configured {emu_name}!")
        progress_callback(emu_name, "Installed")
    except Exception as e:
        log_callback(f"Error configuring {emu_name}: {e}", "error")
        progress_callback(emu_name, "Config Failed")
        raise # Re-raise for _run_download's finally block