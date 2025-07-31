# scanner/core.py
# Contains ALL core logic for scanning, importing, and managing emulators.

import os
import sqlite3
import re
import zipfile
import shutil # For shutil.copy2, shutil.move, shutil.which
import requests
import subprocess # For calling external 7z.exe
from pathlib import Path

# Try to import py7zr for .7z archives
try:
    import py7zr
except ImportError:
    py7zr = None # Set to None if not installed, handled gracefully

from .config import DATABASE_PATH, UPLOAD_FOLDER, EMULATORS_FOLDER, EXTENSION_TO_SYSTEM, EMULATORS

# --- Database Functions (from previous database.py) ---
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    if not os.path.exists(DATABASE_PATH):
        raise FileNotFoundError(f"Database not found at '{DATABASE_PATH}'.\nPlease run the main web app (run.py) once to create it.")
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- Game Scanner Functions (from previous game_scanner.py) ---
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
                log_callback(f"   -> Extracting to {extract_path}")
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
                    
                    log_callback(f"   -> {import_mode.capitalize()}ing to {destination_path}")
                    if import_mode == 'copy':
                        shutil.copy2(original_filepath, destination_path)
                    else: # move
                        shutil.move(original_filepath, destination_path)
                    final_filepath = str(destination_path)
                else: # reference
                    log_callback(f"Processing File (reference): {original_filename}")
                    final_filepath = original_filepath

            log_callback(f"   -> Adding '{title}' to database...")
            conn.execute("INSERT INTO games (title, system, filepath, original_filename) VALUES (?, ?, ?, ?)", (title, system, final_filepath, original_filename))
            conn.commit()
            log_callback(f"   -> Successfully imported.")
            imported_count += 1
            yield {'filepath': original_filepath, 'success': True}

        except sqlite3.IntegrityError:
            log_callback(f"   -> ERROR: Game with this path already exists.", "error")
            yield {'filepath': original_filepath, 'success': False}
        except Exception as e:
            log_callback(f"   -> ERROR: An error occurred during import: {e}", "error")
            yield {'filepath': original_filepath, 'success': False}
    
    conn.close()
    log_callback(f"--- Import Complete: {imported_count} games added. ---")

# --- Emulator Management Functions (from previous emulator_manager.py) ---

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
            # If type is 'web' or other, it remains "Not Installed" from the desktop app's perspective
        
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