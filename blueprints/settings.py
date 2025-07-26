import os
import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

from utils import get_setting, set_setting

settings_bp = Blueprint('settings', __name__)

# Helper function to get DB connection (copied from library_bp for consistency)
def get_db_connection():
    conn = sqlite3.connect(current_app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    conn = get_db_connection()
    current_theme = get_setting('theme', 'modern') 
    
    # Fetch all available systems from the 'systems' table
    # We order by name to make the list consistent
    available_systems = conn.execute('SELECT name FROM systems ORDER BY name').fetchall()
    
    # Fetch all existing emulator configurations
    # We join with 'systems' to ensure we only get configs for valid systems
    # and order by system_name for consistent display.
    emulator_configs = conn.execute('SELECT * FROM emulator_configs ORDER BY system_name').fetchall()

    if request.method == 'POST':
        # --- Handle Theme Setting ---
        selected_theme = request.form.get('theme')
        if selected_theme and selected_theme in current_app.config['THEMES']:
            set_setting('theme', selected_theme) 
            flash('Theme updated successfully!', 'success')
        else:
            flash('Invalid theme selected.', 'error')

        # --- Handle IGDB Settings ---
        igdb_client_id = request.form.get('igdb_client_id', '').strip()
        igdb_client_secret = request.form.get('igdb_client_secret', '').strip()

        # Update IGDB settings
        set_setting('igdb_client_id', igdb_client_id)
        set_setting('igdb_client_secret', igdb_client_secret)
        flash('IGDB credentials updated.', 'success')

        # Optionally, clear the IGDB token file if credentials changed to force a new token
        igdb_token_file = current_app.config['IGDB_TOKEN_FILE']
        if os.path.exists(igdb_token_file):
            try:
                os.remove(igdb_token_file)
                flash("IGDB access token cleared. A new one will be requested.", "info")
            except Exception as e:
                flash(f"Could not clear old IGDB token: {e}", "warning")

        # After saving settings, reload them into app.config for immediate use
        current_app.config['IGDB_CLIENT_ID'] = igdb_client_id
        current_app.config['IGDB_CLIENT_SECRET'] = igdb_client_secret

        # --- Handle Emulator Path Settings ---
        # This loop iterates through all available systems and checks if a path was submitted for them.
        for system in available_systems:
            system_name = system['name']
            form_field_name = f'emulator_path_{system_name.lower().replace(" ", "_").replace(".", "").replace("&", "and")}'
            emulator_path = request.form.get(form_field_name, '').strip()

            # Check if an existing config for this system exists
            existing_config = conn.execute('SELECT * FROM emulator_configs WHERE system_name = ?', (system_name.lower(),)).fetchone()

            if emulator_path: # If a path was provided in the form
                if existing_config:
                    # Update existing path
                    conn.execute('UPDATE emulator_configs SET emulator_path = ? WHERE system_name = ?', 
                                 (emulator_path, system_name.lower()))
                    flash(f"Emulator path for {system_name} updated.", 'success')
                else:
                    # Insert new path
                    conn.execute('INSERT INTO emulator_configs (system_name, emulator_path) VALUES (?, ?)', 
                                 (system_name.lower(), emulator_path))
                    flash(f"Emulator path for {system_name} added.", 'success')
            elif existing_config: # If path was cleared from form but existed in DB
                conn.execute('DELETE FROM emulator_configs WHERE system_name = ?', (system_name.lower(),))
                flash(f"Emulator path for {system_name} cleared.", 'info')

        conn.commit() # Commit all changes related to emulator configs
        conn.close() # Close connection after all operations

        return redirect(url_for('settings.settings'))

    # For GET request, render the template
    conn.close() # Close connection for GET request after fetching data
    return render_template('settings.html', 
                           current_theme=current_theme,
                           available_systems=available_systems, # Pass available systems
                           emulator_configs=emulator_configs) # Pass existing configs
