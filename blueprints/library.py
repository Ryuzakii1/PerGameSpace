# blueprints/library.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
import os
from werkzeug.utils import secure_filename

# Import the unified core functions
from scanner.core import get_all_games_from_db, update_game_metadata_in_db, delete_games_from_db, set_game_cover_image, get_db_connection

library_bp = Blueprint('library', __name__)

@library_bp.route('/')
def index():
    """Renders the main library page."""
    games = get_all_games_from_db()
    return render_template('index.html', games=games)

@library_bp.route('/game/<int:game_id>')
def game_detail(game_id):
    """Renders the detail page for a single game."""
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    conn.close()
    if game is None:
        return "Game not found", 404
    return render_template('game_detail.html', game=game)

@library_bp.route('/edit/<int:game_id>', methods=['GET', 'POST'])
def edit_game(game_id):
    """Handles editing a game's metadata."""
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    
    if request.method == 'POST':
        changes = {
            'title': request.form['title'],
            'system': request.form['system'],
            'genre': request.form['genre'],
            'release_year': request.form['release_year'],
            'developer': request.form['developer'],
            'publisher': request.form['publisher'],
            'description': request.form['description'],
            'play_status': request.form['play_status']
        }
        
        # Handle cover image upload
        if 'cover_image' in request.files:
            file = request.files['cover_image']
            if file.filename != '':
                # Create a temporary path to pass to the core function
                temp_path = os.path.join('/tmp', secure_filename(file.filename))
                file.save(temp_path)
                # Use the core function to handle copying and DB update
                set_game_cover_image(game_id, temp_path)
                os.remove(temp_path) # Clean up temp file

        # Use the core function to update metadata
        update_game_metadata_in_db(game_id, changes)
        
        flash('Game updated successfully!', 'success')
        conn.close()
        return redirect(url_for('library.game_detail', game_id=game_id))

    conn.close()
    return render_template('edit_game.html', game=game)

@library_bp.route('/delete/<int:game_id>', methods=['POST'])
def delete_game(game_id):
    """Handles deleting a game."""
    def web_log(message, tag=None):
        print(f"[{tag or 'INFO'}] {message}")

    # Use the core function to delete the game from DB and filesystem
    delete_games_from_db([game_id], web_log)
    
    flash('Game deleted successfully!', 'success')
    return redirect(url_for('library.index'))
