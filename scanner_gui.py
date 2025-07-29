import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import threading
import os
import requests
import json
import re
import zipfile
import sys # Import sys for better error handling output

# --- Configuration for the Scanner (duplicate from scanner.py for self-containment) ---
FLASK_SERVER_URL = "http://127.0.0.1:5000"
API_ADD_GAME_ENDPOINT = f"{FLASK_SERVER_URL}/api/games"
API_CHECK_EXISTS_ENDPOINT = f"{FLASK_SERVER_URL}/api/games/check_exists"
API_GET_SYSTEMS_ENDPOINT = f"{FLASK_SERVER_URL}/api/systems"
API_UPDATE_EMULATOR_PATH_ENDPOINT = f"{FLASK_SERVER_URL}/api/settings/update_emulator_path" 

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
        output_widget.insert(tk.END, f"Error: Could not connect to Flask server at {FLASK_SERVER_URL}. Is it running? (Connection Refused)\n")
        output_widget.see(tk.END)
        print(f"ERROR: Could not connect to Flask server at {FLASK_SERVER_URL}. Please ensure it is running.") # Print to console for debugging
        return []
    except requests.exceptions.RequestException as e:
        output_widget.insert(tk.END, f"Error fetching supported systems from server: {e}\n")
        output_widget.see(tk.END)
        print(f"ERROR: RequestException fetching supported systems: {e}") # Print to console
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
                'filepath': full_local_path, # Path is still to the ZIP file
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
        master.title("Game Library Scanner & Settings") # Updated title

        self.style = ttk.Style()
        try:
            self.style.theme_use('clam') 
        except tk.TclError:
            print("Warning: 'clam' theme not available, using default.")

        master.geometry("750x650") # Set initial size, slightly larger
        master.minsize(600, 500) # Set minimum size
        master.resizable(True, True)

        self.scan_path = tk.StringVar()
        self.emulator_path_var = tk.StringVar() # For the emulator path input
        self.selected_system_for_emulator = tk.StringVar() # For the combobox selection
        
        # Settings variables
        self.dark_mode_enabled = tk.BooleanVar(value=False) # Default to light mode
        self.hide_copy_log_button_var = tk.BooleanVar(value=False) # Default to show button

        # Main frame for padding and structure
        main_frame = ttk.Frame(master, padding="15 15 15 15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create a Notebook (tabbed interface)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # --- Scan Tab ---
        scan_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(scan_tab, text="Scan Games")

        # Path selection frame (inside scan_tab)
        path_frame = ttk.Frame(scan_tab)
        path_frame.grid(row=0, column=0, columnspan=2, pady=(0,15), sticky="ew")
        scan_tab.grid_columnconfigure(1, weight=1)

        ttk.Label(path_frame, text="Scan Folder:").pack(side=tk.LEFT, padx=(0, 10))
        self.path_entry = ttk.Entry(path_frame, textvariable=self.scan_path)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(path_frame, text="Browse Folder...", command=self.browse_folder).pack(side=tk.LEFT)

        # Scan button (inside scan_tab)
        self.scan_button = ttk.Button(scan_tab, text="Start Scan", command=self.start_scan_thread)
        self.scan_button.grid(row=1, column=0, columnspan=2, pady=10)

        # Progress label (inside scan_tab)
        self.progress_label = ttk.Label(scan_tab, text="Ready to scan.", font=('Arial', 10, 'bold'))
        self.progress_label.grid(row=2, column=0, columnspan=2, pady=(5, 15))

        # --- Emulator Settings Tab ---
        emulator_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(emulator_tab, text="Emulator Paths")

        # Emulator path setting frame
        emulator_settings_frame = ttk.LabelFrame(emulator_tab, text="Set Emulator Executable Path", padding="15")
        emulator_settings_frame.pack(fill=tk.X, pady=10, padx=5)

        # System selection for emulator
        ttk.Label(emulator_settings_frame, text="Select System:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.system_combobox = ttk.Combobox(emulator_settings_frame, textvariable=self.selected_system_for_emulator, state="readonly")
        self.system_combobox.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        emulator_settings_frame.grid_columnconfigure(1, weight=1) # Allow combobox to expand

        # Emulator path input
        ttk.Label(emulator_settings_frame, text="Emulator Path:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.emulator_path_entry = ttk.Entry(emulator_settings_frame, textvariable=self.emulator_path_var)
        self.emulator_path_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(emulator_settings_frame, text="Browse File...", command=self.browse_emulator_file).grid(row=1, column=2, padx=5, pady=5)

        # Send path button
        self.send_emulator_path_button = ttk.Button(emulator_settings_frame, text="Send Path to Web App", command=self.start_send_emulator_path_thread)
        self.send_emulator_path_button.grid(row=2, column=0, columnspan=3, pady=10)

        # --- Settings Tab ---
        settings_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(settings_tab, text="Settings")

        settings_frame = ttk.LabelFrame(settings_tab, text="Application Settings", padding="15")
        settings_frame.pack(fill=tk.X, pady=10, padx=5)

        # Dark Mode Checkbox
        self.dark_mode_checkbox = ttk.Checkbutton(
            settings_frame, 
            text="Enable Dark Mode", 
            variable=self.dark_mode_enabled, 
            command=self.apply_dark_mode
        )
        self.dark_mode_checkbox.pack(anchor=tk.W, pady=5)

        # Hide Copy Log Checkbox
        self.hide_copy_log_checkbox = ttk.Checkbutton(
            settings_frame,
            text="Hide 'Copy Log' Button",
            variable=self.hide_copy_log_button_var,
            command=self.toggle_copy_log_button_visibility
        )
        self.hide_copy_log_checkbox.pack(anchor=tk.W, pady=5)


        # Output Textbox (shared between tabs)
        output_frame = ttk.Frame(main_frame, borderwidth=1, relief="sunken")
        output_frame.pack(fill=tk.BOTH, expand=True, pady=(0,10), padx=5) # Use pack for shared widget
        output_frame.grid_columnconfigure(0, weight=1)
        output_frame.grid_rowconfigure(0, weight=1)

        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, font=('Consolas', 9))
        self.output_text.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        # NEW: Copy Log Button
        self.copy_log_button = ttk.Button(output_frame, text="Copy Log", command=self.copy_log_to_clipboard)
        self.copy_log_button.grid(row=1, column=0, pady=(5, 0), sticky="e") # Placed at the bottom right of the output frame

        self.supported_systems = [] # Changed to list for combobox values
        
        # IMPORTANT CHANGE: Delay load_systems so GUI can draw first
        master.after(100, self.load_systems)
            
        # Apply initial settings
        self.apply_dark_mode() # Apply default theme
        self.toggle_copy_log_button_visibility() # Apply default visibility

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.scan_path.set(folder_selected)

    def browse_emulator_file(self):
        # Use askopenfilename to get the full path of an executable
        file_selected = filedialog.askopenfilename(
            title="Select Emulator Executable",
            filetypes=[("Executables", "*.exe *.app *.sh *.bat"), ("All files", "*.*")]
        )
        if file_selected:
            self.emulator_path_var.set(file_selected)
            self.output_text.insert(tk.END, f"Selected emulator file: {file_selected}\n")
            self.output_text.see(tk.END)

    def load_systems(self):
        systems = get_supported_systems_gui(self.output_text)
        if systems:
            self.supported_systems = sorted(systems) # Sort for combobox
            self.system_combobox['values'] = self.supported_systems
            if self.supported_systems:
                self.selected_system_for_emulator.set(self.supported_systems[0]) # Set default selection
        else:
            messagebox.showerror("Server Error", "Could not retrieve supported systems from Flask server. Please ensure the server is running and accessible.")
            self.scan_button.config(state=tk.DISABLED)
            self.send_emulator_path_button.config(state=tk.DISABLED)

    def start_scan_thread(self):
        folder = self.scan_path.get()
        if not folder:
            messagebox.showwarning("Input Error", "Please select a folder to scan.")
            return

        self.output_text.delete(1.0, tk.END)
        self.scan_button.config(state=tk.DISABLED)
        self.progress_label.config(text="Starting Scan...")

        threading.Thread(target=self._run_scan, args=(folder,)).start()

    def _run_scan(self, folder):
        try:
            scan_folder_gui(folder, self.supported_systems, self.output_text, self.progress_label, self.master)
        finally:
            self.master.after(100, self.scan_button.config, {'state': tk.NORMAL})

    def start_send_emulator_path_thread(self):
        system_name = self.selected_system_for_emulator.get()
        emulator_path = self.emulator_path_var.get()

        if not system_name:
            messagebox.showwarning("Input Error", "Please select a system from the dropdown.")
            return
        if not emulator_path:
            messagebox.showwarning("Input Error", "Please select or type the emulator path.")
            return
            
        self.output_text.insert(tk.END, f"Attempting to send emulator path for '{system_name}' to web app...\n")
        self.output_text.see(tk.END)
        self.send_emulator_path_button.config(state=tk.DISABLED)

        threading.Thread(target=self._send_emulator_path, args=(system_name, emulator_path)).start()

    def _send_emulator_path(self, system_name, emulator_path):
        try:
            payload = {
                "system_name": system_name,
                "emulator_path": emulator_path
            }
            response = requests.post(API_UPDATE_EMULATOR_PATH_ENDPOINT, json=payload)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            
            result = response.json()
            self.master.after(0, lambda: self.output_text.insert(tk.END, f"Successfully updated path for '{system_name}': {result.get('message', 'No message from server')}\n"))
            self.master.after(0, lambda: self.output_text.see(tk.END))
            messagebox.showinfo("Success", f"Emulator path for {system_name} updated successfully!")

        except requests.exceptions.HTTPError as e:
            error_msg = e.response.json().get('error', e.response.text)
            self.master.after(0, lambda: self.output_text.insert(tk.END, f"Error updating path for '{system_name}': {error_msg}\n"))
            self.master.after(0, lambda: self.output_text.see(tk.END))
            messagebox.showerror("API Error", f"Failed to update emulator path: {error_msg}")
        except requests.exceptions.ConnectionError:
            self.master.after(0, lambda: self.output_text.insert(tk.END, f"Error: Could not connect to Flask server at {FLASK_SERVER_URL}. Is it running?\n"))
            self.master.after(0, lambda: self.output_text.see(tk.END))
            messagebox.showerror("Connection Error", "Could not connect to Flask server. Please ensure it is running.")
        except Exception as e:
            self.master.after(0, lambda: self.output_text.insert(tk.END, f"An unexpected error occurred: {e}\n"))
            self.master.after(0, lambda: self.output_text.see(tk.END))
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        finally:
            self.master.after(100, self.send_emulator_path_button.config, {'state': tk.NORMAL})

    def copy_log_to_clipboard(self):
        """Copies the entire content of the output_text widget to the clipboard."""
        try:
            log_content = self.output_text.get(1.0, tk.END) # Get all text from the widget
            if log_content.strip(): # Only copy if there's content
                self.master.clipboard_clear()
                self.master.clipboard_append(log_content)
                self.output_text.insert(tk.END, "\n--- Log content copied to clipboard! ---\n")
                self.output_text.see(tk.END)
            else:
                self.output_text.insert(tk.END, "\n--- Log is empty, nothing to copy. ---\n")
                self.output_text.see(tk.END)
        except Exception as e:
            messagebox.showerror("Copy Error", f"Failed to copy log to clipboard: {e}")

    def apply_dark_mode(self):
        """Applies or removes the dark mode theme."""
        if self.dark_mode_enabled.get():
            # Dark Mode Colors
            bg_color = "#2e2e2e"
            fg_color = "#ffffff"
            entry_bg = "#4a4a4a"
            entry_fg = "#ffffff"
            button_bg = "#555555"
            button_fg = "#ffffff"
            select_bg = "#0078d7" # A nice blue for selected items
            select_fg = "#ffffff"

            self.master.config(bg=bg_color)
            self.style.configure('.', background=bg_color, foreground=fg_color)
            self.style.configure('TFrame', background=bg_color)
            self.style.configure('TLabel', background=bg_color, foreground=fg_color)
            self.style.configure('TButton', background=button_bg, foreground=button_fg, borderwidth=1, focusthickness=3, focuscolor=select_bg)
            self.style.map('TButton', background=[('active', '#666666')])
            self.style.configure('TEntry', fieldbackground=entry_bg, foreground=entry_fg, bordercolor=button_bg)
            self.style.configure('TCombobox', fieldbackground=entry_bg, foreground=entry_fg, selectbackground=select_bg, selectforeground=select_fg)
            self.style.map('TCombobox', fieldbackground=[('readonly', entry_bg)], selectbackground=[('readonly', select_bg)])
            self.style.configure('TNotebook', background=bg_color, borderwidth=0)
            self.style.configure('TNotebook.Tab', background=button_bg, foreground=button_fg, lightcolor=button_bg, darkcolor=button_bg)
            self.style.map('TNotebook.Tab', background=[('selected', select_bg)], foreground=[('selected', select_fg)])
            self.style.configure('TLabelframe', background=bg_color, foreground=fg_color, bordercolor=button_bg)
            self.style.configure('TLabelframe.Label', background=bg_color, foreground=fg_color)
            self.style.configure('TCheckbutton', background=bg_color, foreground=fg_color)

            # ScrolledText (tk.Text) needs direct configuration
            self.output_text.config(bg="#3a3a3a", fg="#ffffff", insertbackground="#ffffff") # Darker background for log
            self.output_text.tag_config("info", foreground="#ffffff")
            self.output_text.tag_config("warning", foreground="#ffcc00")
            self.output_text.tag_config("error", foreground="#ff6666")

        else:
            # Light Mode Colors (default clam theme)
            # Resetting to default theme values (or a known light theme)
            self.style.theme_use('clam') # Re-apply clam to reset
            self.master.config(bg=self.style.lookup('TFrame', 'background'))
            self.style.configure('.', background=self.style.lookup('TFrame', 'background'), foreground=self.style.lookup('TLabel', 'foreground'))
            self.style.configure('TFrame', background=self.style.lookup('TFrame', 'background'))
            self.style.configure('TLabel', background=self.style.lookup('TLabel', 'background'), foreground=self.style.lookup('TLabel', 'foreground'))
            self.style.configure('TButton', background=self.style.lookup('TButton', 'background'), foreground=self.style.lookup('TButton', 'foreground'), borderwidth=1, focusthickness=3, focuscolor='')
            self.style.map('TButton', background=[('active', self.style.lookup('TButton', 'background', state=['active']))])
            self.style.configure('TEntry', fieldbackground=self.style.lookup('TEntry', 'fieldbackground'), foreground=self.style.lookup('TEntry', 'foreground'), bordercolor=self.style.lookup('TEntry', 'bordercolor'))
            self.style.configure('TCombobox', fieldbackground=self.style.lookup('TCombobox', 'fieldbackground'), foreground=self.style.lookup('TCombobox', 'foreground'), selectbackground=self.style.lookup('TCombobox', 'selectbackground'), selectforeground=self.style.lookup('TCombobox', 'selectforeground'))
            self.style.map('TCombobox', fieldbackground=[('readonly', self.style.lookup('TCombobox', 'fieldbackground', state=['readonly']))], selectbackground=[('readonly', self.style.lookup('TCombobox', 'selectbackground', state=['readonly']))])
            self.style.configure('TNotebook', background=self.style.lookup('TNotebook', 'background'), borderwidth=0)
            self.style.configure('TNotebook.Tab', background=self.style.lookup('TNotebook.Tab', 'background'), foreground=self.style.lookup('TNotebook.Tab', 'foreground'), lightcolor=self.style.lookup('TNotebook.Tab', 'lightcolor'), darkcolor=self.style.lookup('TNotebook.Tab', 'darkcolor'))
            self.style.map('TNotebook.Tab', background=[('selected', self.style.lookup('TNotebook.Tab', 'background', state=['selected']))], foreground=[('selected', self.style.lookup('TNotebook.Tab', 'foreground', state=['selected']))])
            self.style.configure('TLabelframe', background=self.style.lookup('TLabelframe', 'background'), foreground=self.style.lookup('TLabelframe', 'foreground'), bordercolor=self.style.lookup('TLabelframe', 'bordercolor'))
            self.style.configure('TLabelframe.Label', background=self.style.lookup('TLabelframe.Label', 'background'), foreground=self.style.lookup('TLabelframe.Label', 'foreground'))
            self.style.configure('TCheckbutton', background=self.style.lookup('TCheckbutton', 'background'), foreground=self.style.lookup('TCheckbutton', 'foreground'))


            self.output_text.config(bg="white", fg="black", insertbackground="black")
            self.output_text.tag_config("info", foreground="black")
            self.output_text.tag_config("warning", foreground="orange")
            self.output_text.tag_config("error", foreground="red")


    def toggle_copy_log_button_visibility(self):
        """Hides or shows the 'Copy Log' button based on the checkbox state."""
        if self.hide_copy_log_button_var.get():
            self.copy_log_button.grid_forget() # Remove from layout
        else:
            # Re-add to layout with its original grid parameters
            self.copy_log_button.grid(row=1, column=0, pady=(5, 0), sticky="e")


if __name__ == '__main__':
    root = tk.Tk()
    try:
        app = ScannerGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"An unhandled error occurred during GUI startup or mainloop: {e}", file=sys.stderr)
        messagebox.showerror("Critical Error", f"The application encountered a critical error and needs to close:\n\n{e}\n\nCheck the console for more details.")
        sys.exit(1) # Exit with an error code
