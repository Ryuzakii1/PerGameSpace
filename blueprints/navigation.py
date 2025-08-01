# blueprints/navigation.py - Navigation and routing only
from flask import Blueprint, render_template, request, redirect, url_for, flash
from scanner.core import get_all_games_from_db, get_db_connection

navigation_bp = Blueprint('navigation', __name__)

@navigation_bp.route('/')
def index():
    """Renders the main homepage (index.html)."""
    conn = get_db_connection()
    systems_with_counts = conn.execute('''
        SELECT s.name, COUNT(g.id) as count
        FROM systems s LEFT JOIN games g ON s.name = g.system
        GROUP BY s.name HAVING COUNT(g.id) > 0 ORDER BY s.name
    ''').fetchall()
    conn.close()

    systems_data = [{
        'name': system['name'],
        'count': system['count'],
        'url': url_for('navigation.library', system_name=system['name']),
        'image_url': url_for('static', filename='placeholder.png')
    } for system in systems_with_counts]

    return render_template('index.html', systems=systems_data)

@navigation_bp.route('/library')
@navigation_bp.route('/library/<string:system_name>')
def library(system_name=None):
    """Renders the game library page, optionally filtered by system."""
    if system_name:
        games = get_all_games_from_db(system_name=system_name)
        title = f"Games on {system_name}"
    else:
        games = get_all_games_from_db()
        title = "My Game Library"
        
    return render_template('library.html', games=games, current_display_title=title, current_system_name=system_name)

@navigation_bp.route('/about')
def about():
    """About page for the application."""
    return render_template('about.html')

@navigation_bp.route('/help')
def help():
    """Help and documentation page."""
    return render_template('help.html')