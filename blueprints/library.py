from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from scanner.core import get_db_connection, delete_games_from_db, update_game_metadata_in_db, download_and_set_cover_image, set_game_cover_image
from blueprints.igdb import construct_igdb_image_url
import json
import os
import tempfile
import sqlite3

library_bp = Blueprint('library', __name__)

@library_bp.route('/<int:game_id>')
def game_detail(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    conn.close()
    
    if game is None:
        flash('Game not found!', 'error')
        return redirect(url_for('navigation.library'))
    
    from blueprints.emulation import _get_rom_paths_for_serving
    
    try:
        game_obj, actual_file_to_serve, directory_to_serve_from, filename_to_serve, original_filename, is_web_playable = _get_rom_paths_for_serving(game_id)
        
        web_emulator_url = None
        desktop_emulator_url = None
        download_url = None
        
        if is_web_playable and filename_to_serve:
            web_emulator_url = url_for('emulation.play_web_emulator', game_id=game_id)
        
        desktop_emulator_url = url_for('emulation.launch_game', game_id=game_id)
        
        if actual_file_to_serve and os.path.exists(actual_file_to_serve):
            download_url = None
            
    except Exception as e:
        current_app.logger.error(f"Error checking emulator compatibility for game {game_id}: {e}")
        web_emulator_url = None
        desktop_emulator_url = None
        download_url = None
    
    return render_template('game_detail.html', 
                         game=game,
                         web_emulator_url=web_emulator_url,
                         desktop_emulator_url=desktop_emulator_url,
                         download_url=download_url)

@library_bp.route('/<int:game_id>/edit', methods=['GET', 'POST'])
def edit_game(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    
    if request.method == 'POST':
        try:
            changes = {
                'title': request.form.get('title'),
                'system': request.form.get('system'),
                'genre': request.form.get('genre'),
                'release_year': request.form.get('release_year'),
                'developer': request.form.get('developer'),
                'publisher': request.form.get('publisher'),
                'description': request.form.get('description'),
                'play_status': request.form.get('play_status')
            }
            
            for key, value in changes.items():
                if value == '':
                    changes[key] = None
                elif key == 'release_year' and value:
                    try:
                        changes[key] = int(value)
                    except ValueError:
                        changes[key] = None
            
            # Handle IGDB cover (new logic)
            igdb_image_id = request.form.get('igdb_cover_image_id')
            if igdb_image_id and igdb_image_id.strip():
                try:
                    def web_log(message, tag=None):
                        current_app.logger.info(f"[{tag or 'INFO'}] {message}")
                    
                    full_igdb_url = construct_igdb_image_url(igdb_image_id.strip())
                    new_cover_filename = download_and_set_cover_image(game_id, full_igdb_url, web_log)
                    if new_cover_filename:
                        changes['cover_image_path'] = new_cover_filename
                        flash('Cover image downloaded from IGDB successfully!', 'success')
                    
                except Exception as e:
                    current_app.logger.error(f"Error downloading IGDB cover: {e}")
                    flash(f'Error downloading cover from IGDB: {str(e)}', 'error')
            
            # Handle custom cover upload
            if 'cover_file' in request.files:
                cover_file = request.files['cover_file']
                if cover_file and cover_file.filename:
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(cover_file.filename)[1]) as tmp_file:
                            cover_file.save(tmp_file.name)
                            new_cover_filename = set_game_cover_image(game_id, tmp_file.name)
                            if new_cover_filename:
                                changes['cover_image_path'] = new_cover_filename
                                flash('Custom cover image uploaded successfully!', 'success')
                        
                        os.unlink(tmp_file.name)
                        
                    except Exception as e:
                        current_app.logger.error(f"Error uploading cover: {e}")
                        flash(f'Error uploading cover image: {str(e)}', 'error')
            
            # Handle clear cover checkbox
            if request.form.get('clear_cover'):
                changes['cover_image_path'] = None
                flash('Cover image cleared.', 'info')
            
            update_game_metadata_in_db(game_id, changes)
            flash('Game updated successfully!', 'success')
            return redirect(url_for('library.game_detail', game_id=game_id))
            
        except Exception as e:
            current_app.logger.error(f"Error updating game {game_id}: {e}")
            flash(f'Error updating game: {str(e)}', 'error')

    if game is None:
        flash('Game not found!', 'error')
        return redirect(url_for('navigation.library'))
    
    systems = conn.execute('SELECT name FROM systems ORDER BY name').fetchall()
    conn.close()
    return render_template('edit_game.html', game=game, systems=systems)

@library_bp.route('/<int:game_id>/delete', methods=['POST'])
def delete_game(game_id):
    def web_log(message, tag=None):
        current_app.logger.info(f"[{tag or 'INFO'}] {message}")

    try:
        delete_games_from_db([game_id], web_log)
        flash('Game deleted successfully!', 'success')
    except Exception as e:
        current_app.logger.error(f"Error deleting game {game_id}: {e}")
        flash(f'Error deleting game: {str(e)}', 'error')
    
    return redirect(url_for('navigation.library'))