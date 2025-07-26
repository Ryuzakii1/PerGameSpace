import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

from utils import get_setting, set_setting

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    current_theme = get_setting('theme', 'modern') 
    
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
        # This prevents using an old token with new credentials
        igdb_token_file = current_app.config['IGDB_TOKEN_FILE']
        if os.path.exists(igdb_token_file):
            # Check if values actually changed before deleting.
            # This is a bit more robust but for now just delete if values are different.
            # For simplicity, let's always delete the token file if settings are submitted.
            try:
                os.remove(igdb_token_file)
                flash("IGDB access token cleared. A new one will be requested.", "info")
            except Exception as e:
                flash(f"Could not clear old IGDB token: {e}", "warning")

        # After saving settings, reload them into app.config for immediate use
        # This is CRUCIAL for the IGDB blueprint to pick up new client ID/secret
        # without restarting the entire app.
        current_app.config['IGDB_CLIENT_ID'] = igdb_client_id
        current_app.config['IGDB_CLIENT_SECRET'] = igdb_client_secret

        return redirect(url_for('settings.settings'))

    return render_template('settings.html', current_theme=current_theme) # Pass current_theme to template