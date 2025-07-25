## Game Library Server - Enhanced Flask Application
import os
import sqlite3
import json
import requests
import re
from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash, session, jsonify # Combined jsonify
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_change_this'

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'exe', 'nes', 'bin', 'sfc', 'smc', 'gba', 'gbc', 'gb', 'iso', 'zip', 'rom'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# API Configuration (will be loaded from config file)
API_CONFIG = {}
CONFIG_FILE = 'api_config.json'

# Load API configuration
def load_api_config():
    global API_CONFIG
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            API_CONFIG = json.load(f)
    else:
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
    'Super Nintendo',
    'Nintendo Entertainment System', 
    'Game Boy',
    'Game Boy Color',
    'Game Boy Advance',
    'Nintendo 64',
    'PlayStation 1',
    'PlayStation 2',
    'Sega Genesis',
    'Sega Master System',
    'Atari 2600',
    'Other'
]

# Available themes
THEMES = {
    'modern': {
        'name': 'Modern',
        'description': 'Clean, modern interface'
    },
    'crt': {
        'name': 'Retro CRT',
        'description': 'Classic CRT TV interface with scanlines'
    },
    'arcade': {
        'name': 'Arcade Cabinet',
        'description': 'Retro arcade machine style'
    }
}

# Database functions
def get_db_connection():
    conn = sqlite3.connect('games.db')
    conn.row_factory = sqlite3.Row
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

# Cover art functions
def clean_game_title(filename):
    """Extract clean game title from filename"""
    # Remove file extension
    name = os.path.splitext(filename)[0]
    
    # Remove common ROM suffixes and brackets
    name = re.sub(r'\[.*?\]', '', name)  # Remove [USA], [Europe], etc.
    name = re.sub(r'\(.*?\)', '', name)  # Remove (v1.0), (Rev A), etc.
    name = re.sub(r'[_-]', ' ', name)    # Replace underscores and dashes with spaces
    name = re.sub(r'\s+', ' ', name).strip()  # Clean up multiple spaces
    
    return name

def get_igdb_access_token():
    """Get IGDB access token using client credentials"""
    if not API_CONFIG.get('igdb_client_id') or not API_CONFIG.get('igdb_client_secret'):
        return None
        
    url = 'https://id.twitch.tv/oauth2/token'
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
            save_api_config()
            return token_data['access_token']
    except Exception as e:
        print(f"Error getting IGDB token: {e}")
    
    return None

def search_igdb_cover(game_title, system=None):
    """Search for game cover using IGDB API"""
    access_token = API_CONFIG.get('igdb_access_token')
    if not access_token:
        access_token = get_igdb_access_token()
    
    if not access_token:
        return None
    
    headers = {
        'Client-ID': API_CONFIG.get('igdb_client_id', ''),
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    
    # Search for the game
    search_query = f'''
    search "{game_title}";
    fields name, cover.image_id, cover.url;
    limit 1;
    '''
    
    try:
        response = requests.post('https://api.igdb.com/v4/games', 
                               headers=headers, data=search_query)
        
        if response.status_code == 200:
            games = response.json()
            if games and games[0].get('cover'):
                # IGDB returns image_id, we need to construct the full URL
                image_id = games[0]['cover']['image_id']
                return f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"
                
    except Exception as e:
        print(f"IGDB search error: {e}")
    
    return None

def search_google_images(game_title, system=None):
    """Fallback: Search Google Custom Search for cover art"""
    api_key = API_CONFIG.get('google_api_key')
    cx = API_CONFIG.get('google_cx')
    
    if not api_key or not cx:
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
    except Exception as e:
        print(f"Google search error: {e}")
    
    return None

def auto_find_cover_art(game_title, system=None):
    """Try multiple sources to find cover art"""
    # Try IGDB first
    cover_url = search_igdb_cover(game_title, system)
    if cover_url:
        return cover_url
    
    # Fallback to Google Images
    cover_url = search_google_images(game_title, system)
    if cover_url:
        return cover_url
    
    return None

# File handling
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route('/')
def index():
    theme = get_setting('theme', 'modern')
    conn = get_db_connection()
    games = conn.execute('SELECT * FROM games ORDER BY upload_date DESC').fetchall()
    conn.close()
    return render_template(f'index_{theme}.html', games=games, systems=SYSTEMS, theme=theme, themes=THEMES)

@app.route('/api/games')
def api_games():
    # Replace this with a real query from your database or file
    sample_games = [
        {'id': 1, 'title': 'Zelda', 'system': 'NES', 'upload_date': '1987', 'cover_url': ''},
        {'id': 2, 'title': 'Halo', 'system': 'Xbox', 'upload_date': '2001', 'cover_url': ''},
        {'id': 3, 'title': 'Final Fantasy VII', 'system': 'PlayStation', 'upload_date': '1997', 'cover_url': ''}
    ]
    return jsonify(sample_games)
@app.route('/system/<system_name>')
def system_games(system_name):
    theme = get_setting('theme', 'modern')
    conn = get_db_connection()
    games = conn.execute('SELECT * FROM games WHERE system = ? ORDER BY title', (system_name,)).fetchall()
    conn.close()
    return render_template(f'system_{theme}.html', games=games, system_name=system_name, systems=SYSTEMS, theme=theme, themes=THEMES)

@app.route('/upload', methods=['GET', 'POST'])
def upload_game():
    theme = get_setting('theme', 'modern')
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            title = request.form['title']
            system = request.form['system']
            description = request.form.get('description', '')
            auto_cover = request.form.get('auto_cover', 'off') == 'on'
            
            cover_url = ''
            if auto_cover:
                # Try to find cover art automatically
                clean_title = clean_game_title(filename) if not title else title
                cover_url = auto_find_cover_art(clean_title, system)
                if cover_url:
                    flash(f'Found cover art for "{clean_title}"!')
                else:
                    flash('Could not find cover art automatically')
            
            conn = get_db_connection()
            conn.execute('INSERT INTO games (filename, title, description, system, file_path, upload_date, cover_url) VALUES (?, ?, ?, ?, ?, ?, ?)',
                      (filename, title, description, system, filepath, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), cover_url))
            conn.commit()
            conn.close()
            
            flash('Game uploaded successfully!')
            return redirect(url_for('index'))
        else:
            flash('Invalid file type')
            return redirect(request.url)
    
    return render_template(f'upload_{theme}.html', systems=SYSTEMS, theme=theme, themes=THEMES)


@app.route('/search')
def search():
    query = request.args.get('query', '').lower()
    matched_games = [g for g in games if query in g.title.lower() or query in g.system.lower()]
    return render_template('search_results.html', games=matched_games, query=query)

@app.route('/game/<int:game_id>')
def game_detail(game_id):
    game = get_game_by_id(game_id)  # Replace with your lookup logic
    return render_template('game_detail.html', game=game)    

@app.route('/recent')
def recent():
    page = int(request.args.get('page', 1))
    per_page = 12
    start = (page - 1) * per_page
    end = start + per_page
    paged_games = games[start:end]
    return render_template('recent.html', games=paged_games, page=page)   


@app.route('/library')
def library():
    theme = get_setting('theme', 'modern') # Get current theme
    conn = get_db_connection()
    # Fetch all games from the database
    games = conn.execute('SELECT * FROM games ORDER BY title').fetchall() # You can change ORDER BY
    conn.close()
    
    # Pass games, systems, theme, and themes to the library template
    # Also pass the full list of themes as done in settings.html for consistency
    return render_template(f'library_{theme}.html', # Render the theme-specific library template
                           games=games, 
                           systems=SYSTEMS, 
                           theme=theme, 
                           themes=THEMES) 

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    theme = get_setting('theme', 'modern')
    
    if request.method == 'POST':
        # Update theme
        new_theme = request.form.get('theme', 'modern')
        set_setting('theme', new_theme)
        
        # Update API settings
        API_CONFIG['igdb_client_id'] = request.form.get('igdb_client_id', '')
        API_CONFIG['igdb_client_secret'] = request.form.get('igdb_client_secret', '')
        API_CONFIG['google_api_key'] = request.form.get('google_api_key', '')
        API_CONFIG['google_cx'] = request.form.get('google_cx', '')
        save_api_config()
        
        flash('Settings saved successfully!')
        return redirect(url_for('settings'))
    
    return render_template(f'settings_{theme}.html', 
                         theme=theme, 
                         themes=THEMES, 
                         api_config=API_CONFIG)

@app.route('/edit/<int:game_id>', methods=['GET', 'POST'])
def edit_game(game_id):
    theme = get_setting('theme', 'modern')
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    
    if request.method == 'POST':
        title = request.form['title']
        system = request.form['system']
        description = request.form['description']
        cover_url = request.form['cover_url']
        
        # Auto-search for cover art if requested
        if request.form.get('auto_cover', 'off') == 'on':
            auto_cover_url = auto_find_cover_art(title, system)
            if auto_cover_url:
                cover_url = auto_cover_url
                flash('Found and updated cover art!')
        
        conn.execute('UPDATE games SET title = ?, system = ?, description = ?, cover_url = ? WHERE id = ?',
                   (title, system, description, cover_url, game_id))
        conn.commit()
        conn.close()
        flash('Game updated successfully!')
        return redirect(url_for('manage_games'))
    
    conn.close()
    return render_template(f'edit_{theme}.html', game=game, systems=SYSTEMS, theme=theme, themes=THEMES)

@app.route('/delete/<int:game_id>')
def delete_game(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    if game:
        if os.path.exists(game['file_path']):
            os.remove(game['file_path'])
        conn.execute('DELETE FROM games WHERE id = ?', (game_id,))
        conn.commit()
    conn.close()
    flash('Game deleted successfully!')
    return redirect(url_for('manage_games'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/scan_covers')
def scan_covers():
    """Scan all games without covers and try to find them"""
    conn = get_db_connection()
    games_without_covers = conn.execute('SELECT * FROM games WHERE cover_url IS NULL OR cover_url = ""').fetchall()
    
    found_count = 0
    for game in games_without_covers:
        clean_title = clean_game_title(game['filename']) if not game['title'] else game['title']
        cover_url = auto_find_cover_art(clean_title, game['system'])
        
        if cover_url:
            conn.execute('UPDATE games SET cover_url = ? WHERE id = ?', (cover_url, game['id']))
            found_count += 1
    
    conn.commit()
    conn.close()
    
    flash(f'Found cover art for {found_count} games!')
    return redirect(url_for('manage_games'))

# Initialize database and load config
load_api_config()
init_db()

if __name__ == '__main__':
    # Create upload directory
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True, host='0.0.0.0', port=5000)
