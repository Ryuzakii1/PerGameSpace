@echo off
:: Game Library Server Complete Installer for Windows

setlocal enabledelayedexpansion

echo ==========================================
echo Game Library Server Installer
echo ==========================================

:: Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo This script requires administrator privileges.
    echo Please run as Administrator.
    echo.
    pause
    exit /b 1
)

:: Set installation directory
set "INSTALL_DIR=%USERPROFILE%\GameLibraryServer"
set "PYTHON_URL=https://www.python.org/ftp/python/3.11.5/python-3.11.5-amd64.exe"
set "PYTHON_EXE=%TEMP%\python-installer.exe"

echo.
echo Installing to: %INSTALL_DIR%
echo.

:: Create installation directory
if not exist "%INSTALL_DIR%" (
    echo Creating directory: %INSTALL_DIR%
    mkdir "%INSTALL_DIR%"
)

echo Changing to directory: %INSTALL_DIR%
cd /d "%INSTALL_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to change directory to %INSTALL_DIR%
    pause
    exit /b 1
)

:: Ensure required folders exist before writing files
echo Creating required directories...
if not exist "templates" mkdir "templates"
if not exist "games" mkdir "games"
if not exist "db" mkdir "db"

:: Remove old database and games
echo Cleaning up old files...
if exist db\games.db del /Q db\games.db
if exist games rmdir /S /Q games
mkdir games

:: Check if Python is installed
echo.
echo Checking for Python installation...
where python >nul 2>&1
if %errorLevel% equ 0 (
    python --version 2>&1
    if %errorLevel% equ 0 (
        echo Python is working correctly
        for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
        echo Found Python !PYTHON_VERSION!
        set "PYTHON_CMD=python"
    ) else (
        goto install_python
    )
) else (
    goto install_python
)
goto skip_python_install

:install_python
echo.
echo Python not found. Installing Python 3.11.5...
powershell -Command "try { Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_EXE%' -UseBasicParsing } catch { Write-Host 'Download failed:' $_.Exception.Message; exit 1 }"
if %errorLevel% neq 0 (
    echo ERROR: Failed to download Python installer
    pause
    exit /b 1
)

echo Installing Python...
"%PYTHON_EXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1
if %errorLevel% neq 0 (
    echo ERROR: Python installation failed
    pause
    exit /b 1
)

if exist "%PYTHON_EXE%" del "%PYTHON_EXE%"
echo Python installation completed

:: Refresh PATH
for /f "skip=2 tokens=3*" %%a in ('reg query HKCU\Environment /v PATH') do set "USER_PATH=%%b"
for /f "skip=2 tokens=3*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH') do set "SYSTEM_PATH=%%b"
set "PATH=%USER_PATH%;%SYSTEM_PATH%"

:: Find Python executable
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) else if exist "%PROGRAMFILES%\Python311\python.exe" (
    set "PYTHON_CMD=%PROGRAMFILES%\Python311\python.exe"
) else (
    set "PYTHON_CMD=python"
)

:skip_python_install

:: Upgrade pip
echo.
echo Upgrading pip...
%PYTHON_CMD% -m pip install --upgrade pip

:: Create virtual environment
echo.
echo Creating virtual environment...
%PYTHON_CMD% -m venv venv
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment was not created properly!
    pause
    exit /b 1
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

:: Install required packages
echo.
echo Installing required packages...
venv\Scripts\python.exe -m pip install Flask==2.3.2 requests==2.31.0 Werkzeug==2.3.4
if %errorLevel% neq 0 (
    echo ERROR: Failed to install required packages
    pause
    exit /b 1
)

:: Create requirements.txt
echo Creating requirements.txt...
(
echo Flask==2.3.2
echo requests==2.31.0
echo Werkzeug==2.3.4
) > requirements.txt

:: Create Python files using a more reliable method
echo Creating Python application files...
powershell -Command "& {
$appContent = @'
# Game Library Server
from flask import Flask, request, render_template, send_file, redirect, url_for, flash
import os
import requests
import json
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'game-library-secret-key-change-in-production'

UPLOAD_FOLDER = 'games'
ALLOWED_EXTENSIONS = {
    'exe', 'zip', 'rar', 'iso', 'dmg',
    'nes', 'sfc', 'smc', 'gba', 'gb', 'gbc', 'nds', 'n64', 'z64',
    'bin', 'gen', 'smd', 'sms', 'gg', 'pce', 'cue'
}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('db', exist_ok=True)
os.makedirs('templates', exist_ok=True)

def init_db():
    conn = sqlite3.connect('db/games.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        filename TEXT NOT NULL,
        description TEXT,
        release_date TEXT,
        genre TEXT,
        rating REAL,
        cover_url TEXT,
        upload_date TEXT,
        system TEXT
    )''')
    conn.commit()
    conn.close()

CLIENT_ID = 'your_client_id_here'
CLIENT_SECRET = 'your_client_secret_here'
ACCESS_TOKEN = None

def get_access_token():
    global ACCESS_TOKEN
    if ACCESS_TOKEN:
        return ACCESS_TOKEN
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, params=params)
    if response.status_code == 200:
        ACCESS_TOKEN = response.json()['access_token']
        return ACCESS_TOKEN
    return None

def scrape_game_info(title):
    token = get_access_token()
    if not token:
        return {}
    url = 'https://api.igdb.com/v4/games'
    headers = {
        'Client-ID': CLIENT_ID,
        'Authorization': f'Bearer {token}'
    }
    data = f'fields name,summary,first_release_date,genres.name,rating,cover.url; search \"{title}\"; limit 1;'
    try:
        response = requests.post(url, headers=headers, data=data)
        if response.status_code == 200 and response.json():
            game = response.json()[0]
            return {
                'title': game.get('name', title),
                'description': game.get('summary', ''),
                'release_date': datetime.fromtimestamp(game['first_release_date']).strftime('%Y-%m-%d') if 'first_release_date' in game else '',
                'genre': ', '.join([g['name'] for g in game.get('genres', [])]),
                'rating': game.get('rating', 0),
                'cover_url': f\"https:{game['cover']['url']}\" if 'cover' in game else ''
            }
    except Exception as e:
        print(f\"Error scraping game info: {e}\")
    return {}

SYSTEM_MAP = {
    'nes': 'Nintendo Entertainment System',
    'sfc': 'Super Nintendo',
    'smc': 'Super Nintendo',
    'gba': 'Game Boy Advance',
    'gb': 'Game Boy',
    'gbc': 'Game Boy Color',
    'nds': 'Nintendo DS',
    'n64': 'Nintendo 64',
    'z64': 'Nintendo 64',
    'bin': 'Genesis',
    'gen': 'Genesis',
    'smd': 'Genesis',
    'sms': 'Sega Master System',
    'gg': 'Game Gear',
    'pce': 'PC Engine',
    'cue': 'PC Engine',
}

def detect_system(filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return SYSTEM_MAP.get(ext, 'Other')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    conn = sqlite3.connect('db/games.db')
    c = conn.cursor()
    c.execute('SELECT * FROM games ORDER BY upload_date DESC')
    games = c.fetchall()
    conn.close()
    systems = sorted(set(game[9] for game in games if game[9]))
    current_cat = request.args.get('cat', systems[0] if systems else 'Other')
    try:
        idx = systems.index(current_cat)
        prev_cat = systems[idx - 1] if idx > 0 else systems[-1]
        next_cat = systems[idx + 1] if idx < len(systems) - 1 else systems[0]
    except ValueError:
        prev_cat = next_cat = current_cat
    return render_template('index.html', games=games, current_cat=current_cat, prev_cat=prev_cat, next_cat=next_cat, system_index=9)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
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
            title = request.form.get('title', '').strip()
            if not title:
                title = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
            game_info = scrape_game_info(title)
            system = detect_system(filename)
            conn = sqlite3.connect('db/games.db')
            c = conn.cursor()
c.execute('''INSERT INTO games (filename, description, release_date, genre, rating, cover_url, upload_date, system)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
          (game_info.get('title', title), filename,
           game_info.get('description', ''),
           game_info.get('release_date', ''),
           game_info.get('genre', ''),
           game_info.get('rating', 0),
           game_info.get('cover_url', ''),
           datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
           system))
            conn.commit()
            conn.close()
            flash('Game uploaded successfully!')
            return redirect(url_for('index'))
        else:
            flash('Invalid file type. Allowed: ' + ', '.join(sorted(ALLOWED_EXTENSIONS)))
    return render_template('upload.html')

@app.route('/download/<int:game_id>')
def download(game_id):
    conn = sqlite3.connect('db/games.db')
    c = conn.cursor()
    c.execute('SELECT filename FROM games WHERE id = ?', (game_id,))
    result = c.fetchone()
    conn.close()
    if result:
        filename = result[0]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
    flash('Game not found')
    return redirect(url_for('index'))

@app.route('/delete/<int:game_id>')
def delete(game_id):
    conn = sqlite3.connect('db/games.db')
    c = conn.cursor()
    c.execute('SELECT filename FROM games WHERE id = ?', (game_id,))
    result = c.fetchone()
    if result:
        filename = result[0]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        c.execute('DELETE FROM games WHERE id = ?', (game_id,))
        conn.commit()
    conn.close()
    flash('Game deleted successfully!')
    return redirect(url_for('index'))

@app.route('/edit/<int:game_id>', methods=['GET', 'POST'])
def edit_game(game_id):
    conn = sqlite3.connect('db/games.db')
    c = conn.cursor()
    if request.method == 'POST':
        title = request.form['title']
        system = request.form['system']
        boxart = request.form['boxart']
        c.execute('UPDATE games SET title=?, system=?, cover_url=? WHERE id=?',
                  (title, system, boxart, game_id))
        conn.commit()
        conn.close()
        flash('Game updated!')
        return redirect(url_for('edit_game', game_id=game_id))
    else:
        c.execute('SELECT * FROM games WHERE id=?', (game_id,))
        game = c.fetchone()
        conn.close()
        return render_template('edit.html', game=game, systems=list(SYSTEM_MAP.values()))

@app.route('/scan_boxart/<int:game_id>', methods=['POST'])
def scan_boxart(game_id):
    conn = sqlite3.connect('db/games.db')
    c = conn.cursor()
    c.execute('SELECT title FROM games WHERE id=?', (game_id,))
    title = c.fetchone()[0]
    game_info = scrape_game_info(title)
    c.execute('UPDATE games SET cover_url=? WHERE id=?', (game_info.get('cover_url', ''), game_id))
    conn.commit()
    conn.close()
    flash('Boxart updated!')
    return redirect(url_for('edit_game', game_id=game_id))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
'@
Set-Content -Path 'app.py' -Value $appContent -Encoding UTF8
}"

echo Creating HTML templates...
powershell -Command "& {
$baseTemplate = @'
<!DOCTYPE html>
<html>
<head>
    <title>Game Library</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');
        html, body { height: 100%%; margin: 0; padding: 0; background: #181818; }
        body { font-family: 'VT323', 'Courier New', monospace; height: 100vh; width: 100vw; overflow: hidden; }
        .crt-outer { position: fixed; top: 0; left: 0; right: 0; bottom: 0; width: 100vw; height: 100vh; background: #222; display: flex; align-items: center; justify-content: center; }
        .crt-frame { position: relative; width: 100vw; height: 100vh; background: #222; border: 24px solid #666; border-radius: 48px; box-shadow: 0 0 80px #0ff, 0 0 0 16px #333 inset; overflow: hidden; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; }
        .crt-logo { position: absolute; bottom: 32px; left: 50%%; transform: translateX(-50%%); font-size: 2em; color: #0ff; text-shadow: 0 0 12px #0ff, 0 0 2px #fff; letter-spacing: 4px; font-family: 'VT323', monospace; pointer-events: none; user-select: none; }
        .crt-screen { position: absolute; top: 70px; left: 40px; right: 40px; bottom: 90px; background: #181818; border-radius: 32px; box-shadow: 0 0 32px #0ff inset; overflow-y: auto; z-index: 10; animation: crt-flicker 1.5s infinite alternate; padding: 20px; }
        .btn { background: #0ff; color: #000; border: none; padding: 8px 16px; margin: 4px; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; font-family: 'VT323', monospace; font-size: 1.2em; }
        .btn:hover { background: #fff; box-shadow: 0 0 8px #0ff; }
        .btn-success { background: #0f0; }
        .btn-success:hover { background: #5f5; }
        input, select, textarea { background: #222; color: #0ff; border: 1px solid #0ff; padding: 8px; margin: 4px; border-radius: 4px; font-family: 'VT323', monospace; font-size: 1.1em; width: 100%%; box-sizing: border-box; }
        label { color: #0ff; display: block; margin-top: 12px; font-size: 1.2em; }
        h1, h2, h3 { color: #0ff; text-align: center; text-shadow: 0 0 8px #0ff; }
        form { max-width: 500px; margin: 20px auto; padding: 20px; }
        .flash-messages { text-align: center; margin-bottom: 20px; }
        .flash-message { background: #333; color: #0ff; padding: 10px; margin: 5px 0; border-radius: 4px; border: 1px solid #0ff; }
        @keyframes crt-flicker { 0%% { opacity: 1; } 100%% { opacity: 0.98; } }
        .game-info { color: #ffd700; text-align: center; margin-bottom: 8px; }
        .game-description { color: #eee; text-align: center; max-width: 500px; margin: 0 auto; }
        .navigation { display: flex; justify-content: center; align-items: center; margin-bottom: 16px; }
        .category-name { margin: 0 24px; color: #ffd700; font-size: 1.3em; }
        .game-container { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 500px; }
        .boxart { width: 320px; height: 420px; object-fit: cover; border-radius: 18px; box-shadow: 0 0 32px #0ff, 0 0 0 8px #333 inset; z-index: 1; }
        .no-boxart { width: 320px; height: 420px; background: #222; color: #0ff; display: flex; align-items: center; justify-content: center; border-radius: 18px; font-size: 2em; box-shadow: 0 0 32px #0ff, 0 0 0 8px #333 inset; }
        .game-title { color: #0ff; margin: 18px 0 8px 0; text-align: center; text-shadow: 0 0 8px #0ff, 0 0 2px #fff; }
        .game-actions { margin-top: 12px; }
        .upload-link { text-align: center; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class=\"crt-outer\">
        <div class=\"crt-frame\">
            <div class=\"crt-screen\">
                {% with messages = get_flashed_messages() %}
                    {% if messages %}
                        <div class=\"flash-messages\">
                            {% for message in messages %}
                                <div class=\"flash-message\">{{ message }}</div>
                            {% endfor %}
                        </div>
                    {% endif %}
                {% endwith %}
                {% block content %}{% endblock %}
            </div>
            <div class=\"crt-logo\">RETROVISION</div>
        </div>
    </div>
</body>
</html>
'@
Set-Content -Path 'templates/base.html' -Value $baseTemplate -Encoding UTF8
}"

powershell -Command "& {
$indexTemplate = @'
{% extends \"base.html\" %}
{% block content %}
<h3>Game Collection</h3>
<div class=\"navigation\">
    <button onclick=\"window.location='?cat={{ prev_cat }}'\" class=\"btn\">&lt; Prev</button>
    <span class=\"category-name\">{{ current_cat }}</span>
    <button onclick=\"window.location='?cat={{ next_cat }}'\" class=\"btn\">Next &gt;</button>
</div>
<div class=\"upload-link\">
    <a href=\"{{ url_for('upload') }}\" class=\"btn btn-success\">Upload New Game</a>
</div>
{% set found = false %}
{% for game in games %}
    {% if game[system_index] == current_cat %}
        {% set found = true %}
        <div class=\"game-container\">
            {% if game[7] %}
                <img src=\"{{ game[7] }}\" alt=\"{{ game[1] }}\" class=\"boxart\">
            {% else %}
                <div class=\"no-boxart\">No Boxart</div>
            {% endif %}
            <h2 class=\"game-title\">{{ game[1] }}</h2>
            <div class=\"game-info\">
                {% if game[4] %}Released: {{ game[4] }}{% endif %}
                {% if game[5] %} | Genre: {{ game[5] }}{% endif %}
                {% if game[6] %} | Rating: {{ \"%.1f\"|format(game[6]) }}/100{% endif %}
            </div>
            <p class=\"game-description\">{{ game[3] or 'No description available' }}</p>
            <div class=\"game-actions\">
                <a href=\"{{ url_for('download', game_id=game[0]) }}\" class=\"btn\">Download</a>
                <a href=\"{{ url_for('delete', game_id=game[0]) }}\" class=\"btn\" onclick=\"return confirm('Are you sure you want to delete this game?')\">Delete</a>
                <a href=\"{{ url_for('edit_game', game_id=game[0]) }}\" class=\"btn\">Edit</a>
            </div>
        </div>
    {% endif %}
{% endfor %}
{% if not found %}
    <p style=\"text-align:center; color:#ffd700;\">No games uploaded yet.</p>
{% endif %}
{% endblock %}
'@
Set-Content -Path 'templates/index.html' -Value $indexTemplate -Encoding UTF8
}"

powershell -Command "& {
$uploadTemplate = @'
{% extends \"base.html\" %}
{% block content %}
<h2>Upload New Game</h2>
<form method=\"POST\" enctype=\"multipart/form-data\">
    <label for=\"title\">Game Title (Optional - will auto-detect if left blank):</label>
    <input type=\"text\" id=\"title\" name=\"title\" placeholder=\"Leave blank to auto-detect from filename\">
    <label for=\"file\">Game File:</label>
    <input type=\"file\" id=\"file\" name=\"file\" required>
    <input type=\"submit\" value=\"Upload Game\" class=\"btn btn-success\">
</form>
<div style=\"text-align: center; margin-top: 20px;\">
    <a href=\"{{ url_for('index') }}\" class=\"btn\">Back to Library</a>
</div>
{% endblock %}
'@
Set-Content -Path 'templates/upload.html' -Value $uploadTemplate -Encoding UTF8
}"

powershell -Command "& {
$editTemplate = @'
{% extends \"base.html\" %}
{% block content %}
<h2>Edit Game</h2>
<form method=\"POST\">
    <label>Name:</label>
    <input type=\"text\" name=\"title\" value=\"{{ game[1] }}\">
    <label>System:</label>
    <select name=\"system\">
        {% for sys in systems %}
            <option value=\"{{ sys }}\" {% if game[9] == sys %}selected{% endif %}>{{ sys }}</option>
        {% endfor %}
    </select>
    <label>Boxart URL:</label>
    <input type=\"text\" name=\"boxart\" value=\"{{ game[7] }}\">
    <button type=\"submit\" class=\"btn\">Save</button>
</form>
<form method=\"POST\" action=\"{{ url_for('scan_boxart', game_id=game[0]) }}\" style=\"margin-top: 10px;\">
    <button type=\"submit\" class=\"btn\">Scan for Boxart</button>
</form>
<div style=\"text-align: center; margin-top: 20px;\">
    <a href=\"{{ url_for('index') }}\" class=\"btn\">Back to Library</a>
</div>
{% endblock %}
'@
Set-Content -Path 'templates/edit.html' -Value $editTemplate -Encoding UTF8
}"

:: Create start script
echo Creating start script...
(
echo @echo off
echo cd /d "%%~dp0"
echo echo Starting Game Library Server...
echo echo Server will be available at http://localhost:5000
echo echo Press Ctrl+C to stop the server
echo echo.
echo call venv\Scripts\activate.bat
echo venv\Scripts\python.exe app.py
echo pause
) > start_server.bat

:: Create Windows service installer (optional)
echo Creating service installer...
(
echo @echo off
echo echo Installing Game Library Server as Windows Service...
echo sc create GameLibraryServer binPath= "cmd /c cd /d \"%CD%\" && call venv\Scripts\activate.bat && venv\Scripts\python.exe app.py" start= auto
echo sc description GameLibraryServer "Game Library Server - Web-based game management system"
echo echo Service installed. Use 'sc start GameLibraryServer' to start it.
echo pause
) > install_service.bat

echo.
echo ==========================================
echo Installation completed successfully!
echo ==========================================
echo.
echo Files created:
echo - app.py (Main Flask application)
echo - requirements.txt (Python dependencies)
echo - templates/ (HTML templates)
echo - start_server.bat (Start the server)
echo - install_service.bat (Optional Windows service)
echo.
echo To start the server:
echo 1. Double-click start_server.bat
echo 2. Open your browser to http://localhost:5000
echo.
echo Note: To use game metadata scraping, you'll need to:
echo 1. Register at https://dev.twitch.tv/console/apps
echo 2. Create a new application to get Client ID and Secret
echo 3. Edit app.py and replace 'your_client_id_here' and 'your_client_secret_here'
echo.
pause