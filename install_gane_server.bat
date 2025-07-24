@echo off
:: Game Library Server Installer for Windows

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
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
cd /d "%INSTALL_DIR%"

:: Ensure required folders exist before writing files
if not exist "templates" mkdir "templates"
if not exist "games" mkdir "games"
if not exist "db" mkdir "db"

:: Remove old database and games
del /Q db\games.db
rmdir /S /Q games
mkdir games

:: Check if Python is installed
python --version >nul 2>&1
if %errorLevel% equ 0 (
    echo Python already installed.
    for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
    echo Found Python %PYTHON_VERSION%
) else (
    echo Python not found. Downloading Python 3.11.5...
    powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_EXE%'"
    if !errorLevel! neq 0 (
        echo Failed to download Python installer.
        pause
        exit /b 1
    )
    echo Installing Python...
    "%PYTHON_EXE%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    if !errorLevel! neq 0 (
        echo Python installation failed.
        pause
        exit /b 1
    )
    del "%PYTHON_EXE%"
    echo Python installed successfully.
)

:: Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

:: Create virtual environment
echo.
echo Creating virtual environment...
python -m venv venv >nul 2>&1
if %errorLevel% neq 0 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install required packages
echo.
echo Installing required packages...
pip install Flask requests Werkzeug >nul 2>&1
if %errorLevel% neq 0 (
    echo Failed to install required packages.
    pause
    exit /b 1
)

:: Create requirements.txt
echo Flask==2.3.2 > requirements.txt
echo requests==2.31.0 >> requirements.txt
echo Werkzeug==2.3.4 >> requirements.txt

:: Create app.py
echo # Game Library Server > app.py
echo from flask import Flask, request, render_template, send_file, redirect, url_for, flash >> app.py
echo import os >> app.py
echo import requests >> app.py
echo import json >> app.py
echo from werkzeug.utils import secure_filename >> app.py
echo import sqlite3 >> app.py
echo from datetime import datetime >> app.py
echo. >> app.py
echo app = Flask(__name__) >> app.py
echo app.secret_key = 'game-library-secret-key-change-in-production' >> app.py
echo. >> app.py
echo UPLOAD_FOLDER = 'games' >> app.py
echo ALLOWED_EXTENSIONS = { >> app.py
echo     'exe', 'zip', 'rar', 'iso', 'dmg', >> app.py
echo     'nes', 'sfc', 'smc', 'gba', 'gb', 'gbc', 'nds', 'n64', 'z64', >> app.py
echo     'bin', 'gen', 'smd', 'sms', 'gg', 'pce', 'cue' >> app.py
echo } >> app.py
echo app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER >> app.py
echo. >> app.py
echo os.makedirs(UPLOAD_FOLDER, exist_ok=True) >> app.py
echo os.makedirs('db', exist_ok=True) >> app.py
echo os.makedirs('templates', exist_ok=True) >> app.py
echo. >> app.py
echo def init_db(): >> app.py
echo     conn = sqlite3.connect('db/games.db') >> app.py
echo     c = conn.cursor() >> app.py
echo     c.execute('''CREATE TABLE IF NOT EXISTS games ( >> app.py
echo         id INTEGER PRIMARY KEY AUTOINCREMENT, >> app.py
echo         title TEXT NOT NULL, >> app.py
echo         filename TEXT NOT NULL, >> app.py
echo         description TEXT, >> app.py
echo         release_date TEXT, >> app.py
echo         genre TEXT, >> app.py
echo         rating REAL, >> app.py
echo         cover_url TEXT, >> app.py
echo         upload_date TEXT, >> app.py
echo         system TEXT >> app.py
echo     )''') >> app.py
echo     conn.commit() >> app.py
echo     conn.close() >> app.py
echo. >> app.py
echo CLIENT_ID = 'your_client_id_here' >> app.py
echo CLIENT_SECRET = 'your_client_secret_here' >> app.py
echo ACCESS_TOKEN = None >> app.py
echo. >> app.py
echo def get_access_token(): >> app.py
echo     global ACCESS_TOKEN >> app.py
echo     if ACCESS_TOKEN: >> app.py
echo         return ACCESS_TOKEN >> app.py
echo     url = 'https://id.twitch.tv/oauth2/token' >> app.py
echo     params = { >> app.py
echo         'client_id': CLIENT_ID, >> app.py
echo         'client_secret': CLIENT_SECRET, >> app.py
echo         'grant_type': 'client_credentials' >> app.py
echo     } >> app.py
echo     response = requests.post(url, params=params) >> app.py
echo     if response.status_code == 200: >> app.py
echo         ACCESS_TOKEN = response.json()['access_token'] >> app.py
echo         return ACCESS_TOKEN >> app.py
echo     return None >> app.py
echo. >> app.py
echo def scrape_game_info(title): >> app.py
echo     token = get_access_token() >> app.py
echo     if not token: >> app.py
echo         return {} >> app.py
echo     url = 'https://api.igdb.com/v4/games' >> app.py
echo     headers = { >> app.py
echo         'Client-ID': CLIENT_ID, >> app.py
echo         'Authorization': f'Bearer {token}' >> app.py
echo     } >> app.py
echo     data = f'fields name,summary,first_release_date,genres.name,rating,cover.url; search "{title}"; limit 1;' >> app.py
echo     try: >> app.py
echo         response = requests.post(url, headers=headers, data=data) >> app.py
echo         if response.status_code == 200 and response.json(): >> app.py
echo             game = response.json()[0] >> app.py
echo             return { >> app.py
echo                 'title': game.get('name', title), >> app.py
echo                 'description': game.get('summary', ''), >> app.py
echo                 'release_date': datetime.fromtimestamp(game['first_release_date']).strftime('%%Y-%%m-%%d') if 'first_release_date' in game else '', >> app.py
echo                 'genre': ', '.join([g['name'] for g in game.get('genres', [])]), >> app.py
echo                 'rating': game.get('rating', 0), >> app.py
echo                 'cover_url': f"https:{game['cover']['url']}" if 'cover' in game else '' >> app.py
echo             } >> app.py
echo     except Exception as e: >> app.py
echo         print(f"Error scraping game info: {e}") >> app.py
echo     return {} >> app.py
echo. >> app.py
echo SYSTEM_MAP = { >> app.py
echo     'nes': 'Nintendo Entertainment System', >> app.py
echo     'sfc': 'Super Nintendo', >> app.py
echo     'smc': 'Super Nintendo', >> app.py
echo     'gba': 'Game Boy Advance', >> app.py
echo     'gb': 'Game Boy', >> app.py
echo     'gbc': 'Game Boy Color', >> app.py
echo     'nds': 'Nintendo DS', >> app.py
echo     'n64': 'Nintendo 64', >> app.py
echo     'z64': 'Nintendo 64', >> app.py
echo     'bin': 'Genesis', >> app.py
echo     'gen': 'Genesis', >> app.py
echo     'smd': 'Genesis', >> app.py
echo     'sms': 'Sega Master System', >> app.py
echo     'gg': 'Game Gear', >> app.py
echo     'pce': 'PC Engine', >> app.py
echo     'cue': 'PC Engine', >> app.py
echo } >> app.py
echo. >> app.py
echo def detect_system(filename): >> app.py
echo     ext = filename.rsplit('.', 1)[-1].lower() >> app.py
echo     return SYSTEM_MAP.get(ext, 'Other') >> app.py
echo. >> app.py
echo def allowed_file(filename): >> app.py
echo     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS >> app.py
echo. >> app.py
echo @app.route('/') >> app.py
echo def index(): >> app.py
echo     conn = sqlite3.connect('db/games.db') >> app.py
echo     c = conn.cursor() >> app.py
echo     c.execute('SELECT * FROM games ORDER BY upload_date DESC') >> app.py
echo     games = c.fetchall() >> app.py
echo     conn.close() >> app.py
echo     systems = sorted(set(game[9] for game in games if game[9])) >> app.py
echo     current_cat = request.args.get('cat', systems[0] if systems else 'Other') >> app.py
echo     try: >> app.py
echo         idx = systems.index(current_cat) >> app.py
echo         prev_cat = systems[idx - 1] if idx > 0 else systems[-1] >> app.py
echo         next_cat = systems[idx + 1] if idx < len(systems) - 1 else systems[0] >> app.py
echo     except ValueError: >> app.py
echo         prev_cat = next_cat = current_cat >> app.py
echo     return render_template('index.html', games=games, current_cat=current_cat, prev_cat=prev_cat, next_cat=next_cat, system_index=9) >> app.py
echo. >> app.py
echo @app.route('/upload', methods=['GET', 'POST']) >> app.py
echo def upload(): >> app.py
echo     if request.method == 'POST': >> app.py
echo         if 'file' not in request.files: >> app.py
echo             flash('No file selected') >> app.py
echo             return redirect(request.url) >> app.py
echo         file = request.files['file'] >> app.py
echo         if file.filename == '': >> app.py
echo             flash('No file selected') >> app.py
echo             return redirect(request.url) >> app.py
echo         if file and allowed_file(file.filename): >> app.py
echo             filename = secure_filename(file.filename) >> app.py
echo             filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename) >> app.py
echo             file.save(filepath) >> app.py
echo             title = request.form.get('title', '').strip() >> app.py
echo             if not title: >> app.py
echo                 title = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ') >> app.py
echo             game_info = scrape_game_info(title) >> app.py
echo             system = detect_system(filename) >> app.py
echo             conn = sqlite3.connect('db/games.db') >> app.py
echo             c = conn.cursor() >> app.py
echo             c.execute('''INSERT INTO games (title, filename, description, release_date, genre, rating, cover_url, upload_date, system) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', >> app.py
echo                 (game_info.get('title', title), filename, >> app.py
echo                  game_info.get('description', ''), >> app.py
echo                  game_info.get('release_date', ''), >> app.py
echo                  game_info.get('genre', ''), >> app.py
echo                  game_info.get('rating', 0), >> app.py
echo                  game_info.get('cover_url', ''), >> app.py
echo                  datetime.now().strftime('%%Y-%%m-%%d %%H:%%M:%%S'), >> app.py
echo                  system)) >> app.py
echo             conn.commit() >> app.py
echo             conn.close() >> app.py
echo             flash('Game uploaded successfully!') >> app.py
echo             return redirect(url_for('index')) >> app.py
echo         else: >> app.py
echo             flash('Invalid file type. Allowed: ' + ', '.join(sorted(ALLOWED_EXTENSIONS))) >> app.py
echo     return render_template('upload.html') >> app.py
echo. >> app.py
echo @app.route('/download/<int:game_id>') >> app.py
echo def download(game_id): >> app.py
echo     conn = sqlite3.connect('db/games.db') >> app.py
echo     c = conn.cursor() >> app.py
echo     c.execute('SELECT filename FROM games WHERE id = ?', (game_id,)) >> app.py
echo     result = c.fetchone() >> app.py
echo     conn.close() >> app.py
echo     if result: >> app.py
echo         filename = result[0] >> app.py
echo         filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename) >> app.py
echo         if os.path.exists(filepath): >> app.py
echo             return send_file(filepath, as_attachment=True) >> app.py
echo     flash('Game not found') >> app.py
echo     return redirect(url_for('index')) >> app.py
echo. >> app.py
echo @app.route('/delete/<int:game_id>') >> app.py
echo def delete(game_id): >> app.py
echo     conn = sqlite3.connect('db/games.db') >> app.py
echo     c = conn.cursor() >> app.py
echo     c.execute('SELECT filename FROM games WHERE id = ?', (game_id,)) >> app.py
echo     result = c.fetchone() >> app.py
echo     if result: >> app.py
echo         filename = result[0] >> app.py
echo         filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename) >> app.py
echo         if os.path.exists(filepath): >> app.py
echo             os.remove(filepath) >> app.py
echo         c.execute('DELETE FROM games WHERE id = ?', (game_id,)) >> app.py
echo         conn.commit() >> app.py
echo     conn.close() >> app.py
echo     flash('Game deleted successfully!') >> app.py
echo     return redirect(url_for('index')) >> app.py
echo. >> app.py
echo @app.route('/edit/<int:game_id>', methods=['GET', 'POST']) >> app.py
echo def edit_game(game_id): >> app.py
echo     conn = sqlite3.connect('db/games.db') >> app.py
echo     c = conn.cursor() >> app.py
echo     if request.method == 'POST': >> app.py
echo         title = request.form['title'] >> app.py
echo         system = request.form['system'] >> app.py
echo         boxart = request.form['boxart'] >> app.py
echo         c.execute('UPDATE games SET title=?, system=?, cover_url=? WHERE id=?', >> app.py
echo                   (title, system, boxart, game_id)) >> app.py
echo         conn.commit() >> app.py
echo         conn.close() >> app.py
echo         flash('Game updated!') >> app.py
echo         return redirect(url_for('edit_game', game_id=game_id)) >> app.py
echo     else: >> app.py
echo         c.execute('SELECT * FROM games WHERE id=?', (game_id,)) >> app.py
echo         game = c.fetchone() >> app.py
echo         conn.close() >> app.py
echo         return render_template('edit.html', game=game, systems=list(SYSTEM_MAP.values())) >> app.py
echo. >> app.py
echo @app.route('/scan_boxart/<int:game_id>', methods=['POST']) >> app.py
echo def scan_boxart(game_id): >> app.py
echo     conn = sqlite3.connect('db/games.db') >> app.py
echo     c = conn.cursor() >> app.py
echo     c.execute('SELECT title FROM games WHERE id=?', (game_id,)) >> app.py
echo     title = c.fetchone()[0] >> app.py
echo     game_info = scrape_game_info(title) >> app.py
echo     c.execute('UPDATE games SET cover_url=? WHERE id=?', (game_info.get('cover_url', ''), game_id)) >> app.py
echo     conn.commit() >> app.py
echo     conn.close() >> app.py
echo     flash('Boxart updated!') >> app.py
echo     return redirect(url_for('edit_game', game_id=game_id)) >> app.py
echo. >> app.py
echo if __name__ == '__main__': >> app.py
echo     init_db() >> app.py
echo     app.run(host='0.0.0.0', port=5000, debug=False) >> app.py

:: Create base.html
echo ^<!DOCTYPE html^> > templates\base.html
echo ^<html^> >> templates\base.html
echo ^<head^> >> templates\base.html
echo     ^<title^>Game Library^</title^> >> templates\base.html
echo     ^<style^> >> templates\base.html
echo         @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap'); >> templates\base.html
echo         html, body { height: 100%%; margin: 0; padding: 0; background: #181818; } >> templates\base.html
echo         body { font-family: 'VT323', 'Courier New', monospace; height: 100vh; width: 100vw; overflow: hidden; } >> templates\base.html
echo         .crt-outer { position: fixed; top: 0; left: 0; right: 0; bottom: 0; width: 100vw; height: 100vh; background: #222; display: flex; align-items: center; justify-content: center; } >> templates\base.html
echo         .crt-frame { position: relative; width: 100vw; height: 100vh; background: #222; border: 24px solid #666; border-radius: 48px; box-shadow: 0 0 80px #0ff, 0 0 0 16px #333 inset; overflow: hidden; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; } >> templates\base.html
echo         .crt-logo { position: absolute; bottom: 32px; left: 50%%; transform: translateX(-50%%); font-size: 2em; color: #0ff; text-shadow: 0 0 12px #0ff, 0 0 2px #fff; letter-spacing: 4px; font-family: 'VT323', monospace; pointer-events: none; user-select: none; } >> templates\base.html
echo         .crt-screen { position: absolute; top: 70px; left: 40px; right: 40px; bottom: 90px; background: #181818; border-radius: 32px; box-shadow: 0 0 32px #0ff inset; overflow-y: auto; z-index: 10; animation: crt-flicker 1.5s infinite alternate; } >> templates\base.html
echo     ^</style^> >> templates\base.html
echo ^</head^> >> templates\base.html
echo ^<body^> >> templates\base.html
echo     ^<div class="crt-outer"^> >> templates\base.html
echo         ^<div class="crt-frame"^> >> templates\base.html
echo             ^<div class="crt-screen"^> >> templates\base.html
echo                 ^{% block content %}^}{% endblock %} >> templates\base.html
echo             ^</div^> >> templates\base.html
echo             ^<div class="crt-logo"^>RETROVISION^</div^> >> templates\base.html
echo         ^</div^> >> templates\base.html
echo     ^</div^> >> templates\base.html
echo ^</body^> >> templates\base.html
echo ^</html^> >> templates\base.html

:: Create index.html
echo {% extends "base.html" %} > templates\index.html
echo {% block content %} >> templates\index.html
echo ^<h3^>Game Collection^</h3^> >> templates\index.html
echo ^<div style="display:flex; justify-content:center; align-items:center; margin-bottom:16px;"^> >> templates\index.html
echo     ^<button onclick="window.location='?cat={{ prev_cat }}'"^>&lt; Prev^</button^> >> templates\index.html
echo     ^<span style="margin:0 24px; color:#ffd700; font-size:1.3em;"^>{{ current_cat }}^</span^> >> templates\index.html
echo     ^<button onclick="window.location='?cat={{ next_cat }}'"^>Next &gt;^</button^> >> templates\index.html
echo ^</div^> >> templates\index.html
echo {% set found = false %} >> templates\index.html
echo {% for game in games %} >> templates\index.html
echo     {% if game[system_index] == current_cat %} >> templates\index.html
echo         {% set found = true %} >> templates\index.html
echo         ^<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 500px;"^> >> templates\index.html
echo             {% if game[7] %} >> templates\index.html
echo                 ^<div style="position:relative;"^> >> templates\index.html
echo                     ^<img src="{{ game[7] }}" alt="{{ game[1] }}" style="width:320px; height:420px; object-fit:cover; border-radius:18px; box-shadow:0 0 32px #0ff, 0 0 0 8px #333 inset; z-index:1;"^> >> templates\index.html
echo                     ^<div style="position:absolute; top:0; left:0; width:100%%; height:100%%; pointer-events:none; background: repeating-linear-gradient(to bottom, rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 1px, transparent 2px, transparent 4px); opacity:0.5; border-radius:18px; z-index:2;"^>^</div^> >> templates\index.html
echo                 ^</div^> >> templates\index.html
echo             {% else %} >> templates\index.html
echo                 ^<div style="width:320px; height:420px; background:#222; color:#0ff; display:flex; align-items:center; justify-content:center; border-radius:18px; font-size:2em; box-shadow:0 0 32px #0ff, 0 0 0 8px #333 inset;"^>No Boxart^</div^> >> templates\index.html
echo             {% endif %} >> templates\index.html
echo             ^<h2 style="color:#0ff; margin:18px 0 8px 0; text-align:center; text-shadow:0 0 8px #0ff, 0 0 2px #fff;"^>{{ game[1] }}^</h2^> >> templates\index.html
echo             ^<div style="color:#ffd700; text-align:center; margin-bottom:8px;"^> >> templates\index.html
echo                 {% if game[4] %}Released: {{ game[4] }}{% endif %} >> templates\index.html
echo                 {% if game[5] %} | Genre: {{ game[5] }}{% endif %} >> templates\index.html
echo                 {% if game[6] %} | Rating: {{ "%.1f"|format(game[6]) }}/100{% endif %} >> templates\index.html
echo             ^</div^> >> templates\index.html
echo             ^<p style="color:#eee; text-align:center; max-width:500px;"^>{{ game[3] or 'No description available' }}^</p^> >> templates\index.html
echo             ^<div style="margin-top:12px;"^> >> templates\index.html
echo                 ^<a href="{{ url_for('download', game_id=game[0]) }}" class="btn"^>Download^</a^> >> templates\index.html
echo                 ^<a href="{{ url_for('delete', game_id=game[0]) }}" class="btn" onclick="return confirm('Are you sure you want to delete this game?')"^>Delete^</a^> >> templates\index.html
echo                 ^<a href="{{ url_for('edit_game', game_id=game[0]) }}" class="btn"^>Edit^</a^> >> templates\index.html
echo             ^</div^> >> templates\index.html
echo         ^</div^> >> templates\index.html
echo     {% endif %} >> templates\index.html
echo {% endfor %} >> templates\index.html
echo {% if not found %} >> templates\index.html
echo     ^<p style="text-align:center; color:#ffd700;"^>No games uploaded yet.^</p^> >> templates\index.html
echo {% endif %} >> templates\index.html
echo {% endblock %} >> templates\index.html

:: Create edit.html
echo {% extends "base.html" %} > templates\edit.html
echo {% block content %} >> templates\edit.html
echo ^<h2^>Edit Game^</h2^> >> templates\edit.html
echo ^<form method="POST"^> >> templates\edit.html
echo     ^<label^>Name:^</label^> >> templates\edit.html
echo     ^<input type="text" name="title" value="{{ game[1] }}"^> >> templates\edit.html
echo     ^<label^>System:^</label^> >> templates\edit.html
echo     ^<select name="system"^> >> templates\edit.html
echo         {% for sys in systems %} >> templates\edit.html
echo             ^<option value="{{ sys }}" {% if game[9] == sys %}selected{% endif %}^>{{ sys }}^</option^> >> templates\edit.html
echo         {% endfor %} >> templates\edit.html
echo     ^</select^> >> templates\edit.html
echo     ^<label^>Boxart URL:^</label^> >> templates\edit.html
echo     ^<input type="text" name="boxart" value="{{ game[7] }}"^> >> templates\edit.html
echo     ^<button type="submit" class="btn"^>Save^</button^> >> templates\edit.html
echo ^</form^> >> templates\edit.html
echo ^<form method="POST" action="{{ url_for('scan_boxart', game_id=game[0]) }}"^> >> templates\edit.html
echo     ^<button type="submit" class="btn"^>Scan for Boxart^</button^> >> templates\edit.html
echo ^</form^> >> templates\edit.html
echo {% endblock %} >> templates\edit.html

:: Create upload.html
echo {% extends "base.html" %} > templates\upload.html
echo {% block content %} >> templates\upload.html
echo ^<h2^>Upload New Game^</h2^> >> templates\upload.html
echo ^<form method="POST" enctype="multipart/form-data"^> >> templates\upload.html
echo     ^<label for="title"^>Game Title (Optional - will auto-detect if left blank):^</label^> >> templates\upload.html
echo     ^<input type="text" id="title" name="title" placeholder="Leave blank to auto-detect from filename"^> >> templates\upload.html
echo     ^<label for="file"^>Game File:^</label^> >> templates\upload.html
echo     ^<input type="file" id="file" name="file" required^> >> templates\upload.html
echo     ^<input type="submit" value="Upload Game" class="btn btn-success"^> >> templates\upload.html
echo ^</form^> >> templates\upload.html
echo {% endblock %} >> templates\upload.html

:: Create start script
echo @echo off > start_server.bat
echo cd /d "%%~dp0" >> start_server.bat
echo echo Starting Game Library Server... >> start_server.bat
echo echo Server will be available at http://localhost:5000 >> start_server.bat
echo echo Press Ctrl+C to stop the server >> start_server.bat
echo echo. >> start_server.bat
echo call venv\Scripts\activate.bat >> start_server.bat
echo python app.py >> start_server.bat

:: Create desktop shortcut
echo Creating desktop shortcut...
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\Game Library Server.lnk"
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT_PATH%'); $Shortcut.TargetPath = '%INSTALL_DIR%\start_server.bat'; $Shortcut.Save()"

echo.
echo Installation completed successfully!
echo.
echo To get started:
echo 1. Get IGDB API credentials at https://api.igdb.com/
echo 2. Edit app.py and replace:
echo    - your_client_id_here with your Client ID
echo    - your_client_secret_here with your Client Secret
echo 3. Double-click "Game Library Server" on your desktop to start
echo 4. Visit http://localhost:5000 in your browser
echo.
echo Your games will be stored in: %INSTALL_DIR%\games
echo.
pause