import os
import sqlite3
import json
import requests
import re
from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
# IMPORTANT: Change this to a strong, random key in production!
app.secret_key = 'your_super_secret_key_here_please_change_me_in_production'

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'exe', 'nes', 'bin', 'sfc', 'smc', 'gba', 'gbc', 'gb', 'iso', 'zip', 'rom'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# New: Configuration for custom cover uploads
COVER_UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'covers')
app.config['COVER_UPLOAD_FOLDER'] = COVER_UPLOAD_FOLDER
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} # Add more if needed

# API Configuration (will be loaded from config file)
API_CONFIG = {}
CONFIG_FILE = 'api_config.json' # This file will store your IGDB/Google API keys

# Load API configuration from api_config.json
def load_api_config():
    global API_CONFIG
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                API_CONFIG = json.load(f)
        except json.JSONDecodeError:
            # Handle empty or invalid JSON file
            print(f"Warning: {CONFIG_FILE} is empty or invalid. Reinitializing config.")
            API_CONFIG = {
                'igdb_client_id': '',
                'igdb_client_secret': '',
                'igdb_access_token': '',
                'google_api_key': '',
                'google_cx': ''
            }
            save_api_config() # Save default empty config
    else:
        # Create default config if file doesn't exist
        API_CONFIG = {
            'igdb_client_id': '',
            'igdb_client_secret': '',
            'igdb_access_token': '',
            'google_api_key': '',
            'google_cx': ''
        }
        save_api_config()

def save_api_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(API_CONFIG, f, indent=2)

# Supported systems
SYSTEMS = [
    'Super Nintendo', 'Nintendo Entertainment System', 'Game Boy', 'Game Boy Color',
    'Game Boy Advance', 'Nintendo 64', 'PlayStation 1', 'PlayStation 2',
    'Sega Genesis', 'Sega Master System', 'Atari 2600', 'Other'
]

# Available themes
THEMES = {
    'modern': {'name': 'Modern', 'description': 'Clean, modern interface'},
    'crt': {'name': 'Retro CRT', 'description': 'Classic CRT TV interface with scanlines'},
    'arcade': {'name': 'Arcade Cabinet', 'description': 'Retro arcade machine style'}
}

# Database functions
def get_db_connection():
    conn = sqlite3.connect('games.db')
    conn.row_factory = sqlite3.Row # This allows access to columns by name
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS games
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      filename TEXT NOT NULL,
                      title TEXT NOT NULL,
                      description TEXT,
                      release_date TEXT,
                      genre TEXT,
                      rating REAL,
                      cover_url TEXT,
                      upload_date TEXT,
                      system TEXT,
                      file_path TEXT)''')
    
    # Settings table for user preferences
    conn.execute('''CREATE TABLE IF NOT EXISTS settings
                     (key TEXT PRIMARY KEY,
                      value TEXT)''')
    
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = get_db_connection()
    result = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return result['value'] if result else default

def set_setting(key, value):
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

# Cover art and description functions
def clean_game_title(filename):
    """Extract clean game title from filename for API searches"""
    name = os.path.splitext(filename)[0]
    name = re.sub(r'\[.*?\]', '', name)   # Remove [USA], [Europe], etc.
    name = re.sub(r'\(.*?\)', '', name)   # Remove (v1.0), (Rev A), etc.
    name = re.sub(r'[_-]', ' ', name)     # Replace underscores and dashes with spaces
    name = re.sub(r'\s+', ' ', name).strip() # Clean up multiple spaces
    return name

def get_igdb_access_token():
    """Get IGDB access token using client credentials from Twitch"""
    if not API_CONFIG.get('igdb_client_id') or not API_CONFIG.get('igdb_client_secret'):
        print("IGDB client ID or secret missing in config.")
        return None
        
    url = 'https://id.twitch.tv/oauth2/token' # Fixed Twitch URL
    data = {
        'client_id': API_CONFIG['igdb_client_id'],
        'client_secret': API_CONFIG['igdb_client_secret'],
        'grant_type': 'client_credentials'
    }
    
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            token_data = response.json()
            API_CONFIG['igdb_access_token'] = token_data['access_token']
            save_api_config() # Save the newly fetched token
            print("Successfully fetched new IGDB access token.")
            return token_data['access_token']
        else:
            print(f"Error getting IGDB token: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Network error getting IGDB token: {e}")
    except Exception as e:
        print(f"An unexpected error occurred getting IGDB token: {e}")
    return None

def get_game_details_from_igdb(game_title, system=None):
    """
    Search for game details (cover, description) using IGDB API.
    Returns a dictionary with 'cover_url' and 'description' or None.
    """
    access_token = API_CONFIG.get('igdb_access_token')
    
    # If token is missing or expired, try to get a new one
    if not access_token:
        access_token = get_igdb_access_token()
    
    if not access_token:
        print("IGDB access token not available.")
        return None
    
    headers = {
        'Client-ID': API_CONFIG.get('igdb_client_id', ''),
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    
    # IGDB query to search for games and get cover image_id and summary (description)
    # We prioritize exact match by phrase, then general search
    # Note: 'summary' is the description field in IGDB
    search_query = f'''
    search "{game_title}";
    fields name, summary, cover.image_id;
    limit 1;
    '''
    
    game_details = {'cover_url': None, 'description': None}

    try:
        response = requests.post('https://api.igdb.com/v4/games', 
                                 headers=headers, data=search_query)
        
        if response.status_code == 200:
            games = response.json()
            if games:
                game_data = games[0]
                
                if game_data.get('cover'):
                    image_id = game_data['cover']['image_id']
                    game_details['cover_url'] = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"
                
                if game_data.get('summary'):
                    game_details['description'] = game_data['summary']
                
                print(f"Found IGDB details for '{game_title}': Cover: {game_details['cover_url'] != None}, Description: {game_details['description'] != None}")
                return game_details
                
        elif response.status_code == 401: # Unauthorized, likely token expired
            print("IGDB token expired or invalid. Attempting to refresh.")
            API_CONFIG['igdb_access_token'] = '' # Clear old token
            save_api_config()
            # Recursively call to get new token and retry search (only once)
            return get_game_details_from_igdb(game_title, system) 
        else:
            print(f"IGDB search API error for '{game_title}': {response.status_code} - {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"Network error during IGDB search for '{game_title}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred during IGDB search for '{game_title}': {e}")
    
    return None

def search_google_images(game_title, system=None):
    """Fallback: Search Google Custom Search for cover art"""
    api_key = API_CONFIG.get('google_api_key')
    cx = API_CONFIG.get('google_cx')
    
    if not api_key or not cx:
        print("Google API Key or CX missing in config.")
        return None
    
    search_query = f"{game_title} {system if system else ''} game cover art"
    url = "https://www.googleapis.com/customsearch/v1"
    
    params = {
        'key': api_key,
        'cx': cx,
        'q': search_query,
        'searchType': 'image',
        'num': 1,
        'imgType': 'photo',
        'imgSize': 'medium'
    }
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get('items'):
                return data['items'][0]['link']
        else:
            print(f"Google Custom Search API error: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Network error during Google search: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during Google search: {e}")
    
    return None

def auto_find_game_details(game_title, system=None):
    """
    Try multiple sources to find game details (cover art and description).
    Returns a dictionary with 'cover_url' and 'description' or None.
    """
    
    # Try IGDB first for both cover and description
    igdb_details = get_game_details_from_igdb(game_title, system)
    if igdb_details:
        return igdb_details
    
    # If IGDB failed or didn't provide everything, try Google for just the cover as fallback
    print(f"IGDB failed for '{game_title}'. Trying Google for cover...")
    google_cover = search_google_images(game_title, system)
    
    # If Google found a cover, return it with a None description (since Google CS is only for images here)
    if google_cover:
        return {'cover_url': google_cover, 'description': None}
        
    print(f"Could not find any details (cover or description) for {game_title} from any source.")
    return None

# File handling
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

# --- ROUTES ---

@app.route('/')
def index():
    theme = get_setting('theme', 'modern')
    conn = get_db_connection()
    # Fetch a limited number of recent games for the home page, if desired, or all games
    games = conn.execute('SELECT * FROM games ORDER BY upload_date DESC LIMIT 12').fetchall() # Displaying recent 12 games
    conn.close()
    return render_template('index.html', games=games, systems=SYSTEMS, theme=theme, themes=THEMES, datetime=datetime)

@app.route('/library')
def library():
    theme = get_setting('theme', 'modern')
    conn = get_db_connection()
    games = conn.execute('SELECT * FROM games ORDER BY title').fetchall()
    conn.close()
    return render_template('library.html', games=games, systems=SYSTEMS, theme=theme, themes=THEMES, datetime=datetime)

@app.route('/upload', methods=['GET', 'POST'])
def upload_game():
    theme = get_setting('theme', 'modern')
    if request.method == 'POST':
        uploaded_files = request.files.getlist('file[]') # Get all files from the 'file[]' input
        
        if not uploaded_files or uploaded_files[0].filename == '': # Check if any files were actually selected
            flash('No files selected for upload.', 'error')
            return redirect(request.url)

        # Get metadata that applies to all files in this batch (for simplicity)
        batch_title_prefix = request.form['title'].strip() # Optional: prefix for titles
        # batch_description is now potentially overwritten by auto-finding
        initial_batch_description = request.form.get('description', '') 
        batch_system = request.form['system']
        batch_auto_metadata_toggle = request.form.get('auto_metadata_toggle', 'off') == 'on' # New toggle

        uploaded_count = 0
        failed_uploads = []

        for file in uploaded_files:
            if file.filename == '':
                continue # Skip empty file fields

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                if os.path.exists(filepath):
                    failed_uploads.append(f'"{filename}" (already exists)')
                    continue # Skip to next file

                try:
                    file.save(filepath)
                    
                    # Determine game title for this specific file
                    current_game_title = batch_title_prefix
                    if not current_game_title: # If prefix was blank, derive from filename
                        current_game_title = clean_game_title(filename)
                    elif len(uploaded_files) > 1: # If multiple files, append filename part to prefix
                        name_without_ext = os.path.splitext(filename)[0]
                        current_game_title = f"{batch_title_prefix} - {name_without_ext}"

                    # Initialize cover_url and description
                    cover_url = ''
                    description = initial_batch_description # Start with user-provided batch description

                    if batch_auto_metadata_toggle: # Use the new combined auto-detection
                        found_details = auto_find_game_details(current_game_title, batch_system)
                        if found_details:
                            if found_details['cover_url']:
                                cover_url = found_details['cover_url']
                            if found_details['description']:
                                description = found_details['description'] # Overwrite if found
                        else:
                            print(f'Warning: Could not find auto metadata for "{current_game_title}"') # Log, but don't flash for every one in batch
                    
                    conn = get_db_connection()
                    try:
                        conn.execute('INSERT INTO games (filename, title, description, system, file_path, upload_date, cover_url) VALUES (?, ?, ?, ?, ?, ?, ?)',
                                     (filename, current_game_title, description, batch_system, filepath, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), cover_url))
                        conn.commit()
                        uploaded_count += 1
                    except sqlite3.Error as e:
                        print(f'Database error for {filename}: {e}') # Log database errors
                        failed_uploads.append(f'"{filename}" (DB error)')
                        if os.path.exists(filepath): # Clean up file if DB insert fails
                            os.remove(filepath)
                    finally:
                        conn.close()

                except Exception as e: # Catch any other file saving errors
                    failed_uploads.append(f'"{filename}" (Save error: {e})')
                    print(f"Error saving file {filename}: {e}")
            else:
                failed_uploads.append(f'"{file.filename}" (invalid type)')
        
        if uploaded_count > 0:
            flash(f'Successfully uploaded {uploaded_count} game(s)!', 'success')
        if failed_uploads:
            flash(f'Failed to upload: {", ".join(failed_uploads)}.', 'error')
        
        return redirect(url_for('library')) # Redirect to library after processing all files
    
    return render_template('upload.html', systems=SYSTEMS, theme=theme, themes=THEMES, datetime=datetime)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    current_theme = get_setting('theme', 'modern') # Get current theme from DB
    
    if request.method == 'POST':
        new_theme = request.form.get('theme', 'modern')
        set_setting('theme', new_theme)
        
        API_CONFIG['igdb_client_id'] = request.form.get('igdb_client_id', '')
        API_CONFIG['igdb_client_secret'] = request.form.get('igdb_client_secret', '')
        API_CONFIG['google_api_key'] = request.form.get('google_api_key', '')
        API_CONFIG['google_cx'] = request.form.get('google_cx', '')
        save_api_config()
        
        flash('Settings saved successfully!', 'success')
        return redirect(url_for('settings'))
    
    return render_template('settings.html', 
                            theme=current_theme, 
                            themes=THEMES, 
                            api_config=API_CONFIG, 
                            datetime=datetime)

@app.route('/edit/<int:game_id>', methods=['GET', 'POST'])
def edit_game(game_id):
    theme = get_setting('theme', 'modern')
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    
    if game is None:
        flash('Game not found!', 'error')
        conn.close()
        return redirect(url_for('library'))

    # Determine the cover_url to display in the text field for external URLs only
    display_cover_url = ''
    if game['cover_url']: # Check if there's any cover_url at all
        # Convert to string to be absolutely safe (though it should be string or None from DB)
        current_cover_str = str(game['cover_url']) 
        # If it's not a locally uploaded cover (starts with /static/covers/), display it
        if not current_cover_str.startswith('/static/covers/'):
            display_cover_url = current_cover_str

    if request.method == 'POST':
        title = request.form['title']
        system = request.form['system']
        description = request.form['description'] # Get description from form
        
        # --- Handle Custom Cover Upload FIRST ---
        new_cover_file = request.files.get('cover_file')
        uploaded_cover_url = None
        if new_cover_file and new_cover_file.filename != '' and allowed_image_file(new_cover_file.filename):
            try:
                # Delete old custom cover if it exists and is from our uploads
                if game['cover_url'] and str(game['cover_url']).startswith('/static/covers/'): # Ensure str() conversion for safety
                    old_cover_filename = os.path.basename(game['cover_url'])
                    old_cover_path = os.path.join(app.config['COVER_UPLOAD_FOLDER'], old_cover_filename)
                    if os.path.exists(old_cover_path):
                        os.remove(old_cover_path)
                        print(f"Removed old cover: {old_cover_path}")

                cover_filename_secured = secure_filename(new_cover_file.filename)
                # Use game ID and a timestamp to ensure unique filenames for custom covers, preventing clashes
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                final_cover_filename = f"game_{game_id}_{timestamp}_{cover_filename_secured}"
                cover_path = os.path.join(app.config['COVER_UPLOAD_FOLDER'], final_cover_filename)
                new_cover_file.save(cover_path)
                
                # Construct URL relative to static folder
                uploaded_cover_url = url_for('static', filename=f'covers/{final_cover_filename}')
                flash(f'Custom cover "{new_cover_file.filename}" uploaded!', 'success')
            except Exception as e:
                flash(f'Error uploading custom cover: {e}', 'error')
        
        # --- Determine final cover_url and description based on different inputs ---
        cover_url = game['cover_url'] # Start with existing cover
        # description is taken from request.form directly unless auto_metadata_toggle is on

        if uploaded_cover_url: # If a new file was uploaded, use that for cover
            cover_url = uploaded_cover_url
        elif request.form.get('cover_url_cleared') == 'true': # If JS signaled removal
            # Delete associated custom cover file if it exists
            if game['cover_url'] and str(game['cover_url']).startswith('/static/covers/'): # Ensure str() conversion for safety
                old_cover_filename = os.path.basename(game['cover_url'])
                old_cover_path = os.path.join(app.config['COVER_UPLOAD_FOLDER'], old_cover_filename)
                if os.path.exists(old_cover_path):
                    os.remove(old_cover_path)
                    print(f"Removed cover on clear: {old_cover_path}")
            cover_url = ''
            flash('Cover art removed successfully!', 'success')
        
        # Handle auto-metadata *after* checking explicit uploads/clears for cover
        if request.form.get('auto_metadata_toggle', 'off') == 'on': # New toggle for all metadata
            # Pass original game title as found in DB, or use the new form title if available and different
            search_title_for_auto = title if title else game['title']
            auto_details = auto_find_game_details(search_title_for_auto, system)
            if auto_details:
                if auto_details['cover_url']:
                    cover_url = auto_details['cover_url'] # Overwrite existing cover if found
                if auto_details['description']:
                    description = auto_details['description'] # Overwrite form description if found
                flash('Found and updated metadata automatically!', 'info')
            else:
                flash('Could not find metadata automatically', 'warning')
        else: # If auto-metadata is NOT toggled on, then use the URL from the form text field
            # This applies if no new file uploaded and auto-detect is off
            if not uploaded_cover_url and request.form.get('cover_url_cleared') != 'true':
                 cover_url = request.form['cover_url'].strip() # Get the URL from the text input


        try:
            conn.execute('UPDATE games SET title = ?, system = ?, description = ?, cover_url = ? WHERE id = ?',
                         (title, system, description, cover_url, game_id))
            conn.commit()
            flash('Game updated successfully!', 'success')
            return redirect(url_for('library'))
        except sqlite3.Error as e:
            flash(f'Database error: {e}', 'error')
            # If there's a DB error, re-render the edit page with current data and error
            conn.close() # Close connection before re-rendering
            return render_template(
                'edit.html',
                game=game, # Pass the original game object or re-fetch if needed
                systems=SYSTEMS,
                theme=theme,
                themes=THEMES, # Ensure themes is passed
                datetime=datetime, # Ensure datetime is passed here on error re-render
                display_cover_url=display_cover_url # Keep original or update as per logic
            )
        finally:
            pass # conn.close() moved to specific branches

    conn.close()
    return render_template(
        'edit.html',
        game=game,
        systems=SYSTEMS,
        theme=theme,
        themes=THEMES, # Pass THEMES here
        datetime=datetime, # Pass datetime here
        display_cover_url=display_cover_url
    )


@app.route('/game/<int:game_id>')
def game_detail(game_id):
    """Displays a detailed page for a single game."""
    theme = get_setting('theme', 'modern')
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    conn.close()

    if game is None:
        flash('Game not found!', 'error')
        return redirect(url_for('library'))
    
    return render_template(
        'game_detail.html',
        game=game,
        systems=SYSTEMS, # Pass systems if you want to display system name differently or in a dropdown
        theme=theme,
        themes=THEMES,
        datetime=datetime # For footer year
    )


@app.route('/delete/<int:game_id>')
def delete_game(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    if game:
        # Delete the associated game file from the uploads folder
        if os.path.exists(game['file_path']):
            try:
                os.remove(game['file_path'])
                flash(f'Game file "{os.path.basename(game["file_path"])}" deleted.', 'info')
            except OSError as e:
                flash(f'Error deleting file: {e}', 'error')
        
        # Delete the associated custom cover file if it exists and is from our uploads
        if game['cover_url'] and str(game['cover_url']).startswith('/static/covers/'): # Ensure str() conversion for safety
            cover_filename = os.path.basename(game['cover_url'])
            cover_path = os.path.join(app.config['COVER_UPLOAD_FOLDER'], cover_filename)
            if os.path.exists(cover_path):
                try:
                    os.remove(cover_path)
                    flash(f'Custom cover file "{cover_filename}" deleted.', 'info')
                except OSError as e:
                    flash(f'Error deleting cover file: {e}', 'error')

        # Delete the record from the database
        conn.execute('DELETE FROM games WHERE id = ?', (game_id,))
        conn.commit()
        flash('Game deleted successfully!', 'success')
    else:
        flash('Game not found!', 'error')
    conn.close()
    return redirect(url_for('library')) # Redirect to library

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded game files from the UPLOAD_FOLDER"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/scan_covers') # This route name is now a bit misleading, it's for all missing metadata
def scan_covers():
    """Scan all games without covers/descriptions and try to find them using APIs"""
    conn = get_db_connection()
    # Select games that are missing either cover or description
    games_to_update = conn.execute('SELECT * FROM games WHERE cover_url IS NULL OR cover_url = "" OR description IS NULL OR description = ""').fetchall()
    
    updated_count = 0
    for game in games_to_update:
        clean_title = game['title'] if game['title'] else clean_game_title(game['filename'])
        
        found_details = auto_find_game_details(clean_title, game['system'])
        
        if found_details:
            update_query = []
            update_params = []

            # Only update if current is null/empty AND new one is found
            if (not game['cover_url'] or game['cover_url'] == "") and found_details['cover_url']:
                update_query.append('cover_url = ?')
                update_params.append(found_details['cover_url'])
            
            if (not game['description'] or game['description'] == "") and found_details['description']:
                update_query.append('description = ?')
                update_params.append(found_details['description'])
            
            if update_query: # Only update if there's something to update
                update_params.append(game['id'])
                conn.execute(f'UPDATE games SET {", ".join(update_query)} WHERE id = ?', tuple(update_params))
                updated_count += 1
                print(f"Updated metadata for {game['title']}") # Debug print
    
    conn.commit()
    conn.close()
    
    flash(f'Updated metadata (covers/descriptions) for {updated_count} games!', 'info')
    return redirect(url_for('library')) # Redirect to library

# Initialize database and load config on app startup
load_api_config()
init_db()

if __name__ == '__main__':
    # Create upload directory if it doesn't exist
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    # Create cover upload directory if it doesn't exist
    if not os.path.exists(COVER_UPLOAD_FOLDER):
        os.makedirs(COVER_UPLOAD_FOLDER)
    app.run(debug=True, host='0.0.0.0', port=5000)