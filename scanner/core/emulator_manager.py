# scanner/core/emulator_manager.py
import os
import sqlite3
import requests
import zipfile
from pathlib import Path
import subprocess
import shutil

try:
    import py7zr
except ImportError:
    py7zr = None 

from .database import get_db_connection
from ..config import EMULATORS, EMULATORS_FOLDER

# (Existing _find_7zip_executable and get_emulator_statuses functions - NO CHANGE)

# NEW FUNCTION: save_emulator_path_to_db
def save_emulator_path_to_db(emulator_name, emulator_path, install_type, log_callback):
    """Saves or updates an emulator's path in the database.
    This function is reusable for both downloads and manual path settings."""
    try:
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO emulator_configs (emulator_name, emulator_path, install_type) VALUES (?, ?, ?)", 
                     (emulator_name, emulator_path, install_type))
        conn.commit()
        conn.close()
        log_callback(f"Database: Saved '{emulator_name}' path: {emulator_path} (type: {install_type}).", "info")
    except Exception as e:
        log_callback(f"Database Error: Could not save path for '{emulator_name}': {e}", "error")
        raise # Re-raise the exception so the calling thread can handle it (e.g., in its finally block)

# Modify download_and_setup_emulator to use the new function
def download_and_setup_emulator(emu_name, progress_callback, log_callback):
    """Downloads, unzips/un7zips, and configures an emulator."""
    emu_data = EMULATORS.get(emu_name)
    if not emu_data:
        log_callback(f"Error: No configuration found for '{emu_name}'.", "error")
        return

    os.makedirs(EMULATORS_FOLDER, exist_ok=True)
    zip_filename = Path(emu_data['url']).name
    zip_path = EMULATORS_FOLDER / zip_filename
    
    try:
        log_callback(f"Downloading {emu_name} from {emu_data['url']}...")
        with requests.get(emu_data['url'], stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            bytes_downloaded = 0
            with open(zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    if total_size > 0:
                        progress = (bytes_downloaded / total_size) * 100
                        progress_callback(emu_name, f"Downloading... {progress:.1f}%")
        log_callback("Download complete.")
    except Exception as e:
        log_callback(f"Error downloading {emu_name}: {e}", "error")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise # Re-raise to be caught by _run_download's finally block in UI module

    extract_folder = EMULATORS_FOLDER / Path(zip_filename).stem
    
    try:
        log_callback(f"Extracting to {extract_folder}...")
        progress_callback(emu_name, "Extracting...")
        
        if zip_path.suffix.lower() == '.zip':
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_folder)
        elif zip_path.suffix.lower() == '.7z':
            extraction_successful = False
            if py7zr:
                try:
                    with py7zr.SevenZipFile(zip_path, mode='r') as zf:
                        zf.extractall(path=extract_folder)
                    extraction_successful = True
                except py7zr.exceptions.Bad7zFile as e:
                    log_callback(f"Warning: py7zr could not extract (possibly unsupported filter like BCJ2): {e}. Attempting with external 7z.exe...", "warning")
                except Exception as e:
                    log_callback(f"Warning: py7zr extraction failed: {e}. Attempting with external 7z.exe...", "warning")

            if not extraction_successful:
                seven_z_exe = _find_7zip_executable()
                if seven_z_exe:
                    log_callback(f"Using external 7z.exe found at: {seven_z_exe}", "info")
                    try:
                        command = [seven_z_exe, 'x', str(zip_path), f'-o{extract_folder}', '-y']
                        result = subprocess.run(command, capture_output=True, text=True, check=True)
                        log_callback(f"7z.exe output:\n{result.stdout}")
                        if result.stderr:
                            log_callback(f"7z.exe errors:\n{result.stderr}", "warning")
                        extraction_successful = True
                    except subprocess.CalledProcessError as e:
                        log_callback(f"Error calling external 7z.exe: {e}\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}", "error")
                    except FileNotFoundError:
                        log_callback(f"Error: 7z.exe not found at '{seven_z_exe}'. Please ensure 7-Zip is installed and in your system PATH.", "error")
                else:
                    log_callback("Error: External 7z.exe not found. Cannot extract this .7z archive.", "error")
            
            if not extraction_successful:
                raise Exception("Failed to extract .7z archive using both py7zr and external 7z.exe.")

        else:
            log_callback(f"Error: Unsupported archive format '{zip_path.suffix}'. Only .zip and .7z are supported for automatic extraction.", "error")
            raise # Re-raise for error handling in calling function

        log_callback("Extraction complete.")
    except Exception as e:
        log_callback(f"Error extracting {emu_name}: {e}", "error")
        if os.path.exists(extract_folder) and os.path.isdir(extract_folder):
            import shutil
            shutil.rmtree(extract_folder)
        raise # Re-raise for error handling in calling function
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

    try:
        progress_callback(emu_name, "Configuring...")
        executable_path = None
        for root, _, files in os.walk(extract_folder):
            for file in files:
                if file.lower() == emu_data['executable_name'].lower():
                    executable_path = os.path.join(root, file)
                    break
            if executable_path: break
        
        if not executable_path:
            raise FileNotFoundError(f"Could not find '{emu_data['executable_name']}' in extracted files.")

        log_callback(f"Found executable: {executable_path}")
        # Use the new centralized save_emulator_path_to_db function
        save_emulator_path_to_db(emu_name, executable_path, 'local', log_callback) 
        
        log_callback(f"Successfully configured {emu_name}!")
        progress_callback(emu_name, "Installed")
    except Exception as e:
        log_callback(f"Error configuring {emu_name}: {e}", "error")
        progress_callback(emu_name, "Config Failed")
        raise # Re-raise for _run_download's finally block