# scanner/config.py
# Central configuration for the Scanner GUI application.
from pathlib import Path

# --- Paths ---
# The base directory is the parent of this file's directory (i.e., the project root)
BASE_DIR = Path(__file__).resolve().parent.parent

# --- FIX: Point to the correct database file name: 'library.db' ---
# This aligns the scanner with the web application's actual database.
DATABASE_PATH = BASE_DIR / 'library.db'
UPLOAD_FOLDER = BASE_DIR / 'uploads'
SETTINGS_FILE = BASE_DIR / 'scanner' / 'gui_settings.json'

# Added for emulator management
EMULATORS_FOLDER = BASE_DIR / 'emulators'
#igdb SETTINGS
IGDB_CLIENT_ID = ""  # Replace with your actual iGDB client ID
IGDB_CLIENT_SECRET = ""  # Replace with your actual iGDB client secret
# --- Mappings ---
# Mapping of file extensions to system names for intelligent guessing.
EXTENSION_TO_SYSTEM = {
    '.sfc': 'Super Nintendo', '.smc': 'Super Nintendo',
    '.nes': 'Nintendo Entertainment System',
    '.gb': 'Game Boy', '.gbc': 'Game Boy Color',
    '.gba': 'Game Boy Advance',
    '.gen': 'Sega Genesis', '.md': 'Sega Genesis', '.smd': 'Sega Genesis',
    '.n64': 'Nintendo 64', '.z64': 'Nintendo 64',
    '.nds': 'Nintendo DS',
    '.iso': 'PlayStation 1', '.bin': 'PlayStation 1', '.cue': 'PlayStation 1', '.chd': 'PlayStation 1',
    '.ps1': 'PlayStation 1', # Common alternate extension for PS1 isos
    '.wii': 'Nintendo Wii', # For Dolphin
    '.gc': 'Nintendo GameCube', # For Dolphin
    '.cxb': 'Xbox', # For Xemu
    '.3ds': 'Nintendo 3DS', # For Citra
    '.cia': 'Nintendo 3DS', # For Citra
    '.nsp': 'Nintendo Switch', # For Yuzu/Ryujinx
    '.xci': 'Nintendo Switch', # For Yuzu/Ryujinx
    '.rpx': 'Nintendo Wii U', # For Cemu
    '.wud': 'Nintendo Wii U', # For Cemu
    '.exe': 'PC', # Generic for PC games, if you want to manage those
}

# --- Emulator Configurations ---
# Dictionary of recommended emulators with their download URLs and supported systems.
EMULATORS = {
    "RetroArch": {
        "url": "https://buildbot.libretro.com/stable/2024-03-24/windows/x86_64/RetroArch.7z", 
        "executable_name": "retroarch.exe",
        "systems": ["Super Nintendo", "Nintendo Entertainment System", "Game Boy", "Game Boy Color", "Game Boy Advance", "Sega Genesis", "Nintendo 64", "Nintendo DS", "PlayStation 1", "Atari 2600", "Game Gear"]
    },
    "SNES9x": {
        "url": "https://github.com/snes9xgit/snes9x/releases/download/1.63/snes9x-1.63-win32-x64.zip",
        "executable_name": "snes9x-x64.exe",
        "systems": ["Super Nintendo"]
    },
    "mGBA": {
        "url": "https://github.com/mgba-emu/mgba/releases/download/0.10.5/mGBA-0.10.5-win64.7z",
        "executable_name": "mGBA.exe", # Common executable name
        "systems": ["Game Boy", "Game Boy Color", "Game Boy Advance"]
    },
    "VBA-M": {
        "url": "https://github.com/visualboyadvance-m/visualboyadvance-m/releases/download/v2.2.0/visualboyadvance-m-Win-x86_64.zip",
        "executable_name": "visualboyadvance-m.exe", # Common executable name
        "systems": ["Game Boy", "Game Boy Color", "Game Boy Advance"]
    },
    "Dolphin": {
        "url": "https://dolphin-emu.org/download/list/master/latest/?n=deluxe", # Placeholder, try to find direct zip/7z
        "executable_name": "Dolphin.exe", 
        "systems": ["Nintendo GameCube", "Nintendo Wii"]
    },
    "PCSX2": {
        "url": "https://pcsx2.net/downloads/", # Placeholder, try to find direct zip/7z
        "executable_name": "pcsx2.exe",
        "systems": ["PlayStation 2"]
    },
    "RPCS3": {
        "url": "https://rpcs3.net/download", # Placeholder, try to find direct zip/7z
        "executable_name": "rpcs3.exe",
        "systems": ["PlayStation 3"]
    },
    "Cemu": {
        "url": "https://cemu.info/#download", # Placeholder, try to find direct zip/7z
        "executable_name": "Cemu.exe",
        "systems": ["Nintendo Wii U"]
    },
    "Citra": {
        "url": "https://citra-emu.org/download/", # Placeholder, try to find direct zip/7z
        "executable_name": "citra-qt.exe", 
        "systems": ["Nintendo 3DS"]
    },
    "Yuzu": {
        "url": "https://yuzu-emu.org/downloads/", # Placeholder, consider Ryujinx instead
        "executable_name": "yuzu.exe", 
        "systems": ["Nintendo Switch"]
    },
    "Ryujinx": {
        "url": "https://ryujinx.org/download", # Placeholder, try to find direct zip/7z
        "executable_name": "Ryujinx.exe",
        "systems": ["Nintendo Switch"]
    },
    "Xemu": {
        "url": "https://xemu.app/#downloads", # Placeholder, try to find direct zip/7z
        "executable_name": "xemu.exe",
        "systems": ["Xbox"]
    },
}
