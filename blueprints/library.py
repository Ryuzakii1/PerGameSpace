from flask import Blueprint, render_template, request, redirect, url_for, flash
from scanner.core import get_db_connection, delete_games_from_db, update_game_metadata_in_db

library_bp = Blueprint('library', __name__)

@library_bp.route('/<int:game_id>')
def game_detail(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    conn.close()
    if game is None:
        flash('Game not found!', 'error')
        return redirect(url_for('navigation.library'))
    return render_template('game_detail.html', game=game)

@library_bp.route('/<int:game_id>/edit', methods=['GET', 'POST'])
def edit_game(game_id):
    conn = get_db_connection()
    game = conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone()
    
    if request.method == 'POST':
        # --- Final dictionary with all fields ---
        changes = {
            'title': request.form.get('title'),
            'system': request.form.get('system'),
            'genre': request.form.get('genre'),
            'release_year': request.form.get('release_year'),
            'developer': request.form.get('developer'),
            'publisher': request.form.get('publisher'),
            'description': request.form.get('description'),
            'play_status': request.form.get('play_status') # Get play_status from the form
        }
        update_game_metadata_in_db(game_id, changes)
        flash('Game updated successfully!', 'success')
        return redirect(url_for('library.game_detail', game_id=game_id))

    if game is None:
        flash('Game not found!', 'error')
        return redirect(url_for('navigation.library'))
    systems = conn.execute('SELECT name FROM systems ORDER BY name').fetchall()
    conn.close()
    return render_template('edit_game.html', game=game, systems=systems)

@library_bp.route('/<int:game_id>/delete', methods=['POST'])
def delete_game(game_id):
    def web_log(message, tag=None):
        print(f"[{tag or 'INFO'}] {message}")

    delete_games_from_db([game_id], web_log)
    flash('Game deleted successfully!', 'success')
    return redirect(url_for('navigation.library'))