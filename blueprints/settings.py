# blueprints/settings.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, jsonify
import os # Import os for path operations
from tkinter import filedialog, Tk # For the folder picker dialog - Note: this runs on the server!

# CORRECTED IMPORT: Use 'set_setting' instead of 'save_setting'
from utils import get_setting, set_setting, get_effective_path # Import get_effective_path
from config import Config # Import Config to get default paths and setting keys
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
        set_setting('theme', request.form.get('theme'))
        set_setting('igdb_client_id', request.form.get('igdb_client_id', '').strip())
        set_setting('igdb_client_secret', request.form.get('igdb_client_secret', '').strip())

        # --- Handle Custom File Storage Paths ---
        custom_upload_folder = request.form.get('custom_upload_folder', '').strip()
        custom_covers_folder = request.form.get('custom_covers_folder', '').strip()

        # Save only if a value is provided and it's a valid directory or empty to reset to default
        if custom_upload_folder:
            if os.path.isdir(custom_upload_folder):
                set_setting(Config.CUSTOM_UPLOAD_FOLDER_SETTING_KEY, custom_upload_folder)
            else:
                flash(f"Invalid path for Game ROMs Folder: '{custom_upload_folder}'. Path not saved.", 'error')
        else: # If empty, clear the custom setting to revert to default
            set_setting(Config.CUSTOM_UPLOAD_FOLDER_SETTING_KEY, "")

        if custom_covers_folder:
            if os.path.isdir(custom_covers_folder):
                set_setting(Config.CUSTOM_COVERS_FOLDER_SETTING_KEY, custom_covers_folder)
            else:
                flash(f"Invalid path for Cover Images Folder: '{custom_covers_folder}'. Path not saved.", 'error')
        else: # If empty, clear the custom setting to revert to default
            set_setting(Config.CUSTOM_COVERS_FOLDER_SETTING_KEY, "")


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

    # Get current effective paths for display
    current_upload_folder = get_effective_path(Config.CUSTOM_UPLOAD_FOLDER_SETTING_KEY, 'UPLOAD_FOLDER')
    current_covers_folder = get_effective_path(Config.CUSTOM_COVERS_FOLDER_SETTING_KEY, 'COVERS_FOLDER')
    
    # Get default paths from Config for display
    default_upload_folder = current_app.config['UPLOAD_FOLDER']
    default_covers_folder = current_app.config['COVERS_FOLDER']

    return render_template(
        'settings.html',
        title="Settings",
        current_theme=current_theme,
        themes=themes,
        get_setting=get_setting, # Pass the helper function to the template
        emulator_statuses=emulator_statuses, # Pass the corrected data structure
        current_upload_folder=current_upload_folder, # NEW
        current_covers_folder=current_covers_folder, # NEW
        default_upload_folder=default_upload_folder, # NEW
        default_covers_folder=default_covers_folder # NEW
    )

@settings_bp.route('/browse_directory')
def browse_directory():
    """
    Opens a folder selection dialog on the server-side and returns the selected path.
    NOTE: This will open a GUI dialog on the SERVER machine, not the client's browser.
    This feature is typically for desktop applications, or for specific server setups.
    For a true web application, you would need client-side file system access APIs (like
    the File System Access API), which are browser-specific and require user permissions.
    """
    root = Tk()
    root.withdraw() # Hide the main window
    root.wm_attributes('-topmost', 1) # Keep dialog on top
    selected_path = filedialog.askdirectory(
        parent=root,
        title="Select Folder"
    )
    root.destroy() # Destroy the Tkinter root window
    return jsonify({"selected_path": selected_path})