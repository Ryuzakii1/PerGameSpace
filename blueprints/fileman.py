# blueprints/fileman.py - File Manager Blueprint
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from scanner.core import get_db_connection, download_and_set_cover_image, set_game_cover_image
from blueprints.igdb import construct_igdb_image_url
from werkzeug.utils import secure_filename
import os
import tempfile
import json
import sqlite3
import zipfile
from pathlib import Path

fileman_bp = Blueprint('fileman', __name__)

@fileman_bp.route('/upload', methods=['GET', 'POST'])
def upload_game():
    """Handles game file uploads and metadata."""
    conn = get_db_connection()
    systems = conn.execute('SELECT name FROM systems ORDER BY name').fetchall()
    conn.close()
    
    if request.method == 'POST':
        try:
            # Get form data
            title = request.form.get('title', '').strip()
            system = request.form.get('system', '').strip()
            new_system_name = request.form.get('new_system_name', '').strip()
            genre = request.form.get('genre', '').strip()
            release_year = request.form.get('release_year', '').strip()
            developer = request.form.get('developer', '').strip()
            publisher = request.form.get('publisher', '').strip()
            description = request.form.get('description', '').strip()
            
            # Use new system name if provided
            if new_system_name:
                system = new_system_name
                # Add new system to database
                conn = get_db_connection()
                conn.execute('INSERT OR IGNORE INTO systems (name) VALUES (?)', (system,))
                conn.commit()
                conn.close()
            
            if not title or not system:
                flash('Title and system are required!', 'error')
                return redirect(url_for('fileman.upload_game'))
            
            # Handle file upload
            if 'game_file' not in request.files:
                flash('No game file provided!', 'error')
                return redirect(url_for('fileman.upload_game'))
            
            game_file = request.files['game_file']
            if game_file.filename == '':
                flash('No game file selected!', 'error')
                return redirect(url_for('fileman.upload_game'))
            
            # Secure the filename
            original_filename = secure_filename(game_file.filename)
            
            # Create system directory
            safe_system = "".join(c for c in system if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')
            system_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_system)
            os.makedirs(system_dir, exist_ok=True)
            
            file_path = os.path.join(system_dir, original_filename)
            game_file.save(file_path)

            # Check if the uploaded file is a ZIP and extract it
            if original_filename.lower().endswith('.zip'):
                try:
                    extract_path = os.path.splitext(file_path)[0] # Extract to a folder with the same name
                    os.makedirs(extract_path, exist_ok=True)
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        zf.extractall(extract_path)
                    os.remove(file_path) # Delete the original zip file
                    file_path = extract_path # The new filepath is the directory
                except Exception as e:
                    flash(f"Error extracting ZIP file: {e}", 'error')
                    current_app.logger.error(f"Error extracting ZIP file: {e}")
                    return redirect(url_for('fileman.upload_game'))
            
            # Prepare metadata
            metadata = {
                'genre': genre if genre else None,
                'release_year': int(release_year) if release_year.isdigit() else None,
                'developer': developer if developer else None,
                'publisher': publisher if publisher else None,
                'description': description if description else None,
                'play_status': 'Not Played'
            }
            
            # Add to database
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO games (title, system, filepath, original_filename, genre, release_year, 
                                 developer, publisher, description, play_status, cover_image_path) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, system, file_path, original_filename, metadata['genre'], 
                  metadata['release_year'], metadata['developer'], metadata['publisher'], 
                  metadata['description'], metadata['play_status'], None))
            
            game_id = cursor.lastrowid
            conn.commit()
            conn.close()
            print(f"DEBUG: Newly inserted game ID is: {game_id}")
            
            # Handle IGDB cover if provided
            igdb_image_id = request.form.get('igdb_cover_image_id', '').strip()
            if igdb_image_id:
                try:
                    def web_log(message, tag=None):
                        current_app.logger.info(f"[{tag or 'INFO'}] {message}")
                    
                    full_igdb_url = construct_igdb_image_url(igdb_image_id)
                    download_and_set_cover_image(game_id, full_igdb_url, web_log)
                    flash('Game uploaded successfully with IGDB cover!', 'success')
                except Exception as e:
                    current_app.logger.error(f"Error downloading IGDB cover: {e}")
                    flash('Game uploaded successfully, but cover download failed.', 'warning')
            else:
                # Handle custom cover upload
                if 'cover_file' in request.files:
                    cover_file = request.files['cover_file']
                    if cover_file and cover_file.filename:
                        try:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(cover_file.filename)[1]) as tmp_file:
                                cover_file.save(tmp_file.name)
                                set_game_cover_image(game_id, tmp_file.name)
                                flash('Game uploaded successfully with custom cover!', 'success')
                            
                            os.unlink(tmp_file.name)
                        except Exception as e:
                            current_app.logger.error(f"Error uploading cover: {e}")
                            flash('Game uploaded successfully, but cover upload failed.', 'warning')
                else:
                    flash('Game uploaded successfully!', 'success')
            
            return redirect(url_for('library.game_detail', game_id=game_id))
            
        except Exception as e:
            current_app.logger.error(f"Error uploading game: {e}")
            flash(f'Error uploading game: {str(e)}', 'error')
    
    return render_template('upload.html', systems=systems)

@fileman_bp.route('/batch_upload', methods=['GET', 'POST'])
def batch_upload():
    """Handle batch file uploads (multiple games at once)."""
    if request.method == 'POST':
        flash('Batch upload functionality coming soon!', 'info')
        return redirect(url_for('fileman.upload_game'))
    
    return render_template('batch_upload.html')

@fileman_bp.route('/scan_directory', methods=['GET', 'POST'])
def scan_directory():
    """Scan a directory for games and import them."""
    if request.method == 'POST':
        scan_path = request.form.get('scan_path', '').strip()
        if not scan_path or not os.path.exists(scan_path):
            flash('Invalid directory path!', 'error')
            return redirect(url_for('fileman.scan_directory'))
        
        try:
            from scanner.core import scan_directory, import_games
            
            def web_log(message, tag=None):
                current_app.logger.info(f"[{tag or 'INFO'}] {message}")
            
            games_found = list(scan_directory(scan_path, web_log))
            
            if not games_found:
                flash('No new games found in the specified directory.', 'info')
                return redirect(url_for('fileman.scan_directory'))
            
            import_mode = request.form.get('import_mode', 'reference')
            imported_games = list(import_games(games_found, import_mode, web_log))
            
            successful_imports = sum(1 for result in imported_games if result['success'])
            flash(f'Successfully imported {successful_imports} out of {len(games_found)} games found.', 'success')
            
        except Exception as e:
            current_app.logger.error(f"Error scanning directory: {e}")
            flash(f'Error scanning directory: {str(e)}', 'error')
        
        return redirect(url_for('navigation.library'))
    
    return render_template('scan_directory.html')

@fileman_bp.route('/manage_files')
def manage_files():
    """File management interface - view and organize uploaded files."""
    try:
        upload_folder = current_app.config['UPLOAD_FOLDER']
        file_structure = {}
        
        for root, dirs, files in os.walk(upload_folder):
            rel_path = os.path.relpath(root, upload_folder)
            if rel_path == '.':
                rel_path = ''
            
            if files:
                file_structure[rel_path] = {
                    'full_path': root,
                    'files': files,
                    'file_count': len(files)
                }
        
        return render_template('manage_files.html', file_structure=file_structure)
        
    except Exception as e:
        current_app.logger.error(f"Error managing files: {e}")
        flash(f'Error accessing files: {str(e)}', 'error')
        return redirect(url_for('navigation.index'))