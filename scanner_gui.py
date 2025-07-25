# scanner_gui.py (Updated for zip scanning and pretty GUI)
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk # Import ttk!
import threading
import os
import requests
import json
import re
import zipfile # <-- NEW: Import zipfile for zip handling

# --- Configuration for the Scanner (duplicate from scanner.py for self-containment) ---
FLASK_SERVER_URL = "http://127.0.0.1:5000"
API_ADD_GAME_ENDPOINT = f"{FLASK_SERVER_URL}/api/games"
API_CHECK_EXISTS_ENDPOINT = f"{FLASK_SERVER_URL}/api/games/check_exists"
API_GET_SYSTEMS_ENDPOINT = f"{FLASK_SERVER_URL}/api/systems"

SCAN_ALLOWED_EXTENSIONS = {
    'exe', 'nes', 'bin', 'sfc', 'smc', 'gba', 'gbc', 'gb', 'iso', 'zip', 'rom',
    'md', 'n64', 'z64', 'v64', 'nds', 'ps1', 'cue', 'ccd', 'img', 'mdf', 'chd',
    'dsk', 'adf', 'atr',
}

EXTENSION_TO_SYSTEM_MAP = {
    'nes': 'Nintendo Entertainment System', 'sfc': 'Super Nintendo', 'smc': 'Super Nintendo',
    'gb': 'Game Boy', 'gbc': 'Game Boy Color', 'gba': 'Game Boy Advance',
    'n64': 'Nintendo 64', 'z64': 'Nintendo 64', 'v64': 'Nintendo 64',
    'iso': 'PlayStation 1',
    'cue': 'PlayStation 1',
    'md': 'Sega Genesis',
    'nds': 'Nintendo DS',
    'exe': 'Other',
    'zip': 'Other', # Will be overridden by looking inside
    'rom': 'Other',
    'chd': 'Arcade',
    'dsk': 'Other', 'adf': 'Other', 'atr': 'Other',
    'bin': 'Other',
}

# NEW: Ordered list of common ROM extensions, for prioritizing when scanning zips
PREFERRED_ROM_EXTENSIONS_IN_ZIPS = [
    'nes', 'sfc', 'smc', 'gba', 'gbc', 'gb', 'n64', 'z64', 'v64', 'md', 'nds',
    'ps1',
    'cue', 'iso',
    'rom', 'bin', 'chd', 'exe'
]

def clean_game_title_for_api(filename):
    name = os.path.splitext(filename)[0]
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'[_-]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def get_system_from_extension(extension):
    return EXTENSION_TO_SYSTEM_MAP.get(extension.lower(), 'Other')

# NEW Function: determine_system_for_zip, updated to take output_widget for GUI logging
def determine_system_for_zip(zip_filepath, output_widget):
    """
    Analyzes the contents of a zip file to determine the most likely system
    based on the extensions of files within the archive.
    Args:
        zip_filepath (str): The full path to the zip file.
        output_widget (tkinter.scrolledtext.ScrolledText): The widget to send messages to.
    Returns:
        str: The guessed system string, or 'Other' if no specific ROM type is found.
    """
    try:
        with zipfile.ZipFile(zip_filepath, 'r') as zf:
            namelist = zf.namelist()
            
            for preferred_ext in PREFERRED_ROM_EXTENSIONS_IN_ZIPS:
                for internal_name in namelist:
                    if internal_name.lower().endswith(f'.{preferred_ext}'):
                        output_widget.insert(tk.END, f"  -> Found '{internal_name}' inside zip. Guessing system based on .{preferred_ext}\n")
                        output_widget.see(tk.END)
                        return get_system_from_extension(preferred_ext)
            
            for internal_name in namelist:
                internal_ext = internal_name.rsplit('.', 1)[-1].lower()
                if internal_ext in SCAN_ALLOWED_EXTENSIONS and internal_ext != 'zip':
                    output_widget.insert(tk.END, f"  -> Found '{internal_name}' inside zip. Guessing system based on .{internal_ext}\n")
                    output_widget.see(tk.END)
                    return get_system_from_extension(internal_ext)
                    
    except zipfile.BadZipFile:
        output_widget.insert(tk.END, f"  -> Warning: '{zip_filepath}' is a bad or corrupted zip file.\n")
        output_widget.see(tk.END)
    except Exception as e:
        output_widget.insert(tk.END, f"  -> Error processing zip file '{zip_filepath}': {e}\n")
        output_widget.see(tk.END)
        
    output_widget.insert(tk.END, f"  -> No specific ROM type found inside '{os.path.basename(zip_filepath)}'. Defaulting to 'Other'.\n")
    output_widget.see(tk.END)
    return 'Other'

def get_supported_systems_gui(output_widget):
    output_widget.insert(tk.END, f"Attempting to connect to Flask server at {FLASK_SERVER_URL} to get supported systems...\n")
    output_widget.see(tk.END)
    try:
        response = requests.get(API_GET_SYSTEMS_ENDPOINT)
        response.raise_for_status()
        systems = response.json()
        output_widget.insert(tk.END, f"Successfully retrieved supported systems: {', '.join(systems)}\n")
        output_widget.see(tk.END)
        return systems
    except requests.exceptions.ConnectionError:
        output_widget.insert(tk.END, f"Error: Could not connect to Flask server at {FLASK_SERVER_URL}. Is it running?\n")
        output_widget.see(tk.END)
        return []
    except requests.exceptions.RequestException as e:
        output_widget.insert(tk.END, f"Error fetching supported systems from server: {e}\n")
        output_widget.see(tk.END)
        return []

def scan_folder_gui(folder_path, systems_map, output_widget, progress_label, master_window):
    if not os.path.isdir(folder_path):
        master_window.after(0, lambda: output_widget.insert(tk.END, f"Error: Scan path '{folder_path}' is not a valid directory.\n"))
        master_window.after(0, lambda: output_widget.see(tk.END))
        master_window.after(0, lambda: progress_label.config(text="Scan Failed!"))
        return

    master_window.after(0, lambda: output_widget.insert(tk.END, f"Starting scan of: {folder_path}\n"))
    master_window.after(0, lambda: output_widget.see(tk.END))
    master_window.after(0, lambda: progress_label.config(text="Scanning..."))

    found_files_count = 0
    added_games_count = 0
    skipped_games_count = 0
    
    for root, _, files in os.walk(folder_path):
        for filename in files:
            full_local_path = os.path.join(root, filename)
            extension = filename.rsplit('.', 1)[-1].lower()

            if extension not in SCAN_ALLOWED_EXTENSIONS:
                continue

            found_files_count += 1
            
            master_window.after(0, lambda f=filename: output_widget.insert(tk.END, f"Processing: {f}\n"))
            master_window.after(0, lambda: output_widget.see(tk.END))

            try:
                check_response = requests.get(API_CHECK_EXISTS_ENDPOINT, params={'file_path': full_local_path})
                check_response.raise_for_status()
                if check_response.json().get('exists'):
                    master_window.after(0, lambda f=filename: output_widget.insert(tk.END, f"  -> Skipping '{f}': Already in library.\n"))
                    master_window.after(0, lambda: output_widget.see(tk.END))
                    skipped_games_count += 1
                    continue
            except requests.exceptions.RequestException as e:
                master_window.after(0, lambda f=filename, err=e: output_widget.insert(tk.END, f"  -> Error checking existence for '{f}': {err}\n"))
                master_window.after(0, lambda: output_widget.see(tk.END))
                continue

            # --- System Determination Logic (Updated for Zips) ---
            guessed_system = 'Other'
            if extension == 'zip':
                # Pass output_widget to determine_system_for_zip for GUI logging
                guessed_system = determine_system_for_zip(full_local_path, output_widget)
            else:
                guessed_system = get_system_from_extension(extension)
            # --- End System Determination Logic ---
            
            game_title = clean_game_title_for_api(filename)
            
            final_system = 'Other'
            if guessed_system in systems_map:
                final_system = guessed_system
            else:
                found_match = False
                for s in systems_map:
                    if guessed_system.lower() in s.lower() or s.lower() in guessed_system.lower():
                        final_system = s
                        found_match = True
                        break
                if not found_match:
                    master_window.after(0, lambda gs=guessed_system, f=filename: output_widget.insert(tk.END, f"  -> Warning: Guessed system '{gs}' not directly supported. Defaulting to 'Other' for '{f}'.\n"))
                    master_window.after(0, lambda: output_widget.see(tk.END))

            master_window.after(0, lambda f=filename, gt=game_title, fs=final_system: output_widget.insert(tk.END, f"Found '{f}' (Title: '{gt}', System: '{fs}')\n"))
            master_window.after(0, lambda: output_widget.see(tk.END))

            game_data = {
                'filename': filename,
                'title': game_title,
                'system': final_system,
                'file_path': full_local_path, # Path is still to the ZIP file
                'description': '', 
                'cover_url': ''    
            }

            try:
                response = requests.post(API_ADD_GAME_ENDPOINT, json=game_data)
                response.raise_for_status()
                result = response.json()
                master_window.after(0, lambda f=filename, msg=result.get('message'): output_widget.insert(tk.END, f"  -> Added '{f}': {msg}\n"))
                master_window.after(0, lambda: output_widget.see(tk.END))
                added_games_count += 1
            except requests.exceptions.HTTPError as e:
                error_msg = e.response.json().get('error', e.response.text)
                master_window.after(0, lambda f=filename, err=error_msg: output_widget.insert(tk.END, f"  -> Failed to add '{f}': {err}\n"))
                master_window.after(0, lambda: output_widget.see(tk.END))
            except requests.exceptions.RequestException as e:
                master_window.after(0, lambda f=filename, err=e: output_widget.insert(tk.END, f"  -> Network error adding '{f}': {err}\n"))
                master_window.after(0, lambda: output_widget.see(tk.END))
                
    summary_message = f"\n--- Scan Summary ---\n" \
                      f"Files found: {found_files_count}\n" \
                      f"Games added to library: {added_games_count}\n" \
                      f"Games already in library (skipped): {skipped_games_count}\n" \
                      f"Scan complete for: {folder_path}\n"
    master_window.after(0, lambda: output_widget.insert(tk.END, summary_message))
    master_window.after(0, lambda: output_widget.see(tk.END))
    master_window.after(0, lambda: progress_label.config(text="Scan Complete!"))

    master_window.after(0, lambda: output_widget.insert(tk.END, "\nTriggering server's metadata scan for newly added games...\n"))
    master_window.after(0, lambda: output_widget.see(tk.END))
    try:
        requests.get(f"{FLASK_SERVER_URL}/scan_covers") 
        master_window.after(0, lambda: output_widget.insert(tk.END, "Server metadata scan triggered successfully.\n"))
        master_window.after(0, lambda: output_widget.see(tk.END))
    except requests.exceptions.RequestException as e:
        master_window.after(0, lambda err=e: output_widget.insert(tk.END, f"Error triggering server metadata scan: {err}\n"))
        master_window.after(0, lambda: output_widget.see(tk.END))


class ScannerGUI:
    def __init__(self, master):
        self.master = master
        master.title("Game Library Scanner")

        # Optional: Set a theme for a modern look
        try:
            # 'clam' is often a good cross-platform default.
            # Other options: 'alt', 'default', 'classic', 'vista', 'xpnative' (Windows), 'aqua' (macOS)
            ttk.Style().theme_use('clam') 
        except tk.TclError:
            print("Warning: 'clam' theme not available, using default.")

        master.geometry("700x550") # Set initial size
        master.minsize(500, 400) # Set minimum size
        master.resizable(True, True) # Allow resizing

        self.scan_path = tk.StringVar()

        # Main frame for padding and structure
        main_frame = ttk.Frame(master, padding="15 15 15 15") # More padding
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Path selection frame
        path_frame = ttk.Frame(main_frame)
        path_frame.grid(row=0, column=0, columnspan=2, pady=(0,15), sticky="ew") # Increased pady
        main_frame.grid_columnconfigure(1, weight=1) # Allow path_entry to expand

        ttk.Label(path_frame, text="Scan Folder:").pack(side=tk.LEFT, padx=(0, 10)) # Added padx
        self.path_entry = ttk.Entry(path_frame, textvariable=self.scan_path)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10)) # Added padx
        ttk.Button(path_frame, text="Browse...", command=self.browse_folder).pack(side=tk.LEFT) # Changed text

        # Scan button
        self.scan_button = ttk.Button(main_frame, text="Start Scan", command=self.start_scan_thread)
        self.scan_button.grid(row=1, column=0, columnspan=2, pady=10) # Increased pady

        # Progress label
        self.progress_label = ttk.Label(main_frame, text="Ready to scan.", font=('Arial', 10, 'bold'))
        self.progress_label.grid(row=2, column=0, columnspan=2, pady=(5, 15)) # Increased pady

        # Output Textbox (scrolledtext does not have a ttk equivalent, but blends okay)
        # Using a Frame to hold the ScrolledText, might allow for better styling later
        output_frame = ttk.Frame(main_frame, borderwidth=1, relief="sunken") # Add a border for visual separation
        output_frame.grid(row=3, column=0, columnspan=2, pady=(0,10), sticky="nsew")
        main_frame.grid_rowconfigure(3, weight=1) # Allow output_text to expand vertically
        output_frame.grid_columnconfigure(0, weight=1)
        output_frame.grid_rowconfigure(0, weight=1)

        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, font=('Consolas', 9))
        self.output_text.grid(row=0, column=0, sticky="nsew", padx=2, pady=2) # Fill the frame

        self.supported_systems = set()
        self.load_systems()

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.scan_path.set(folder_selected)

    def load_systems(self):
        systems = get_supported_systems_gui(self.output_text)
        if systems:
            self.supported_systems = set(systems)
        else:
            messagebox.showerror("Server Error", "Could not retrieve supported systems from Flask server. Please ensure the server is running and accessible.")
            self.scan_button.config(state=tk.DISABLED)

    def start_scan_thread(self):
        folder = self.scan_path.get()
        if not folder:
            messagebox.showwarning("Input Error", "Please select a folder to scan.")
            return

        self.output_text.delete(1.0, tk.END)
        self.scan_button.config(state=tk.DISABLED)
        self.progress_label.config(text="Starting Scan...")

        # Pass self.master to the scan function for thread-safe GUI updates
        threading.Thread(target=self._run_scan, args=(folder,)).start()

    def _run_scan(self, folder):
        try:
            # Now, scan_folder_gui will handle outputting to output_text directly
            scan_folder_gui(folder, self.supported_systems, self.output_text, self.progress_label, self.master)
        finally:
            self.master.after(100, self.scan_button.config, {'state': tk.NORMAL})

if __name__ == '__main__':
    root = tk.Tk()
    app = ScannerGUI(root)
    root.mainloop()