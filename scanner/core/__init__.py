# scanner/core/__init__.py
# Contains ALL core logic for scanning, importing, and managing emulators.

import os
import sqlite3
import re
import zipfile
import shutil
import requests
import subprocess
from pathlib import Path
import time
import sys

# --- UNIFIED CONFIGURATION IMPORT ---
try:
    PACKAGE_PARENT = '..'
    SCRIPT_DIR = os.path.dirname(os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__))))
    sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))
    from config import Config, basedir
    DATABASE_PATH = Config.DATABASE
    UPLOAD_FOLDER = Config.UPLOAD_FOLDER
    COVERS_FOLDER = Config.COVERS_FOLDER
    BASE_DIR = basedir
    print(f"Successfully imported top-level config. Database path is: {DATABASE_PATH}")
    from ..config import EMULATORS_FOLDER, EXTENSION_TO_SYSTEM, EMULATORS, SETTINGS_FILE
except ImportError as e:
    print(f"Failed to import unified config, falling back to scanner-only config: {e}")
    from ..config import DATABASE_PATH, UPLOAD_FOLDER, EMULATORS_FOLDER, EXTENSION_TO_SYSTEM, EMULATORS, SETTINGS_FILE, BASE_DIR, COVERS_FOLDER

try:
    import py7zr
except ImportError:
    py7zr = None

# --- Global variable for IGDB access token and its expiry ---
_IGDB_ACCESS_TOKEN = None
_IGDB_TOKEN_EXPIRY = 0

# --- IGDB API Functions ---
def _get_igdb_token(log_callback, client_id, client_secret):
    global _IGDB_ACCESS_TOKEN, _IGDB_TOKEN_EXPIRY
    if _IGDB_ACCESS_TOKEN and time.time() < _IGDB_TOKEN_EXPIRY - 60:
        return
    if not client_id or not client_secret:
        raise ValueError("IGDB API credentials are not configured in settings.")
    try:
        response = requests.post('https://id.twitch.tv/oauth2/token', params={'client_id': client_id, 'client_secret': client_secret, 'grant_type': 'client_credentials'})
        response.raise_for_status()
        token_data = response.json()
        _IGDB_ACCESS_TOKEN = token_data['access_token']
        _IGDB_TOKEN_EXPIRY = time.time() + token_data['expires_in'] - 60
        log_callback("Successfully obtained new IGDB token.", "success")
    except requests.exceptions.RequestException as e:
        log_callback(f"Failed to get IGDB token: {e}", "error")
        raise

def fetch_igdb_data(game_title, system_name, log_callback, client_id, client_secret):
    """Fetches game metadata AND cover/artwork URLs from the IGDB API."""
    try:
        _get_igdb_token(log_callback, client_id, client_secret)
    except Exception:
        return None, []
        
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {_IGDB_ACCESS_TOKEN}', 'Accept': 'application/json'}
    sanitized_title = game_title.replace('"', '')
    # Expanded query to include cover and artworks
    query = (f'search "{sanitized_title}"; fields name, summary, genres.name, first_release_date, involved_companies.company.name, involved_companies.developer, involved_companies.publisher, cover.url, artworks.url; where platforms.name = "{system_name}"; limit 1;')
    
    try:
        response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=query.encode('utf-8'))
        response.raise_for_status()
        games = response.json()
        if not games: return None, []
        
        game = games[0]
        metadata = {}
        if 'genres' in game and game['genres']: metadata['genre'] = game['genres'][0]['name']
        if 'first_release_date' in game: metadata['release_year'] = time.gmtime(game['first_release_date']).tm_year
        if 'summary' in game: metadata['description'] = game['summary']
        developers = [ic['company']['name'] for ic in game.get('involved_companies', []) if ic.get('developer') and 'company' in ic and 'name' in ic['company']]
        publishers = [ic['company']['name'] for ic in game.get('involved_companies', []) if ic.get('publisher') and 'company' in ic and 'name' in ic['company']]
        if developers: metadata['developer'] = ", ".join(developers)
        if publishers: metadata['publisher'] = ", ".join(publishers)
        
        image_urls = []
        # Get the main cover art, preferring 1080p
        if 'cover' in game and 'url' in game['cover']:
            image_urls.append("https:" + game['cover']['url'].replace('t_thumb', 't_1080p'))
        # Get additional artwork
        if 'artworks' in game:
            for art in game['artworks']:
                if 'url' in art:
                    image_urls.append("https:" + art['url'].replace('t_thumb', 't_1080p'))

        return metadata, image_urls
    except requests.exceptions.RequestException as e:
        log_callback(f"IGDB API request failed: {e}", "error")
        return None, []

# --- Database Functions ---
def get_db_connection():
    db_path_obj = Path(DATABASE_PATH)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)
    db_just_created = not db_path_obj.exists()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    if db_just_created:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, system TEXT NOT NULL,
                filepath TEXT NOT NULL UNIQUE, original_filename TEXT, genre TEXT,
                release_year INTEGER, developer TEXT, publisher TEXT, description TEXT,
                play_status TEXT DEFAULT 'Not Played', cover_image_path TEXT
            )''')
        conn.execute('CREATE TABLE IF NOT EXISTS systems (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)')
        conn.execute('CREATE TABLE IF NOT EXISTS emulator_configs (emulator_name TEXT PRIMARY KEY, emulator_path TEXT, install_type TEXT)')
        conn.commit()
    else: # Schema migration
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(games)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'cover_image_path' not in columns:
            cursor.execute("ALTER TABLE games ADD COLUMN cover_image_path TEXT")
        conn.commit()
    return conn

# --- Library Management Core Functions ---
def get_all_games_from_db():
    conn = get_db_connection()
    games = conn.execute("SELECT * FROM games ORDER BY title").fetchall()
    conn.close()
    return [dict(game) for game in games]

def update_game_metadata_in_db(game_id, changes):
    conn = get_db_connection()
    set_clause = ", ".join([f"{key} = ?" for key in changes.keys()])
    values = list(changes.values()) + [game_id]
    query = f"UPDATE games SET {set_clause} WHERE id = ?"
    conn.execute(query, tuple(values))
    conn.commit()
    conn.close()

def delete_games_from_db(game_ids, log_callback):
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in game_ids)
    cursor.execute(f"SELECT filepath, cover_image_path FROM games WHERE id IN ({placeholders})", tuple(game_ids))
    paths_to_delete = cursor.fetchall()
    cursor.execute(f"DELETE FROM games WHERE id IN ({placeholders})", tuple(game_ids))
    conn.commit()
    conn.close()
    for row in paths_to_delete:
        for path_str in [row['filepath'], row['cover_image_path']]:
            if not path_str: continue
            try:
                path = Path(path_str)
                if Path(UPLOAD_FOLDER).resolve() in path.resolve().parents or Path(COVERS_FOLDER).resolve() in path.resolve().parents:
                    if path.is_dir(): shutil.rmtree(path)
                    elif path.is_file(): path.unlink()
                    log_callback(f"Deleted asset: {path}", "info")
            except Exception as e:
                log_callback(f"Error deleting file {path_str}: {e}", "error")

def set_game_cover_image(game_id, new_image_path):
    source_path = Path(new_image_path)
    dest_filename = f"game_{game_id}{source_path.suffix}"
    dest_path = Path(COVERS_FOLDER) / dest_filename
    os.makedirs(COVERS_FOLDER, exist_ok=True)
    shutil.copy2(source_path, dest_path)
    conn = get_db_connection()
    conn.execute("UPDATE games SET cover_image_path = ? WHERE id = ?", (str(dest_path), game_id))
    conn.commit()
    conn.close()
    return str(dest_path)

def download_and_set_cover_image(game_id, image_url, log_callback):
    """Downloads an image from a URL and sets it as the cover for a game."""
    try:
        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status()
        
        # Determine file extension from URL
        source_extension = Path(image_url.split('?')[0]).suffix
        if not source_extension:
            source_extension = ".jpg" # Default if no extension found

        dest_filename = f"game_{game_id}{source_extension}"
        dest_path = Path(COVERS_FOLDER) / dest_filename
        os.makedirs(COVERS_FOLDER, exist_ok=True)
        
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        log_callback(f"Downloaded cover to {dest_path}", "info")

        conn = get_db_connection()
        conn.execute("UPDATE games SET cover_image_path = ? WHERE id = ?", (str(dest_path), game_id))
        conn.commit()
        conn.close()
        
        return str(dest_path)
    except requests.exceptions.RequestException as e:
        log_callback(f"Failed to download image from {image_url}: {e}", "error")
        raise


# --- Game Scanner Functions ---
def clean_game_title(filename):
    title = Path(filename).stem
    title = re.sub(r'\(.*?\)|\[.*?\]', '', title).strip().replace('_', ' ').replace('.', ' ')
    return ' '.join(word.capitalize() for word in title.split())

def scan_directory(scan_path, log_callback):
    try:
        conn = get_db_connection()
        existing_filepaths = {row['filepath'] for row in conn.execute("SELECT filepath FROM games").fetchall()}
        conn.close()
    except Exception as e:
        log_callback(f"DB error during scan: {e}", "error")
        return
    for root, _, files in os.walk(scan_path):
        for file in files:
            file_path = Path(root) / file
            if str(file_path) in existing_filepaths: continue
            ext = file_path.suffix.lower()
            game_info = None
            if ext == '.zip':
                try:
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        rom_files = [f for f in zf.namelist() if Path(f).suffix.lower() in EXTENSION_TO_SYSTEM]
                        if rom_files:
                            system = EXTENSION_TO_SYSTEM.get(Path(rom_files[0]).suffix.lower(), "Other")
                            title = clean_game_title(rom_files[0])
                            game_info = {'title': title, 'system': system, 'filepath': str(file_path), 'type': 'zip', 'rom_in_zip': rom_files[0]}
                except zipfile.BadZipFile:
                    log_callback(f"Bad ZIP file: {file}", "warning")
            elif ext in EXTENSION_TO_SYSTEM:
                system = EXTENSION_TO_SYSTEM.get(ext, "Other")
                title = clean_game_title(file)
                game_info = {'title': title, 'system': system, 'filepath': str(file_path), 'type': 'file'}
            if game_info:
                game_info.update({'genre': '', 'release_year': None, 'developer': '', 'publisher': '', 'description': '', 'play_status': 'Not Played'})
                yield game_info

def import_games(games_to_import, import_mode, log_callback):
    conn = get_db_connection()
    for game in games_to_import:
        title, system, original_filepath = game['title'], game['system'], game['filepath']
        final_filepath, original_filename = original_filepath, Path(original_filepath).name
        try:
            if game['type'] == 'zip':
                safe_system = "".join(c for c in system if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')
                extract_path = Path(UPLOAD_FOLDER) / safe_system / Path(original_filepath).stem
                os.makedirs(extract_path, exist_ok=True)
                with zipfile.ZipFile(original_filepath, 'r') as zf: zf.extract(game['rom_in_zip'], extract_path)
                final_filepath = str(extract_path)
            elif game['type'] == 'file' and import_mode in ("copy", "move"):
                safe_system = "".join(c for c in system if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')
                destination_dir = Path(UPLOAD_FOLDER) / safe_system
                os.makedirs(destination_dir, exist_ok=True)
                destination_path = destination_dir / original_filename
                if import_mode == 'copy': shutil.copy2(original_filepath, destination_path)
                else: shutil.move(original_filepath, destination_path)
                final_filepath = str(destination_path)
            conn.execute("INSERT INTO games (title, system, filepath, original_filename, genre, release_year, developer, publisher, description, play_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (title, system, final_filepath, original_filename, game.get('genre'), game.get('release_year'), game.get('developer'), game.get('publisher'), game.get('description'), game.get('play_status')))
            conn.commit()
            yield {'filepath': original_filepath, 'success': True}
        except sqlite3.IntegrityError:
            yield {'filepath': original_filepath, 'success': False}
        except Exception as e:
            log_callback(f"Error importing {original_filename}: {e}", "error")
            yield {'filepath': original_filepath, 'success': False}
    conn.close()

# --- Emulator Management Functions ---
def _find_7zip_executable():
    if seven_z_path := shutil.which("7z"): return seven_z_path
    possible_paths = []
    if pf_x86 := os.environ.get('ProgramFiles(x86)'): possible_paths.append(Path(pf_x86) / '7-Zip' / '7z.exe')
    if pf := os.environ.get('ProgramFiles'): possible_paths.append(Path(pf) / '7-Zip' / '7z.exe')
    for p in possible_paths:
        if p.exists(): return str(p)
    return None

def get_emulator_statuses(force_refresh=False):
    conn = get_db_connection()
    try: configs = {row['emulator_name']: dict(row) for row in conn.execute("SELECT * FROM emulator_configs").fetchall()}
    except sqlite3.OperationalError: configs = {}
    conn.close()
    statuses = {}
    for name, data in EMULATORS.items():
        status, path = "Not Installed", ""
        if name in configs and configs[name]['emulator_path']:
            path = configs[name]['emulator_path']
            status = "Installed" if os.path.exists(path) else "Path Invalid"
        statuses[name] = {"status": status, "path": path, "url": data.get('url', ''), "systems": data.get('systems', [])}
    return statuses

def save_emulator_path_to_db(emulator_name, emulator_path, install_type, log_callback):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO emulator_configs (emulator_name, emulator_path, install_type) VALUES (?, ?, ?)", (emulator_name, emulator_path, install_type))
    conn.commit()
    conn.close()
    log_callback(f"Saved '{emulator_name}' path.", "info")

def delete_emulator_from_db(emulator_name, log_callback):
    conn = get_db_connection()
    conn.execute("DELETE FROM emulator_configs WHERE emulator_name = ?", (emulator_name,))
    conn.commit()
    conn.close()
    log_callback(f"Deleted '{emulator_name}' entry.", "info")

def download_and_setup_emulator(emu_config, progress_callback, log_callback):
    os.makedirs(EMULATORS_FOLDER, exist_ok=True)
    zip_path = EMULATORS_FOLDER / Path(emu_config['url']).name
    try:
        with requests.get(emu_config['url'], stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            with open(zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    if total_size > 0: progress_callback(emu_config['name'], f"Downloading... {(f.tell() / total_size) * 100:.1f}%")
    except Exception as e:
        if os.path.exists(zip_path): os.remove(zip_path)
        raise e
    extract_folder = EMULATORS_FOLDER / zip_path.stem
    try:
        if zip_path.suffix.lower() == '.zip':
            with zipfile.ZipFile(zip_path, 'r') as zf: zf.extractall(extract_folder)
        elif zip_path.suffix.lower() == '.7z':
            if py7zr:
                try:
                    with py7zr.SevenZipFile(zip_path, mode='r') as z: z.extractall(path=extract_folder)
                except Exception:
                    if seven_z_exe := _find_7zip_executable(): subprocess.run([seven_z_exe, 'x', str(zip_path), f'-o{extract_folder}', '-y'], check=True)
                    else: raise Exception("py7zr failed and 7z.exe not found.")
            else:
                if seven_z_exe := _find_7zip_executable(): subprocess.run([seven_z_exe, 'x', str(zip_path), f'-o{extract_folder}', '-y'], check=True)
                else: raise Exception("7z archive but py7zr not installed and 7z.exe not found.")
    except Exception as e:
        if os.path.exists(extract_folder): shutil.rmtree(extract_folder)
        raise e
    finally:
        if os.path.exists(zip_path): os.remove(zip_path)
    try:
        executable_path = next((os.path.join(r, f) for r, _, fs in os.walk(extract_folder) for f in fs if f.lower() == emu_config['executable_name'].lower()), None)
        if not executable_path: raise FileNotFoundError(f"Could not find '{emu_config['executable_name']}'")
        save_emulator_path_to_db(emu_config['name'], executable_path, 'local', log_callback)
        progress_callback(emu_config['name'], "Installed")
    except Exception as e:
        progress_callback(emu_config['name'], "Config Failed")
        raise e

def backup_application_data(backup_location, log_callback, base_dir):
    backup_path = Path(backup_location)
    backup_path.mkdir(parents=True, exist_ok=True)
    files_to_backup = [("Database", DATABASE_PATH), ("GUI Settings", SETTINGS_FILE)]
    folders_to_backup = [("Uploaded Games", UPLOAD_FOLDER), ("Downloaded Emulators", EMULATORS_FOLDER)]
    for _, src_path_str in files_to_backup:
        if Path(src_path_str).exists(): shutil.copy2(src_path_str, backup_path / Path(src_path_str).name)
    for _, src_path_str in folders_to_backup:
        src_path = Path(src_path_str)
        if src_path.exists() and src_path.is_dir():
            dest_path = backup_path / src_path.name
            if dest_path.exists(): shutil.rmtree(dest_path)
            shutil.copytree(src_path, dest_path)
    log_callback(f"Backup complete to: {backup_path}", "success")

def restore_application_data(restore_location, log_callback, base_dir):
    source_path = Path(restore_location)
    if not source_path.is_dir(): raise FileNotFoundError(f"Restore location '{restore_location}' not found.")
    files_to_restore = [("Database", DATABASE_PATH), ("GUI Settings", SETTINGS_FILE)]
    folders_to_restore = [("Uploaded Games", UPLOAD_FOLDER), ("Downloaded Emulators", EMULATORS_FOLDER)]
    for _, dest_path_str in files_to_restore:
        src_file = source_path / Path(dest_path_str).name
        if src_file.exists(): shutil.copy2(src_file, dest_path_str)
    for _, dest_path_str in folders_to_restore:
        src_folder = source_path / Path(dest_path_str).name
        if src_folder.exists() and src_folder.is_dir():
            dest_path = Path(dest_path_str)
            if dest_path.exists(): shutil.rmtree(dest_path)
            shutil.copytree(src_folder, dest_path)
    log_callback(f"Restore complete from: {source_path}", "success")
