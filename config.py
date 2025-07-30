import os

# Get the base directory of the application
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Flask application configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_strong_unique_secret_key_here' # **CHANGE THIS TO A STRONG, UNIQUE KEY**

    # File paths
    # Define the root folder for all game ROMs, where system subfolders will be created
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'roms')
    # Define a temporary folder for initial uploads before processing (NEW)
    TEMP_UPLOAD_FOLDER = os.path.join(basedir, 'static', 'temp_uploads') 
    COVERS_FOLDER = os.path.join(basedir, 'static', 'covers')
    DATABASE = os.path.join(basedir, 'library.db')
    SETTINGS_FILE = os.path.join(basedir, 'settings.json')
    
    # Ensure directories exist (can be done here or in app factory)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True) # Ensure temp upload folder exists (NEW)
    os.makedirs(COVERS_FOLDER, exist_ok=True)

    # IGDB Configuration
    IGDB_CLIENT_ID = os.environ.get('IGDB_CLIENT_ID') or 'YOUR_IGDB_CLIENT_ID' # <-- REPLACE WITH YOUR CLIENT ID
    IGDB_CLIENT_SECRET = os.environ.get('IGDB_CLIENT_SECRET') or 'YOUR_IGDB_CLIENT_SECRET' # <-- REPLACE WITH YOUR CLIENT SECRET
    IGDB_TOKEN_FILE = os.path.join(basedir, 'igdb_token.json')

    # Define themes (if not dynamically loaded from settings.json)
    THEMES = ['modern', 'dark', 'light', 'retro'] # Add more as you create them

    # Other settings can go here if needed for different environments
    DEBUG = True # For development
    # TESTING = False