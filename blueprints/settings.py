# blueprints/settings.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app

# CORRECTED IMPORT: Use 'set_setting' instead of 'save_setting'
from utils import get_setting, set_setting
# This import works because 'scanner' is a package in the project root
from scanner.core import get_emulator_statuses, save_emulator_path_to_db, EMULATORS

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    """
    Handles the application settings page for both viewing and updating.
    """
    if request.method == 'POST':
        # --- Handle Theme and IGDB Settings ---
        # CORRECTED: Use the correct function name 'set_setting'
        set_setting('theme', request.form.get('theme'))
        set_setting('igdb_client_id', request.form.get('igdb_client_id', '').strip())
        set_setting('igdb_client_secret', request.form.get('igdb_client_secret', '').strip())

        # --- Handle Emulator Path Settings ---
        # Loop through the known emulators from the config file
        for emu_name in EMULATORS.keys():
            # Construct the form field name, e.g., 'emulator_path_snes9x'
            form_field_name = f"emulator_path_{emu_name.lower().replace(' ', '_')}"
            if form_field_name in request.form:
                path = request.form[form_field_name].strip()
                
                # For the web app, we can just print logs to the console
                def web_log(message, tag=None):
                    print(f"[{tag or 'INFO'}] {message}")
                
                # Use the core function to save the path to the database
                # Assume 'local' install type for paths set via the web UI
                save_emulator_path_to_db(emu_name, path, 'local', web_log)

        flash('Settings saved successfully!', 'success')
        return redirect(url_for('settings.settings'))

    # --- For GET request, load all settings to display ---
    current_theme = get_setting('theme', 'modern')
    themes = current_app.config.get('THEMES', ['modern'])
    
    # Use the core function to get a unified view of emulator statuses
    emulator_statuses = get_emulator_statuses()

    return render_template(
        'settings.html',
        title="Settings",
        current_theme=current_theme,
        themes=themes,
        get_setting=get_setting, # Pass the helper function to the template
        emulator_statuses=emulator_statuses # Pass the corrected data structure
    )
