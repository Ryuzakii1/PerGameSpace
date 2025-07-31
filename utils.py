import os
import json
# Import the Config class directly instead of relying on the Flask app context
from config import Config

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
