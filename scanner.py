# scanner.py (Updated Console Version)
import os
import requests
import json
import argparse
import re
import sys # Import sys for exiting gracefully

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
    'md': 'Sega Genesis',
    'nds': 'Nintendo DS',
    'exe': 'Other', # Windows executables
    'zip': 'Other', # Can contain anything, user might specify system for zip
    'rom': 'Other', # Generic, needs user input
    'chd': 'Arcade', # Often used for arcade ROMs
    'dsk': 'Other',
    'adf': 'Other',
    'atr': 'Other',
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
    print(f"Attempting to connect to Flask server at {FLASK_SERVER_URL} to get supported systems...")
    try:
        response = requests.get(API_GET_SYSTEMS_ENDPOINT)
        response.raise_for_status()  # Raise an exception for HTTP errors
        systems = response.json()
        print(f"Successfully retrieved supported systems: {', '.join(systems)}")
        return systems
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to Flask server at {FLASK_SERVER_URL}. Is it running?")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching supported systems from server: {e}")
        return [] # Return empty list if server is unreachable or errors

def scan_folder(folder_path, systems_map=None, progress_callback=None):
    """
    Scans a given folder for game files and attempts to add them to the library.
    Args:
        folder_path (str): The root directory to start scanning from.
        systems_map (set): A set of supported system names for validation.
        progress_callback (callable): Optional callback function to update GUI/console.
    """
    if not os.path.isdir(folder_path):
        print(f"Error: Scan path '{folder_path}' is not a valid directory.")
        if progress_callback:
            progress_callback(f"Error: Scan path '{folder_path}' is not a valid directory.", True)
        return

    print(f"Starting scan of: {folder_path}")
    if progress_callback:
        progress_callback(f"Starting scan of: {folder_path}")

    found_files_count = 0
    added_games_count = 0
    skipped_games_count = 0
    
    if systems_map is None:
        systems_map = set() # Initialize if not provided

    for root, _, files in os.walk(folder_path):
        for filename in files:
            extension = filename.rsplit('.', 1)[-1].lower()
            if extension in SCAN_ALLOWED_EXTENSIONS:
                found_files_count += 1
                full_local_path = os.path.join(root, filename)
                
                if progress_callback:
                    progress_callback(f"Processing: {filename}")

                # Check if game already exists in the library
                try:
                    check_response = requests.get(API_CHECK_EXISTS_ENDPOINT, params={'file_path': full_local_path})
                    check_response.raise_for_status()
                    if check_response.json().get('exists'):
                        print(f"Skipping '{filename}': Already in library.")
                        skipped_games_count += 1
                        if progress_callback:
                            progress_callback(f"  -> Skipping '{filename}': Already in library.", True)
                        continue
                except requests.exceptions.RequestException as e:
                    print(f"Error checking existence for '{filename}': {e}")
                    if progress_callback:
                        progress_callback(f"  -> Error checking existence for '{filename}': {e}", True)
                    continue # Skip this game if check fails

                game_title = clean_game_title_for_api(filename)
                guessed_system = get_system_from_extension(extension)
                
                # Validate guessed system against server's supported systems
                final_system = 'Other'
                if guessed_system in systems_map:
                    final_system = guessed_system
                else:
                    # Try to find a partial match or default to 'Other'
                    found_match = False
                    for s in systems_map:
                        if guessed_system.lower() in s.lower() or s.lower() in guessed_system.lower():
                            final_system = s
                            found_match = True
                            break
                    if not found_match:
                        print(f"Warning: Guessed system '{guessed_system}' not directly supported. Defaulting to 'Other' for '{filename}'.")
                        if progress_callback:
                            progress_callback(f"  -> Warning: Guessed system '{guessed_system}' not supported. Defaulting to 'Other'.", True)

                print(f"Found '{filename}' (Title: '{game_title}', System: '{final_system}')")
                if progress_callback:
                    progress_callback(f"  -> Found '{filename}' (Title: '{game_title}', System: '{final_system}')", True)


                game_data = {
                    'filename': filename,
                    'title': game_title,
                    'system': final_system,
                    'file_path': full_local_path, # Send the absolute path
                    'description': '', 
                    'cover_url': ''    
                }

                try:
                    response = requests.post(API_ADD_GAME_ENDPOINT, json=game_data)
                    response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
                    result = response.json()
                    print(f"  -> Added '{filename}': {result.get('message')}")
                    added_games_count += 1
                    if progress_callback:
                        progress_callback(f"  -> Added '{filename}': {result.get('message')}", True)
                except requests.exceptions.HTTPError as e:
                    error_msg = e.response.json().get('error', e.response.text)
                    print(f"  -> Failed to add '{filename}': HTTP Error {e.response.status_code} - {error_msg}")
                    if progress_callback:
                        progress_callback(f"  -> Failed to add '{filename}': {error_msg}", True)
                except requests.exceptions.RequestException as e:
                    print(f"  -> Network error adding '{filename}': {e}")
                    if progress_callback:
                        progress_callback(f"  -> Network error adding '{filename}': {e}", True)
                
    summary_message = f"\n--- Scan Summary ---\n" \
                      f"Files found: {found_files_count}\n" \
                      f"Games added to library: {added_games_count}\n" \
                      f"Games already in library (skipped): {skipped_games_count}\n" \
                      f"Scan complete for: {folder_path}"
    print(summary_message)
    if progress_callback:
        progress_callback(summary_message, True)

    # After scanning and adding, trigger the server's metadata scan
    print("\nTriggering server's metadata scan for newly added games...")
    if progress_callback:
        progress_callback("Triggering server's metadata scan for newly added games...")
    try:
        # Note: /scan_covers is a web route, not an API route designed for programmatic use.
        # It relies on redirecting. For a clean API call, you'd want a dedicated /api/scan_metadata endpoint.
        # For now, we'll hit the web route directly.
        requests.get(f"{FLASK_SERVER_URL}/scan_covers") 
        print("Server metadata scan triggered successfully.")
        if progress_callback:
            progress_callback("Server metadata scan triggered successfully.", True)
    except requests.exceptions.RequestException as e:
        print(f"Error triggering server metadata scan: {e}")
        if progress_callback:
            progress_callback(f"Error triggering server metadata scan: {e}", True)

# --- Console Entry Point ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Scan folders for games and add them to the Flask Game Library.")
    parser.add_argument('scan_path', type=str, nargs='?', # nargs='?' makes it optional
                        help='The path to the folder to scan (e.g., /Volumes/Roms/Nintendo or C:\\Games)')
    args = parser.parse_args()

    if not args.scan_path:
        print("Error: No scan path provided.")
        print("Usage: python scanner.py <path_to_folder>")
        sys.exit(1) # Exit with an error code

    # Get supported systems from the server to validate input
    supported_systems_list = get_supported_systems()
    if not supported_systems_list:
        print("Cannot proceed without knowing supported systems from the server. Ensure server is running and accessible.")
        sys.exit(1) # Exit if server is not reachable for systems list

    supported_systems_set = set(supported_systems_list) # For quick lookups

    # Start the scan
    scan_folder(args.scan_path, supported_systems_set)
    print("\nScanner finished. Press Enter to exit.")
    input() # Keep the console window open after completion