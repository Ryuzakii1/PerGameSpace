# scanner/core/__init__.py
# Contains ALL core logic for scanning, importing, and managing emulators.

import os
import sqlite3
import re
import zipfile
import shutil # For shutil.copy2, shutil.move, shutil.which
import requests
import subprocess # For calling external 7z.exe
from pathlib import Path
import time # For rate limiting/delays

# Try to import py7zr for .7z archives
try:
    import py7zr
except ImportError:
    py7zr = None # Set to None if not installed, handled gracefully

from ..config import DATABASE_PATH, UPLOAD_FOLDER, EMULATORS_FOLDER, EXTENSION_TO_SYSTEM, EMULATORS, SETTINGS_FILE, BASE_DIR, IGDB_CLIENT_ID, IGDB_CLIENT_SECRET

# --- Global variable for IGDB access token and its expiry ---
# This is a simple in-memory cache. For production, consider persisting this securely.
_IGDB_ACCESS_TOKEN = None
_IGDB_TOKEN_EXPIRY = 0 # Unix timestamp

# --- IGDB API Functions ---

def _get_igdb_token(log_callback):
    """Gets a new IGDB API token if the current one is expired."""
    global _IGDB_ACCESS_TOKEN, _IGDB_TOKEN_EXPIRY
    # Check if the token is still valid (with a 60-second buffer)
    if _IGDB_ACCESS_TOKEN and time.time() < _IGDB_TOKEN_EXPIRY - 60:
        log_callback("Using existing IGDB token.", "info")
        return

    log_callback("Requesting new IGDB access token...", "info")
    if not IGDB_CLIENT_ID or not IGDB_CLIENT_SECRET:
        log_callback("IGDB_CLIENT_ID or IGDB_CLIENT_SECRET is not set in config.", "error")
        raise ValueError("IGDB API credentials are not configured.")

    try:
        response = requests.post(
            'https://id.twitch.tv/oauth2/token',
            params={
                'client_id': IGDB_CLIENT_ID,
                'client_secret': IGDB_CLIENT_SECRET,
                'grant_type': 'client_credentials'
            }
        )
        response.raise_for_status()
        token_data = response.json()
        _IGDB_ACCESS_TOKEN = token_data['access_token']
        # Set expiry time with a small buffer
        _IGDB_TOKEN_EXPIRY = time.time() + token_data['expires_in'] - 60
        log_callback("Successfully obtained new IGDB token.", "success")
    except requests.exceptions.RequestException as e:
        log_callback(f"Failed to get IGDB token: {e}", "error")
        raise

def fetch_igdb_metadata(game_title, system_name, log_callback, client_id, client_secret):
    """
    Fetches game metadata from the IGDB API.
    Note: client_id and client_secret are passed but the function uses the globally imported ones.
    This is to match the calling signature in scan_review_dialog.py.
    """
    try:
        _get_igdb_token(log_callback)
    except Exception as e:
        return None # Can't proceed without a token

    headers = {
        'Client-ID': IGDB_CLIENT_ID,
        'Authorization': f'Bearer {_IGDB_ACCESS_TOKEN}',
        'Accept': 'application/json'
    }

    # Build the APICalypse query string
    # Searching by title and filtering by platform name is a good approach.
    # The search term is sanitized by removing quotes to prevent query injection.
    sanitized_title = game_title.replace('"', '')
    query = (
        f'search "{sanitized_title}"; '
        'fields name, summary, genres.name, first_release_date, '
        'involved_companies.company.name, involved_companies.developer, involved_companies.publisher; '
        f'where platforms.name = "{system_name}"; '
        'limit 1;'
    )

    log_callback(f"Querying IGDB for: '{game_title}' on '{system_name}'", "info")

    try:
        response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=query.encode('utf-8'))
        response.raise_for_status()
        games = response.json()

        if not games:
            log_callback(f"No match found on IGDB for '{game_title}' on '{system_name}'.", "warning")
            return None

        game = games[0] # Take the first result
        log_callback(f"Found IGDB match: {game.get('name')}", "info")

        metadata = {}
        if 'genres' in game and game['genres']:
            metadata['genre'] = game['genres'][0]['name']
        if 'first_release_date' in game:
            metadata['release_year'] = time.gmtime(game['first_release_date']).tm_year
        if 'summary' in game:
            metadata['description'] = game['summary']

        developers = [
            ic['company']['name'] for ic in game.get('involved_companies', [])
            if ic.get('developer') and 'company' in ic and 'name' in ic['company']
        ]
        publishers = [
            ic['company']['name'] for ic in game.get('involved_companies', [])
            if ic.get('publisher') and 'company' in ic and 'name' in ic['company']
        ]

        if developers:
            metadata['developer'] = ", ".join(developers)
        if publishers:
            metadata['publisher'] = ", ".join(publishers)

        return metadata

    except requests.exceptions.RequestException as e:
        log_callback(f"IGDB API request failed: {e}", "error")
        # Log the response body if available for more details
        if e.response is not None:
            log_callback(f"Response body: {e.response.text}", "error")
        return None
    except Exception as e:
        log_callback(f"An unexpected error occurred during IGDB fetch: {e}", "error")
        return None

# --- Database Functions ---
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    db_path_obj = Path(DATABASE_PATH)
    # Ensure the directory for the database exists
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Check if DB file exists. If not, create it and its tables.
    db_just_created = not db_path_obj.exists()

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    if db_just_created:
        # Create initial tables if the DB file was just created
        conn.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                system TEXT NOT NULL,
                filepath TEXT NOT NULL UNIQUE,
                original_filename TEXT,
                genre TEXT,
                release_year INTEGER,
                developer TEXT,
                publisher TEXT,
                description TEXT,
                play_status TEXT DEFAULT 'Not Played'
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
                emulator_name TEXT PRIMARY KEY,
                emulator_path TEXT, -- Path can be null if not configured
                install_type TEXT   -- 'local', 'web', etc.
            )
        ''')
        conn.commit()
        # In a GUI context, you might log this creation
        # print(f"Database created and initialized at '{DATABASE_PATH}'.") # Use a log_callback if available here
    else:
        # --- Handle potential schema migration for existing databases ---
        # This is a simple example for adding columns if they don't exist.
        # For a production app, you'd use a proper migration tool.
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(games)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'genre' not in columns: conn.execute("ALTER TABLE games ADD COLUMN genre TEXT")
        if 'release_year' not in columns: conn.execute("ALTER TABLE games ADD COLUMN release_year INTEGER")
        if 'developer' not in columns: conn.execute("ALTER TABLE games ADD COLUMN developer TEXT")
        if 'publisher' not in columns: conn.execute("ALTER TABLE games ADD COLUMN publisher TEXT")
        if 'description' not in columns: conn.execute("ALTER TABLE games ADD COLUMN description TEXT")
        if 'play_status' not in columns: conn.execute("ALTER TABLE games ADD COLUMN play_status TEXT DEFAULT 'Not Played'")
        conn.commit()
        # --- End schema migration handling ---

    return conn

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
                final_path_check = game_info['filepath']
                if final_path_check not in existing_filepaths:
                    # Initialize new metadata fields to empty string or None for scanned games
                    game_info['genre'] = ''
                    game_info['release_year'] = None
                    game_info['developer'] = ''
                    game_info['publisher'] = ''
                    game_info['description'] = ''
                    game_info['play_status'] = 'Not Played'
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
                log_callback(f"   -> Extracting to {extract_path}")
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

                    log_callback(f"   -> {import_mode.capitalize()}ing to {destination_path}")
                    if import_mode == 'copy':
                        shutil.copy2(original_filepath, destination_path)
                    else: # move
                        shutil.move(original_filepath, destination_path)
                    final_filepath = str(destination_path)
                else: # reference
                    log_callback(f"Processing File (reference): {original_filename}")
                    final_filepath = original_filepath

            log_callback(f"   -> Adding '{title}' to database...")
            # Updated INSERT statement to include new metadata fields
            conn.execute("""
                INSERT INTO games (title, system, filepath, original_filename,
                               genre, release_year, developer, publisher, description, play_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, system, final_filepath, original_filename,
                game.get('genre'), game.get('release_year'), game.get('developer'),
                game.get('publisher'), game.get('description'), game.get('play_status')
            ))
            conn.commit()
            log_callback(f"   -> Successfully imported.")
            imported_count += 1
            yield {'filepath': original_filepath, 'success': True}

        except sqlite3.IntegrityError:
            log_callback(f"   -> ERROR: Game with this path already exists.", "error")
            yield {'filepath': original_filepath, 'success': False}
        except Exception as e:
            log_callback(f"   -> ERROR: An error occurred during import: {e}", "error")
            yield {'filepath': original_filepath, 'success': False}

    conn.close()
    log_callback(f"--- Import Complete: {imported_count} games added. ---")

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

def get_emulator_statuses(force_refresh=False):
    """
    Checks the database for configured paths for recommended emulators.
    The force_refresh parameter is accepted but does not alter behavior
    in this function's current implementation (it's always a fresh DB query).
    """
    statuses = {}
    conn = get_db_connection()
    if not conn: return {}

    # Fetch all configured emulators directly by their name key
    try:
        configured_emulators_db = {row['emulator_name']: {'path': row['emulator_path'], 'type': row['install_type']}
                               for row in conn.execute("SELECT emulator_name, emulator_path, install_type FROM emulator_configs").fetchall()}
    except sqlite3.OperationalError:
        configured_emulators_db = {} # No emulators configured yet if table not found or empty.

    conn.close()

    for name, data in EMULATORS.items(): # Iterating through EMULATORS (from config.py)
        status = "Not Installed"
        path = ""

        # Check if this specific emulator is configured in the DB
        if name in configured_emulators_db:
            emu_config = configured_emulators_db[name]
            if emu_config['path']: # Check if a path is actually stored
                path = emu_config['path']
                if os.path.exists(path): # Check if the executable/folder actually exists on disk
                    status = "Installed"
                else:
                    status = "Path Invalid" # Path in DB, but file/folder missing on disk
            else:
                status = "Not Installed" # Should not happen if path is NOT NULL, but defensive

        statuses[name] = {"status": status, "path": path, "url": data.get('url', ''), "systems": data.get('systems', [])}
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
        raise

def delete_emulator_from_db(emulator_name, log_callback):
    """Deletes an emulator entry from the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM emulator_configs WHERE emulator_name = ?", (emulator_name,))
        conn.commit()
        conn.close()
        log_callback(f"Database: Deleted '{emulator_name}' entry.", "info")
    except Exception as e:
        log_callback(f"Database Error: Could not delete '{emulator_name}': {e}", "error")
        raise


def download_and_setup_emulator(emu_config, progress_callback, log_callback): # THIS FUNCTION IS HERE
    """Downloads, unzips/un7zips, and configures an emulator."""
    os.makedirs(EMULATORS_FOLDER, exist_ok=True)
    zip_filename = Path(emu_config['url']).name
    zip_path = EMULATORS_FOLDER / zip_filename

    try:
        log_callback(f"Downloading {emu_config['name']} from {emu_config['url']}...", "info")
        with requests.get(emu_config['url'], stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            bytes_downloaded = 0
            with open(zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    if total_size > 0:
                        progress = (bytes_downloaded / total_size) * 100
                        progress_callback(emu_config['name'], f"Downloading... {progress:.1f}%")
        log_callback("Download complete.", "info")
    except Exception as e:
        log_callback(f"Error downloading {emu_config['name']}: {e}", "error")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise

    extract_folder = EMULATORS_FOLDER / Path(zip_filename).stem

    try:
        log_callback(f"Extracting to {extract_folder}...", "info")
        progress_callback(emu_config['name'], "Extracting...")

        if zip_path.suffix.lower() == '.zip':
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_folder)
        elif zip_path.suffix.lower() == '.7z':
            extraction_successful = False
            if py7zr:
                try:
                    with py7zr.SevenZipFile(zip_path, mode='r') as zf:
                        zf.extractall(path=extract_folder)
                    extraction_successful = True
                except py7zr.exceptions.Bad7zFile as err:
                    log_callback(f"Warning: py7zr could not extract (possibly unsupported filter like BCJ2): {err}. Attempting with external 7z.exe...", "warning")
                except Exception as err:
                    log_callback(f"Warning: py7zr extraction failed: {err}. Attempting with external 7z.exe...", "warning")

            if not extraction_successful:
                seven_z_exe = _find_7zip_executable()
                if seven_z_exe:
                    log_callback(f"Using external 7z.exe found at: {seven_z_exe}", "info")
                    try:
                        command = [seven_z_exe, 'x', str(zip_path), f'-o{extract_folder}', '-y']
                        result = subprocess.run(command, capture_output=True, text=True, check=True)
                        log_callback(f"7z.exe output:\n{result.stdout}", "info")
                        if result.stderr:
                            log_callback(f"7z.exe errors:\n{result.stderr}", "warning")
                        extraction_successful = True
                    except subprocess.CalledProcessError as err:
                        log_callback(f"Error calling external 7z.exe: {err}\nSTDOUT: {err.stdout}\nSTDERR: {err.stderr}", "error")
                    except FileNotFoundError:
                        log_callback(f"Error: 7z.exe not found at '{seven_z_exe}'. Please ensure 7-Zip is installed and in your system PATH.", "error")
                else:
                    log_callback("Error: External 7z.exe not found. Cannot extract this .7z archive.", "error")

            if not extraction_successful:
                raise Exception("Failed to extract .7z archive using both py7zr and external 7z.exe.")

        else:
            log_callback(f"Error: Unsupported archive format '{zip_path.suffix}'. Only .zip and .7z are supported for automatic extraction.", "error")
            raise

        log_callback("Extraction complete.", "info")
    except Exception as e:
        log_callback(f"Error extracting {emu_config['name']}: {e}", "error")
        if os.path.exists(extract_folder) and os.path.isdir(extract_folder):
            shutil.rmtree(extract_folder)
        raise
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

    try:
        progress_callback(emu_config['name'], "Configuring...")
        executable_path = None
        for root, _, files in os.walk(extract_folder):
            for file in files:
                if file.lower() == emu_config['executable_name'].lower():
                    executable_path = os.path.join(root, file)
                    break
            if executable_path: break

        if not executable_path:
            raise FileNotFoundError(f"Could not find '{emu_config['executable_name']}' in extracted files for {emu_config['name']}.")

        log_callback(f"Found executable: {executable_path}", "info")
        save_emulator_path_to_db(emu_config['name'], executable_path, 'local', log_callback)

        log_callback(f"Successfully configured {emu_config['name']}!", "success")
        progress_callback(emu_config['name'], "Installed")
    except Exception as e:
        log_callback(f"Error configuring {emu_config['name']}: {e}", "error")
        progress_callback(emu_config['name'], "Config Failed")
        raise


# --- Configuration Backup/Restore Functions ---
def backup_application_data(backup_location, log_callback, base_dir):
    """
    Backs up application data (database, settings, uploads, emulators) to a specified location.
    """
    log_callback(f"Starting backup to: {backup_location}", "info")

    # Ensure backup directory exists
    backup_path = Path(backup_location)
    backup_path.mkdir(parents=True, exist_ok=True)

    files_to_backup = [
        ("Database", DATABASE_PATH),
        ("GUI Settings", SETTINGS_FILE),
    ]
    folders_to_backup = [
        ("Uploaded Games", UPLOAD_FOLDER),
        ("Downloaded Emulators", EMULATORS_FOLDER),
    ]

    # Backup individual files
    for description, src_path_str in files_to_backup:
        src_path = Path(src_path_str) # Ensure it's a Path object for operations
        try:
            if src_path.exists():
                dest_path = backup_path / src_path.name
                shutil.copy2(src_path, dest_path)
                log_callback(f"Backed up {description}: {src_path.name}", "info")
            else:
                log_callback(f"Warning: {description} not found at {src_path}, skipping backup.", "warning")
        except Exception as e:
            log_callback(f"Error backing up {description} ({src_path.name}): {e}", "error")
            raise

    # Backup folders
    for description, src_path_str in folders_to_backup:
        src_path = Path(src_path_str) # Ensure it's a Path object
        try:
            if src_path.exists() and src_path.is_dir():
                dest_path = backup_path / src_path.name
                if dest_path.exists():
                    shutil.rmtree(dest_path) # Remove existing folder before copying
                    log_callback(f"Cleared existing backup folder for {description}: {src_path.name}", "info")
                shutil.copytree(src_path, dest_path)
                log_callback(f"Backed up {description} folder: {src_path.name}", "info")
            else:
                log_callback(f"Warning: {description} folder not found at {src_path}, skipping backup.", "warning")
        except Exception as e:
            log_callback(f"Error backing up {description} folder ({src_path.name}): {e}", "error")
            raise

    log_callback(f"Backup complete to: {backup_path}", "success")


def restore_application_data(restore_location, log_callback, base_dir):
    """
    Restores application data (database, settings, uploads, emulators) from a specified location.
    WARNING: This will overwrite existing data.
    """
    log_callback(f"Starting restore from: {restore_location}", "info")

    source_path = Path(restore_location)
    if not source_path.is_dir():
        raise FileNotFoundError(f"Restore location '{restore_location}' is not a valid directory.")

    files_to_restore = [
        ("Database", DATABASE_PATH),
        ("GUI Settings", SETTINGS_FILE),
    ]
    folders_to_restore = [
        ("Uploaded Games", UPLOAD_FOLDER),
        ("Downloaded Emulators", EMULATORS_FOLDER),
    ]

    # Restore individual files
    for description, dest_path_str in files_to_restore:
        dest_path = Path(dest_path_str) # Ensure dest_path is a Path object
        src_file = source_path / dest_path.name
        try:
            if src_file.exists():
                shutil.copy2(src_file, dest_path)
                log_callback(f"Restored {description}: {src_file.name}", "info")
            else:
                log_callback(f"Warning: Backup file for {description} not found at {src_file}, skipping restore.", "warning")
        except Exception as e:
            log_callback(f"Error restoring {description} ({src_file.name}): {e}", "error")
            raise

    # Restore folders
    for description, dest_path_str in folders_to_restore:
        dest_path = Path(dest_path_str) # Ensure dest_path is a Path object
        src_folder = source_path / dest_path.name
        try:
            if src_folder.exists() and src_folder.is_dir():
                if dest_path.exists():
                    shutil.rmtree(dest_path) # Remove current folder before restoring
                    log_callback(f"Cleared existing folder for {description}: {dest_path.name}", "info")
                shutil.copytree(src_folder, dest_path)
                log_callback(f"Restored {description} folder: {src_folder.name}", "info")
            else:
                log_callback(f"Warning: {description} folder not found at {src_folder}, skipping restore.", "warning")
        except Exception as e:
            log_callback(f"Error restoring {description} folder ({src_folder.name}): {e}", "error")
            raise

    log_callback(f"Restore complete from: {source_path}", "success")