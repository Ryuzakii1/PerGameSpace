import os
import json
from flask import current_app # Import current_app because these functions need app.config

def get_setting(key, default=None):
    # These functions need to be able to access current_app.config['SETTINGS_FILE']
    # If they are called from a Blueprint, current_app will be available.
    # If called directly from run.py (e.g., init_db), then current_app might not be set,
    # so we might pass the app instance directly if called outside a request context.
    # For now, let's assume they are called within an app context.
    settings_file = current_app.config['SETTINGS_FILE']
    if not os.path.exists(settings_file):
        return default
    try:
        with open(settings_file, 'r') as f:
            settings = json.load(f)
        return settings.get(key, default)
    except json.JSONDecodeError:
        # Handle cases where settings.json might be empty or malformed
        return default


def set_setting(key, value):
    settings_file = current_app.config['SETTINGS_FILE']
    settings = {}
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r') as f:
                settings = json.load(f)
        except json.JSONDecodeError:
            # If the file is malformed, start with an empty settings dict
            pass
    settings[key] = value
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=4)