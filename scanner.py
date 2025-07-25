# scanner.py
import os
import requests
import json
import argparse

# --- Configuration for the Scanner ---
FLASK_SERVER_URL = "http://127.0.0.1:5000"  # Or your server's IP/hostname
API_ADD_GAME_ENDPOINT = f"{FLASK_SERVER_URL}/api/games"
API_CHECK_EXISTS_ENDPOINT = f"{FLASK_SERVER_URL}/api/games/check_exists"
API_GET_SYSTEMS_ENDPOINT = f"{FLASK_SERVER_URL}/api/systems"

# These should match the ALLOWED_EXTENSIONS in your Flask app
# You might expand this list as needed for your roms/games
SCAN_ALLOWED_EXTENSIONS = {
    'exe', 'nes', 'bin', 'sfc', 'smc', 'gba', 'gbc', 'gb', 'iso', 'zip', 'rom',
    'md', # Sega Genesis
    'n64', # Nintendo 64
    'z64', # Nintendo 64
    'v64', # Nintendo 64
    'nds', # Nintendo DS
    'gba', # Game Boy Advance
    'ps1', 'cue', 'ccd', 'img', 'mdf', # PlayStation 1 (ISO/BIN/CUE variants)
    'chd', # Common for arcade/console CD images
    'dsk', # Amstrad CPC, ZX Spectrum, etc.
    'adf', # Amiga Disk File
    'atr', # Atari 8-bit
    'rom', # Generic ROM extension
}

# Mapping of file extensions to systems (expand this for better auto-detection)
# This is a basic example; you might need a more sophisticated mapping or user input.
EXTENSION_TO_SYSTEM_MAP = {
    'nes': 'Nintendo Entertainment System',
    'sfc': 'Super Nintendo',
    'smc': 'Super Nintendo',
    'gb': 'Game Boy',
    'gbc': 'Game Boy Color',
    'gba': 'Game Boy Advance',
    'n64': 'Nintendo 64',
    'z64': 'Nintendo 64',
    'v64': 'Nintendo 64',
    'iso': 'PlayStation 1', # Could also be PS2, PSP, etc. needs context
    'cue': 'PlayStation 1',
    ''md': 'Sega Genesis',
    'exe': 'Other', # Windows executables
    'zip': 'Other', # Can contain anything, user might specify system for zip
    'rom': 'Other', # Generic, needs user input
}

def clean_game_title_for_api(filename):
    """
    Cleans a filename to extract a searchable game title.
    This should ideally mirror the clean_game_title function in your app.py.
    """
    name = os.path.splitext(filename)[0]
    name = re.sub(r'\[.*?\]', '', name)   # Remove [USA], [Europe], etc.
    name = re.sub(r'\(.*?\)', '', name)   # Remove (v1.0), (Rev A), etc.
    name = re.sub(r'[_-]', ' ', name)     # Replace underscores and dashes with spaces
    name = re.sub(r'\s+', ' ', name).strip() # Clean up multiple spaces
    return name

def get_system_from_extension(extension):
    """Tries to guess the system based on file extension."""
    return EXTENSION_TO_SYSTEM_MAP.get(extension.lower(), 'Other')

def get_supported_systems():
    """Fetches the list of supported systems from the Flask server."""
    try:
        response = requests.get(API_GET_SYSTEMS_ENDPOINT)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching supported systems from server: {e}")
        return [] # Return empty list if server is unreachable or errors

def scan_folder(folder_path, systems_map=None, upload_folder_on_server=None):
    """
    Scans a given folder for game files and attempts to add them to the library.
    Args:
        folder_path (str): The root directory to start scanning from.
        systems_map (dict): A dictionary mapping system names to a canonical list.
        upload_folder_on_server (str): The path to the 'uploads' folder *on the server*.
                                       This is crucial for the `file_path` field.
    """
    print(f"Starting scan of: {folder_path}")
    found_files_count = 0
    added_games_count = 0
    skipped_games_count = 0
    
    if systems_map is None:
        systems_map = {} # Initialize if not provided

    for root, _, files in os.walk(folder_path):
        for filename in files:
            extension = filename.rsplit('.', 1)[-1].lower()
            if extension in SCAN_ALLOWED_EXTENSIONS:
                found_files_count += 1
                full_local_path = os.path.join(root, filename)
                
                # IMPORTANT: Construct the file_path as it would be *on the server*
                # This assumes your scanner runs on the same machine/file system
                # or that you've configured shared network drives.
                # If the scanner is on a different machine, you'd need a more complex
                # file transfer/mapping strategy.
                
                # We need to ensure the server's path matches how it stores files.
                # If you generally copy files to the UPLOAD_FOLDER on the server,
                # then the `file_path` sent to the API should reflect that path.
                
                # For this setup, assuming the scanner is run on the same machine
                # and the files are already in (or will be moved to) the server's UPLOAD_FOLDER structure.
                # If your UPLOAD_FOLDER is structured like:
                # /path/to/your/flask_app/uploads/<filename>
                # Then we should calculate the file_path relative to that base.
                # For simplicity, if `upload_folder_on_server` is provided, we assume files
                # are placed directly into it.
                
                # More robust way would be to make your Flask API handle the file upload itself.
                # But since your current /upload route is web-based, we're mimicking its DB insert here.
                
                # For mass scanning, it's common to *not* move files to the `uploads` folder
                # but rather just record their original location. If you want this, your
                # `UPLOAD_FOLDER` concept might need to be re-evaluated on the Flask side
                # to allow absolute paths, or you need to copy the files first.
                
                # Let's assume for this scanner that the games will reside at their
                # current 'full_local_path' and your Flask app can access them there.
                # So, we'll send the full_local_path directly as the file_path.
                # Your Flask app's `uploaded_file` route currently serves from `UPLOAD_FOLDER`,
                # so if you use this, you'll need to modify `uploaded_file` to serve arbitrary paths
                # or ensure the scanner *copies* files to `UPLOAD_FOLDER` first.
                
                # **Crucial Decision Point:**
                # 1. Scanner provides *absolute path* to existing files. Flask serves from there.
                #    - Requires `uploaded_file` route to be more flexible, or direct path access from client.
                # 2. Scanner *uploads* files to Flask's `UPLOAD_FOLDER` via a new API endpoint.
                #    - Requires Flask API to handle file reception, which is more complex but robust.
                
                # Given your existing `app.py` has `UPLOAD_FOLDER` and `filepath` is always inside it,
                # for the scanner to work without file transfer, the `file_path` in the DB
                # must match where the file *actually* is on the server's file system.
                # Let's make a simplified assumption: the scanner is run on the same machine
                # as the Flask app and can access the files directly. We'll store the
                # full local path from the scan.
                
                # If you want to store copies in the `uploads` folder via this scanner,
                # you'd need to add a file upload mechanism to the Flask API.
                
                # For now, let's assume `file_path` is the absolute path found by the scanner.
                # This means `uploaded_file` route might need adjustment or you manually access the path.
                
                game_file_path = full_local_path 

                # Check if game already exists in the library
                try:
                    check_response = requests.get(API_CHECK_EXISTS_ENDPOINT, params={'file_path': game_file_path})
                    check_response.raise_for_status()
                    if check_response.json().get('exists'):
                        print(f"Skipping '{filename}': Already in library.")
                        skipped_games_count += 1
                        continue
                except requests.exceptions.RequestException as e:
                    print(f"Error checking existence for '{filename}': {e}")
                    continue # Skip this game if check fails

                game_title = clean_game_title_for_api(filename)
                guessed_system = get_system_from_extension(extension)
                
                # If the guessed system isn't one of the supported ones,
                # try to find a close match or default to 'Other'
                final_system = 'Other'
                if guessed_system in systems_map:
                    final_system = guessed_system
                elif guessed_system != 'Other': # Try to find a partial match
                    for s in systems_map:
                        if guessed_system.lower() in s.lower():
                            final_system = s
                            break
                print(f"Found '{filename}' (Title: '{game_title}', System: '{final_system}')")

                game_data = {
                    'filename': filename,
                    'title': game_title,
                    'system': final_system,
                    'file_path': game_file_path,
                    # Add other metadata here if you can infer it (e.g., description, cover_url)
                    # For a scanner, it's often better to let the server's auto_find_game_details
                    # fill this in after the basic entry is made.
                    'description': '', # Leave empty for now, let server fetch
                    'cover_url': ''    # Leave empty for now, let server fetch
                }

                try:
                    response = requests.post(API_ADD_GAME_ENDPOINT, json=game_data)
                    response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
                    result = response.json()
                    print(f"  -> Added '{filename}': {result.get('message')}")
                    added_games_count += 1
                except requests.exceptions.HTTPError as e:
                    print(f"  -> Failed to add '{filename}': HTTP Error {e.response.status_code} - {e.response.json().get('error', e.response.text)}")
                except requests.exceptions.RequestException as e:
                    print(f"  -> Network error adding '{filename}': {e}")
                
    print("\n--- Scan Summary ---")
    print(f"Files found: {found_files_count}")
    print(f"Games added to library: {added_games_count}")
    print(f"Games already in library (skipped): {skipped_games_count}")
    print(f"Scan complete for: {folder_path}")

if __name__ == '__main__':
    import re # Ensure re is imported if not already

    parser = argparse.ArgumentParser(description="Scan folders for games and add them to the Flask Game Library.")
    parser.add_argument('scan_path', type=str, 
                        help='The path to the folder to scan (e.g., /Volumes/Roms/Nintendo or C:\\Games)')
    args = parser.parse_args()

    # Get supported systems from the server to validate input
    supported_systems_list = get_supported_systems()
    supported_systems_set = set(supported_systems_list) # For quick lookups

    if not supported_systems_list:
        print("Could not retrieve supported systems from the Flask server. Please ensure the server is running.")
    else:
        print(f"Supported systems from server: {', '.join(supported_systems_list)}")
        # Start the scan
        scan_folder(args.scan_path, supported_systems_set)
        
        # After scanning and adding, you might want to trigger the metadata scan
        # on the server to fill in covers and descriptions for newly added games.
        # This can be done by making another API call to your /scan_covers route.
        print("\nTriggering server's metadata scan for newly added games...")
        try:
            requests.get(f"{FLASK_SERVER_URL}/scan_covers") # Make sure this route is accessible
            print("Server metadata scan triggered successfully.")
        except requests.exceptions.RequestException as e:
            print(f"Error triggering server metadata scan: {e}")