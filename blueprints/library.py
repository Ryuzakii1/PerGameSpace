import os
import sqlite3
import shutil
import json
import requests
from urllib.parse import urlparse
import zipfile
from datetime import datetime
from uuid import uuid4

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

from utils import get_setting
from blueprints.emulation import _get_rom_paths_for_serving

library_bp = Blueprint('library', __name__)

def get_db_connection():
    conn = sqlite3.connect(current_app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def get_system_image_url(system_name):
    filename = system_name.lower().replace(' ', '_').replace('-', '_').replace('.', '').replace('&', 'and') + '.png'
    image_path = os.path.join(current_app.root_path, 'static', 'img', 'systems', filename)

    if os.path.exists(image_path):
        return url_for('static', filename=f'img/systems/{filename}')
    else:
        return url_for('static', filename='img/systems/placeholder_system.png')

def save_and_organize_game_file(uploaded_file, system_name, game_title):
    if not uploaded_file or not uploaded_file.filename:
        return None, None

    original_filename = uploaded_file.filename
    safe_system_name = "".join(c for c in system_name if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')
    safe_game_title = "".join(c for c in game_title if c.isalnum() or c in (' ', '_', '-')).strip()
    system_roms_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_system_name)
    os.makedirs(system_roms_dir, exist_ok=True)
    file_extension = os.path.splitext(original_filename)[1].lower()
    temp_filepath = os.path.join(current_app.config['TEMP_UPLOAD_FOLDER'], f"{uuid4()}_{original_filename}")
    os.makedirs(current_app.config['TEMP_UPLOAD_FOLDER'], exist_ok=True)
    uploaded_file.save(temp_filepath)
    current_app.logger.info(f"Saved temporary file to: {temp_filepath}")
    final_game_path = None
    try:
        if file_extension == '.zip':
            unzip_target_dir_name = f"{safe_game_title}_{uuid4().hex[:8]}"
            unzip_target_path = os.path.join(system_roms_dir, unzip_target_dir_name)
            os.makedirs(unzip_target_path, exist_ok=True)
            current_app.logger.info(f"Created unzip target directory: {unzip_target_path}")
            with zipfile.ZipFile(temp_filepath, 'r') as zip_ref:
                zip_ref.extractall(unzip_target_path)
            current_app.logger.info(f"Extracted '{original_filename}' to '{unzip_target_path}'")
            final_game_path = unzip_target_path
            flash(f"'{original_filename}' unzipped and organized into '{safe_system_name}' folder.", 'info')
        else:
            unique_filename_for_storage = f"{uuid4()}{file_extension}"
            destination_filepath = os.path.join(system_roms_dir, unique_filename_for_storage)
            shutil.move(temp_filepath, destination_filepath)
            final_game_path = destination_filepath
            current_app.logger.info(f"Moved '{original_filename}' to '{destination_filepath}'")
            flash(f"'{original_filename}' organized into '{safe_system_name}' folder.", 'info')
    except zipfile.BadZipFile:
        flash(f"Error: '{original_filename}' is not a valid zip file.", 'error')
        current_app.logger.error(f"BadZipFile error for: {temp_filepath}")
        final_game_path = None
    except Exception as e:
        flash(f"Error processing game file: {e}", 'error')
        current_app.logger.error(f"General error processing {temp_filepath}: {e}", exc_info=True)
        final_game_path = None
    finally:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
            current_app.logger.info(f"Cleaned up temporary file: {temp_filepath}")
    return final_game_path, original_filename

@library_bp.route('/')
def index():
    conn = get_db_connection()
    systems_data = conn.execute('''
        SELECT system, COUNT(id) as game_count
        FROM games
        GROUP BY system
        ORDER BY system
    ''').fetchall()
    conn.close()
    systems_for_template = []
    for system in systems_data:
        systems_for_template.append({
            'name': system['system'],
            'count': system['game_count'],
            'image_url': get_system_image_url(system['system']),
            'url': url_for('library.library', system=system['system'])
        })
    return render_template('index.html', systems=systems_for_template)

@library_bp.route('/library')
@library_bp.route('/library/<string:system_name>')
def library(system_name=None):
    conn = get_db_connection()
    system_filter_param = request.args.get('system')
    search_query = request.args.get('search')
    sort_by = request.args.get('sort_by', 'title')
    sort_order = request.args.get('sort_order', 'ASC')
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
    valid_sort_columns = ['title', 'system', 'last_played', 'play_count']
    if sort_by not in valid_sort_columns:
        sort_by = 'title'
    if sort_order.upper() not in ['ASC', 'DESC']:
        sort_order = 'ASC'
    query += f" ORDER BY {sort_by} {sort_order}"
    games = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('library.html',
                           games=games,
                           current_display_title=current_display_title,
                           current_system_filter=effective_system_filter,
                           current_search_query=search_query,
                           current_sort_by=sort_by,
                           current_sort_order=sort_order)

@library_bp.route('/game/<int:game_id>')
def game_detail(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    conn.close()
    if game is None:
        flash('Game not found.', 'error')
        return redirect(url_for('library.library'))

    game_dict = dict(game)
    game_json = json.dumps(game_dict)

    web_emulator_url = None
    desktop_emulator_url = None
    download_url = None

    if game['original_filename']:
        # --- FIX: Changed endpoint name from 'emulation.play_web' to 'emulation.play_web_emulator' ---
        # This now correctly matches the function name 'play_web_emulator' in the emulation.py blueprint.
        web_emulator_url = url_for('emulation.play_web_emulator',
                                   game_id=game['id'])

        desktop_emulator_url = url_for('emulation.launch_game', 
                                       game_id=game['id'])

        # This correctly points to the download route in run.py
        download_url = url_for('download_rom_file', 
                               game_id=game['id'], 
                               original_filename=game['original_filename'])

    return render_template('game_detail.html', 
                           game=game,
                           game_json=game_json,
                           web_emulator_url=web_emulator_url,
                           desktop_emulator_url=desktop_emulator_url,
                           download_url=download_url)

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
        final_system = new_system_name.strip() if new_system_name else system
        if new_system_name:
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO systems (name) VALUES (?)', (final_system,))
                conn.commit()
                flash(f"New system '{final_system}' added.", 'success')
            except sqlite3.IntegrityError:
                flash(f"System '{final_system}' already exists, using existing system.", 'info')
            finally:
                conn.close()
        filepath, original_filename = save_and_organize_game_file(game_file, final_system, title)
        if filepath is None:
            return redirect(request.url)
        cover_url = None
        if cover_file and cover_file.filename:
            _, cover_extension = os.path.splitext(cover_file.filename)
            unique_cover_filename = f"{uuid4()}{cover_extension}"
            cover_path = os.path.join(current_app.config['COVERS_FOLDER'], unique_cover_filename)
            os.makedirs(current_app.config['COVERS_FOLDER'], exist_ok=True)
            cover_file.save(cover_path)
            cover_url = url_for('static', filename=f'covers/{unique_cover_filename}')
        elif igdb_cover_url_input:
            try:
                response = requests.get(igdb_cover_url_input, stream=True)
                response.raise_for_status()
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
                os.makedirs(current_app.config['COVERS_FOLDER'], exist_ok=True)
                with open(cover_path, 'wb') as out_file:
                    shutil.copyfileobj(response.raw, out_file)
                cover_url = url_for('static', filename=f'covers/{unique_cover_filename}')
            except requests.exceptions.RequestException as req_e:
                flash(f"Could not download IGDB cover (Network Error): {req_e}", "warning")
                cover_url = None
            except Exception as e:
                flash(f"Could not download IGDB cover (General Error): {e}", "warning")
                cover_url = None
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO games (title, system, filepath, cover_url, original_filename) VALUES (?, ?, ?, ?, ?)',
                         (title, final_system, filepath, cover_url, original_filename))
            conn.commit()
            flash('Game uploaded successfully!', 'success')
            return redirect(url_for('library.library', system=final_system))
        except Exception as e:
            flash(f'An error occurred: {e}', 'error')
            if filepath and os.path.exists(filepath):
                if os.path.isdir(filepath):
                    shutil.rmtree(filepath)
                else:
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
        final_system = new_system_name.strip() if new_system_name else new_system
        if new_system_name:
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
        updated_original_filename = game['original_filename']
        updated_cover_url = game['cover_url']
        if new_game_file and new_game_file.filename:
            if updated_filepath and os.path.exists(updated_filepath):
                if os.path.isdir(updated_filepath):
                    shutil.rmtree(updated_filepath)
                else:
                    os.remove(updated_filepath)
            filepath_from_upload, original_filename_from_upload = save_and_organize_game_file(new_game_file, final_system, new_title)
            if filepath_from_upload is None:
                flash("Failed to process new game file. Keeping old file.", 'error')
            else:
                updated_filepath = filepath_from_upload
                updated_original_filename = original_filename_from_upload
        if new_cover_file and new_cover_file.filename:
            if game['cover_url'] and 'static/covers/' in game['cover_url']:
                old_cover_path = os.path.join(current_app.root_path, game['cover_url'].replace('/static/', 'static/'))
                if os.path.exists(old_cover_path):
                    os.remove(old_cover_path)
            _, cover_extension = os.path.splitext(new_cover_file.filename)
            unique_cover_filename = f"{uuid4()}{cover_extension}"
            cover_path = os.path.join(current_app.config['COVERS_FOLDER'], unique_cover_filename)
            os.makedirs(current_app.config['COVERS_FOLDER'], exist_ok=True)
            new_cover_file.save(cover_path)
            updated_cover_url = url_for('static', filename=f'covers/{unique_cover_filename}')
        elif igdb_cover_url_input:
            if game['cover_url'] and 'static/covers/' in game['cover_url']:
                old_cover_path = os.path.join(current_app.root_path, game['cover_url'].replace('/static/', 'static/'))
                if os.path.exists(old_cover_path):
                    os.remove(old_cover_path)
            try:
                response = requests.get(igdb_cover_url_input, stream=True)
                response.raise_for_status()
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
                os.makedirs(current_app.config['COVERS_FOLDER'], exist_ok=True)
                with open(cover_path, 'wb') as out_file:
                    shutil.copyfileobj(response.raw, out_file)
                updated_cover_url = url_for('static', filename=f'covers/{unique_cover_filename}')
            except requests.exceptions.RequestException as req_e:
                flash(f"Could not download IGDB cover (Network Error): {req_e}", "warning")
                updated_cover_url = game['cover_url']
            except Exception as e:
                flash(f"Could not download IGDB cover (General Error): {e}", "warning")
                updated_cover_url = game['cover_url']
        elif 'clear_cover' in request.form:
            if game['cover_url'] and 'static/covers/' in game['cover_url']:
                old_cover_path = os.path.join(current_app.root_path, game['cover_url'].replace('/static/', 'static/'))
                if os.path.exists(old_cover_path):
                    os.remove(old_cover_path)
            updated_cover_url = None
        conn = get_db_connection()
        try:
            conn.execute('''
                UPDATE games SET title = ?, system = ?, filepath = ?, cover_url = ?, original_filename = ?
                WHERE id = ?
            ''', (new_title, final_system, updated_filepath, updated_cover_url, updated_original_filename, game_id))
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
        if game['filepath'] and os.path.exists(game['filepath']):
            if os.path.isdir(game['filepath']):
                shutil.rmtree(game['filepath'])
            else:
                os.remove(game['filepath'])
        if game['cover_url'] and 'static/covers/' in game['cover_url']:
            cover_path = os.path.join(current_app.root_path, game['cover_url'].replace('/static/', 'static/'))
            if os.path.exists(cover_path):
                os.remove(cover_path)
        conn.execute('DELETE FROM games WHERE id = ?', (game_id,))
        conn.commit()
        flash(f"Game '{game['title']}' deleted successfully.", 'success')
    except Exception as e:
        flash(f'An error occurred during deletion: {e}', 'error')
        current_app.logger.error(f"Error deleting game {game_id}: {e}", exc_info=True)
    finally:
        conn.close()
    return redirect(url_for('library.library', system=game['system']))
