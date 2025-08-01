import os
import json
# Import the Config class directly instead of relying on the Flask app context
from config import Config
from flask import current_app # Import current_app for accessing app.config

def load_settings():
    """Helper function to load settings from the JSON file, handling empty or corrupt files."""
    # Get the settings file path directly from the Config object
    settings_file = Config.SETTINGS_FILE
    if not os.path.exists(settings_file):
        return {}
    try:
        with open(settings_file, 'r') as f:
            content = f.read()
            if not content: # Handle case where the file is empty
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, IOError):
        # Handle cases where settings.json might be malformed or unreadable
        return {}

def get_setting(key, default=None):
    """Gets a single value from the settings JSON file."""
    settings = load_settings()
    return settings.get(key, default)

def set_setting(key, value):
    """Saves a single key-value pair to the settings JSON file."""
    settings_file = Config.SETTINGS_FILE
    settings = load_settings() # Use the robust loader
    settings[key] = value
    try:
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=4)
    except IOError as e:
        print(f"Error saving settings file: {e}")

def get_effective_path(setting_key_for_custom_path, default_config_key):
    """
    Determines the effective path for a folder by checking user settings first,
    then falling back to the default path defined in Config.
    
    Args:
        setting_key_for_custom_path (str): The key in settings.json where the user's custom path is stored.
        default_config_key (str): The attribute name in Config (e.g., 'UPLOAD_FOLDER') for the default path.
    Returns:
        str: The effective path.
    """
    custom_path = get_setting(setting_key_for_custom_path)
    if custom_path and os.path.isdir(custom_path):
        return custom_path
    
    # Fallback to the default path from Config
    # We need current_app.config to get the default path defined in Config object
    # This function should only be called within a Flask application context.
    return current_app.config.get(default_config_key)