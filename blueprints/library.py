import os
import sqlite3
import subprocess
from datetime import datetime
from uuid import uuid4
import shutil
import json
import requests
from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

from utils import get_setting

# Create a Blueprint instance
library_bp = Blueprint('library', __name__)

# Helper function to get DB connection
def get_db_connection():
    conn = sqlite3.connect(current_app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

# Helper function to get system image URL
# This function determines the path to the system silhouette image
def get_system_image_url(system_name):
    # Convert system name to a URL-friendly filename (lowercase, spaces to underscores, remove special chars)
    # Example: "Nintendo Switch" -> "nintendo_switch.png"
    # "PlayStation 5" -> "playstation_5.png"
    # "PC" -> "pc.png"
    filename = system_name.lower().replace(' ', '_').replace('-', '_').replace('.', '').replace('&', 'and') + '.png'
    image_path = os.path.join(current_app.root_path, 'static', 'img', 'systems', filename)

    # Check if the specific image exists
    if os.path.exists(image_path):
        return url_for('static', filename=f'img/systems/{filename}')
    else:
        # Fallback to a generic placeholder system image
        return url_for('static', filename='img/systems/placeholder_system.png')


@library_bp.route('/')
def index():
    conn = get_db_connection()
    # Get unique systems and their game counts
    systems_data = conn.execute('''
        SELECT system, COUNT(id) as game_count
        FROM games
        GROUP BY system
        ORDER BY system
    ''').fetchall()
    conn.close()

    # Prepare data for template, including image URLs and library filter URLs
    systems_for_template = []
    for system in systems_data:
        systems_for_template.append({
            'name': system['system'],
            'count': system['game_count'],
            'image_url': get_system_image_url(system['system']),
            # Link to filter the main library by this system
            'url': url_for('library.library', system=system['system'])
        })

    # The homepage no longer needs a total games counter, as the focus is on systems
    return render_template('index.html', systems=systems_for_template)


@library_bp.route('/library')
@library_bp.route('/library/<string:system_name>') # Keep this for direct system links if needed
def library(system_name=None): # system_name from URL path
    conn = get_db_connection()
    
    # Get filters/sorts from query parameters (for the new library page functionality)
    system_filter_param = request.args.get('system') # system from query param (e.g., ?system=NES)
    search_query = request.args.get('search')
    sort_by = request.args.get('sort_by', 'title') # Default sort by title
    sort_order = request.args.get('sort_order', 'ASC') # Default sort ascending

    # Determine the effective system filter: query param takes precedence over path param
    effective_system_filter = system_filter_param if system_filter_param else system_name

    query = "SELECT * FROM games"
    params = []
    where_clauses = []

    current_display_title = "My Game Library"

    if effective_system_filter:
        where_clauses.append("system = ?")
        params.append(effective_system_filter)
        current_display_title = f"Games on {effective_system_filter}"

    if search_query:
        where_clauses.append("(title LIKE ? OR system LIKE ?)")
        params.append(f"%{search_query}%")
        params.append(f"%{search_query}%")
        current_display_title = f"Search results for '{search_query}'"

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    # Basic input validation for sort_by to prevent SQL injection
    # Ensure these match your database column names
    valid_sort_columns = ['title', 'system', 'last_played', 'play_count'] # Added last_played, play_count
    if sort_by not in valid_sort_columns:
        sort_by = 'title' # Default if invalid

    # Basic input validation for sort_order
    if sort_order.upper() not in ['ASC', 'DESC']:
        sort_order = 'ASC' # Default if invalid

    query += f" ORDER BY {sort_by} {sort_order}"

    games = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('library.html',
                           games=games,
                           current_display_title=current_display_title,
                           current_system_filter=effective_system_filter, # Pass the active filter to template
                           current_search_query=search_query, # Pass search query to template
                           current_sort_by=sort_by, # Pass sort preference to template
                           current_sort_order=sort_order) # Pass sort order to template


@library_bp.route('/game/<int:game_id>')
def game_detail(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    conn.close()
    if game is None:
        flash('Game not found.', 'error')
        return redirect(url_for('library.library'))
    return render_template('game_detail.html', game=game)


# --- NEW: Web Emulator Route ---
@library_bp.route('/play_web/<int:game_id>')
def play_web_emulator(game_id):
    conn = get_db_connection()
    game_row = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    conn.close() # Close connection after fetching game data

    if game_row:
        # Convert sqlite3.Row object to a regular dictionary for JSON serialization
        game = dict(game_row) 
        # Convert backslashes to forward slashes for URL compatibility and JSON safety
        if 'filepath' in game and game['filepath'] is not None:
            game['filepath'] = game['filepath'].replace('\\', '/')

        # We need the filename part of the filepath to construct the URL
        # The filepath stored is an absolute path (e.g., C:\...)
        # We configured run.py to serve files from UPLOAD_FOLDER via /roms/<filename>
        rom_filename = os.path.basename(game['filepath'])
        
        # --- IMPORTANT CHANGE: Generate a full absolute URL for the ROM ---
        # This ensures Nostalgist.js doesn't try to resolve it against a CDN base.
        rom_url = url_for('roms_file', filename=rom_filename, _external=True)
        
        system_name = game['system'] # Get the system name from the game record

        # Add a basic security check: only allow SNES for web emulation for now
        # Adjust 'Super Nintendo' to match your database entry exactly (case-insensitive due to .lower())
        if system_name.lower() != 'super nintendo': # Example: 'super nintendo' or 'snes'
            flash(f"Web emulation is only configured for Super Nintendo games at the moment. This is a {system_name} game.", 'error')
            return redirect(url_for('library.game_detail', game_id=game_id))

        return render_template('web_emulator.html', game=game, rom_url=rom_url)
    else:
        flash('Game not found.', 'error')
        return redirect(url_for('library.library'))


@library_bp.route('/upload', methods=['GET', 'POST'])
def upload_game():
    conn = get_db_connection()
    systems = conn.execute('SELECT name FROM systems ORDER BY name').fetchall()
    conn.close()

    if request.method == 'POST':
        title = request.form['title']
        system = request.form['system']
        new_system_name = request.form.get('new_system_name')
        game_file = request.files.get('game_file')
        cover_file = request.files.get('cover_file')
        igdb_cover_url_input = request.form.get('igdb_cover_url')

        if not title or not (system or new_system_name) or not game_file:
            flash('Title, System, and Game File are required.', 'error')
            return redirect(request.url)
        
        if new_system_name:
            final_system = new_system_name.strip()
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO systems (name) VALUES (?)', (final_system,))
                conn.commit()
                flash(f"New system '{final_system}' added.", 'success')
            except sqlite3.IntegrityError:
                flash(f"System '{final_system}' already exists, using existing system.", 'info')
            finally:
                conn.close()
        else:
            final_system = system

        filename_base, file_extension = os.path.splitext(game_file.filename)
        unique_filename = f"{uuid4()}{file_extension}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        game_file.save(filepath)
        
        cover_url = None
        if cover_file and cover_file.filename:
            cover_filename_base, cover_extension = os.path.splitext(cover_file.filename)
            unique_cover_filename = f"{uuid4()}{cover_extension}"
            cover_path = os.path.join(current_app.config['COVERS_FOLDER'], unique_cover_filename)
            cover_file.save(cover_path)
            cover_url = url_for('static', filename=f'covers/{unique_cover_filename}')
        elif igdb_cover_url_input:
            try:
                response = requests.get(igdb_cover_url_input, stream=True)
                response.raise_for_status()

                # Determine file extension more robustly
                ext = '.jpg' # Default to JPG if not found
                parsed_url = urlparse(igdb_cover_url_input)
                path_without_query = parsed_url.path
                if '.' in path_without_query:
                    ext = os.path.splitext(path_without_query)[-1]
                else:
                    content_type = response.headers.get('Content-Type')
                    if content_type and 'image/' in content_type:
                        ext = '.' + content_type.split('/')[-1].split(';')[0] # Remove charset etc.
                    if not ext or len(ext) > 5: # Fallback if content-type is also unhelpful
                        ext = '.jpg'
                
                unique_cover_filename = f"{uuid4()}{ext}"
                cover_path = os.path.join(current_app.config['COVERS_FOLDER'], unique_cover_filename)

                # Ensure the covers folder exists before saving
                os.makedirs(current_app.config['COVERS_FOLDER'], exist_ok=True)

                with open(cover_path, 'wb') as out_file:
                    shutil.copyfileobj(response.raw, out_file)
                cover_url = url_for('static', filename=f'covers/{unique_cover_filename}')
                flash("IGDB cover downloaded and applied.", "info")
            except requests.exceptions.RequestException as req_e:
                flash(f"Could not download IGDB cover (Network Error): {req_e}", "warning")
                cover_url = None
            except Exception as e:
                flash(f"Could not download IGDB cover (General Error): {e}", "warning")
                cover_url = None

        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO games (title, system, filepath, cover_url) VALUES (?, ?, ?, ?)',
                         (title, final_system, filepath, cover_url))
            conn.commit()
            flash('Game uploaded successfully!', 'success')
            return redirect(url_for('library.library', system=final_system)) # Use 'system' query param
        except Exception as e:
            flash(f'An error occurred: {e}', 'error')
            if os.path.exists(filepath):
                os.remove(filepath)
            if cover_url and os.path.exists(os.path.join(current_app.root_path, cover_url.replace('/static/', 'static/'))):
                os.remove(os.path.join(current_app.root_path, cover_url.replace('/static/', 'static/')))
            return redirect(request.url)
        finally:
            conn.close()
    
    return render_template('upload_game.html', systems=systems)


@library_bp.route('/edit/<int:game_id>', methods=['GET', 'POST'])
def edit_game(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    systems = conn.execute('SELECT name FROM systems ORDER BY name').fetchall()
    conn.close()

    if game is None:
        flash('Game not found.', 'error')
        return redirect(url_for('library.library'))

    if request.method == 'POST':
        new_title = request.form['title']
        new_system = request.form['system']
        new_system_name = request.form.get('new_system_name')
        new_game_file = request.files.get('game_file')
        new_cover_file = request.files.get('cover_file')
        igdb_cover_url_input = request.form.get('igdb_cover_url')
        
        final_system = new_system
        if new_system_name:
            final_system = new_system_name.strip()
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO systems (name) VALUES (?)', (final_system,))
                conn.commit()
                flash(f"New system '{final_system}' added.", 'success')
            except sqlite3.IntegrityError:
                pass
            finally:
                conn.close()

        updated_filepath = game['filepath']
        updated_cover_url = game['cover_url'] # Preserve current URL by default

        # Handle new game file upload
        if new_game_file and new_game_file.filename:
            if os.path.exists(game['filepath']):
                os.remove(game['filepath']) # Delete old file
            
            filename_base, file_extension = os.path.splitext(new_game_file.filename)
            unique_filename = f"{uuid4()}{file_extension}"
            updated_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
            new_game_file.save(updated_filepath)

        # Handle new cover file upload (custom or IGDB)
        if new_cover_file and new_cover_file.filename:
            if game['cover_url'] and 'static/covers/' in game['cover_url']:
                old_cover_path = os.path.join(current_app.root_path, game['cover_url'].replace('/static/', 'static/'))
                if os.path.exists(old_cover_path):
                    os.remove(old_cover_path) # Delete old cover
            
            cover_filename_base, cover_extension = os.path.splitext(new_cover_file.filename)
            unique_cover_filename = f"{uuid4()}{cover_extension}"
            cover_path = os.path.join(current_app.config['COVERS_FOLDER'], unique_cover_filename)
            new_cover_file.save(cover_path)
            updated_cover_url = url_for('static', filename=f'covers/{unique_cover_filename}')
        elif igdb_cover_url_input:
            # If a new IGDB cover is selected, delete the old one first if it's local
            if game['cover_url'] and 'static/covers/' in game['cover_url']:
                old_cover_path = os.path.join(current_app.root_path, game['cover_url'].replace('/static/', 'static/'))
                if os.path.exists(old_cover_path):
                    os.remove(old_cover_path)
            try:
                response = requests.get(igdb_cover_url_input, stream=True)
                response.raise_for_status()
                
                # Determine file extension more robustly
                ext = '.jpg'
                parsed_url = urlparse(igdb_cover_url_input)
                path_without_query = parsed_url.path
                if '.' in path_without_query:
                    ext = os.path.splitext(path_without_query)[-1]
                else:
                    content_type = response.headers.get('Content-Type')
                    if content_type and 'image/' in content_type:
                        ext = '.' + content_type.split('/')[-1].split(';')[0]
                    if not ext or len(ext) > 5:
                        ext = '.jpg'

                unique_cover_filename = f"{uuid4()}{ext}"
                cover_path = os.path.join(current_app.config['COVERS_FOLDER'], unique_cover_filename)

                # Ensure the covers folder exists before saving
                os.makedirs(current_app.config['COVERS_FOLDER'], exist_ok=True)

                with open(cover_path, 'wb') as out_file:
                    shutil.copyfileobj(response.raw, out_file)
                updated_cover_url = url_for('static', filename=f'covers/{unique_cover_filename}')
                flash("IGDB cover downloaded and applied.", "info")
            except requests.exceptions.RequestException as req_e:
                flash(f"Could not download IGDB cover (Network Error): {req_e}", "warning")
                # IMPORTANT: If download fails, revert to the original cover URL
                updated_cover_url = game['cover_url']
            except Exception as e:
                flash(f"Could not download IGDB cover (General Error): {e}", "warning")
                # IMPORTANT: If download fails, revert to the original cover URL
                updated_cover_url = game['cover_url']
        elif 'clear_cover' in request.form:
            if game['cover_url'] and 'static/covers/' in game['cover_url']:
                old_cover_path = os.path.join(current_app.root_path, game['cover_url'].replace('/static/', 'static/'))
                if os.path.exists(old_cover_path):
                    os.remove(old_cover_path)
            updated_cover_url = None # Set to None if user chose to clear

        conn = get_db_connection()
        try:
            conn.execute('''
                UPDATE games SET title = ?, system = ?, filepath = ?, cover_url = ?
                WHERE id = ?
            ''', (new_title, final_system, updated_filepath, updated_cover_url, game_id))
            conn.commit()
            flash('Game updated successfully!', 'success')
            return redirect(url_for('library.game_detail', game_id=game_id))
        except Exception as e:
            flash(f'An error occurred: {e}', 'error')
            return redirect(request.url)
        finally:
            conn.close()

    return render_template('edit_game.html', game=game, systems=systems)


@library_bp.route('/delete/<int:game_id>')
def delete_game(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    
    if game is None:
        flash('Game not found.', 'error')
        conn.close()
        return redirect(url_for('library.library'))

    try:
        # Delete game file
        if os.path.exists(game['filepath']):
            os.remove(game['filepath'])
        
        # Delete cover file if it's a locally stored one
        if game['cover_url'] and 'static/covers/' in game['cover_url']:
            cover_path = os.path.join(current_app.root_path, game['cover_url'].replace('/static/', 'static/'))
            if os.path.exists(cover_path):
                os.remove(cover_path)

        conn.execute('DELETE FROM games WHERE id = ?', (game_id,))
        conn.commit()
        flash(f"Game '{game['title']}' deleted successfully.", 'success')
    except Exception as e:
        flash(f'An error occurred during deletion: {e}', 'error')
    finally:
        conn.close()

    # Redirect back to the library, potentially filtered by the system it was in
    return redirect(url_for('library.library', system=game['system']))


@library_bp.route('/launch/<int:game_id>')
def launch_game(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    
    if game is None:
        flash('Game not found.', 'error')
        conn.close()
        return redirect(url_for('library.library'))

    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('UPDATE games SET last_played = ?, play_count = play_count + 1 WHERE id = ?', 
                     (current_time, game_id))
        conn.commit()
        conn.close()

        emulator_command = []
        # Emulator configurations (these are example paths, adjust for your system)
        if game['system'].lower() == 'nes':
            if os.name == 'nt': # Windows
                emulator_command = ['C:\\Emulators\\Nestopia\\nestopia.exe', game['filepath']]
            else: # Linux/macOS (assuming emulator is in PATH)
                emulator_command = ['nestopia', game['filepath']]
        elif game['system'].lower() == 'snes':
            if os.name == 'nt':
                emulator_command = ['C:\\Emulators\\Snes9x\\snes9x.exe', game['filepath']]
            else:
                emulator_command = ['snes9x', game['filepath']]
        elif game['system'].lower() == 'n64':
            if os.name == 'nt':
                emulator_command = ['C:\\Emulators\\Project64\\Project64.exe', game['filepath']]
            else:
                emulator_command = ['project64', game['filepath']]
        elif game['system'].lower() == 'gba':
            if os.name == 'nt':
                emulator_command = ['C:\\Emulators\\VBA-M\\vbam.exe', game['filepath']]
            else:
                emulator_command = ['vbam', game['filepath']]
        elif game['system'].lower() == 'mame':
            if os.name == 'nt':
                emulator_command = ['C:\\Emulators\\MAME\\mame.exe', game['filepath']]
            else:
                emulator_command = ['mame', game['filepath']]
        elif game['system'].lower() == 'dreamcast':
            if os.name == 'nt':
                emulator_command = ['C:\\Emulators\\Demul\\demul.exe', '-run=dc', '-rom=' + game['filepath']]
            else:
                emulator_command = ['demul', '-run=dc', '-rom=' + game['filepath']]
        elif game['system'].lower() == 'ps1':
            if os.name == 'nt':
                emulator_command = ['C:\\Emulators\\ePSXe\\ePSXe.exe', '-nogui', '-loadbin', game['filepath']]
            else:
                emulator_command = ['epsxe', '-nogui', '-loadbin', game['filepath']]
        elif game['system'].lower() == 'pc':
            if os.name == 'nt':
                os.startfile(game['filepath']) # On Windows, this opens the file with its default program
                flash(f"Launched PC game: {game['title']}", 'success')
                return redirect(url_for('library.game_detail', game_id=game['id']))
            else:
                # On Linux/macOS, use subprocess.Popen to run the executable
                subprocess.Popen([game['filepath']], start_new_session=True)
                flash(f"Launched PC game: {game['title']}", 'success')
                return redirect(url_for('library.game_detail', game_id=game['id']))
        else:
            flash(f"No emulator configured for system: {game['system']}", 'error')
            return redirect(url_for('library.game_detail', game_id=game['id']))

        if emulator_command:
            subprocess.Popen(emulator_command, start_new_session=True)
            flash(f"Launched {game['title']} using {game['system']} emulator.", 'success')
        
    except FileNotFoundError:
        flash(f"Emulator for {game['system']} not found. Please check your configuration.", 'error')
    except Exception as e:
        flash(f"An error occurred while launching the game: {e}", 'error')
    
    return redirect(url_for('library.game_detail', game_id=game['id']))
