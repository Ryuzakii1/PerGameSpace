# blueprints/settings.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
import json
import os

# Import the main Config class to get the path to the settings file
from config import Config
# This import works because 'scanner' is a package in the project root
# We import the functions that correctly interact with the database
from scanner.core import get_emulator_statuses, save_emulator_path_to_db, EMULATORS

settings_bp = Blueprint('settings', __name__)

# --- Settings Helper Functions (Restored from your backup's logic) ---

def load_settings():
    """Loads settings from the JSON file defined in the main config."""
    if os.path.exists(Config.SETTINGS_FILE):
        try:
            with open(Config.SETTINGS_FILE, 'r') as f:
                content = f.read()
                if not content:
                    return {}
                return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_setting(key, value):
    """Saves a single key-value pair to the settings JSON file."""
    settings = load_settings()
    settings[key] = value
    try:
        with open(Config.SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except IOError as e:
        print(f"Error saving settings file: {e}")

def get_setting(key, default=None):
    """Gets a single value from the settings JSON file."""
    settings = load_settings()
    return settings.get(key, default)


@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    """
    Handles the application settings page for both viewing and updating.
    """
    if request.method == 'POST':
        # --- Handle Theme and IGDB Settings ---
        save_setting('theme', request.form.get('theme'))
        save_setting('igdb_client_id', request.form.get('igdb_client_id', '').strip())
        save_setting('igdb_client_secret', request.form.get('igdb_client_secret', '').strip())

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
                save_emulator_path_to_db(emu_name, path, 'local', web_log)

        flash('Settings saved successfully!', 'success')
        return redirect(url_for('settings.settings'))

    # --- For GET request, load all settings to display ---
    all_settings = load_settings()
    current_theme = all_settings.get('theme', 'modern')
    themes = current_app.config.get('THEMES', ['modern'])
    
    # CORRECTED: Use the core function to get a unified view of emulator statuses
    # This fetches data by 'emulator_name' which matches the database structure
    emulator_statuses = get_emulator_statuses()

    return render_template(
        'settings.html',
        title="Settings",
        current_theme=current_theme,
        themes=themes,
        get_setting=get_setting, # Pass the helper function to the template
        emulator_statuses=emulator_statuses # Pass the corrected data structure
    )
