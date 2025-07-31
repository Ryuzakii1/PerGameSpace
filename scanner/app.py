# scanner/app.py
# Contains the main ScannerGUI class and all Tkinter UI code.

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk, simpledialog
import threading
import os
import sys
import json
import inspect

# Import configuration
from .config import SETTINGS_FILE, EMULATORS

# --- Core Function Imports ---
try:
    from .core import (
        get_db_connection,
        scan_directory,
        import_games,
        get_emulator_statuses,
        download_and_setup_emulator,
        save_emulator_path_to_db,
        backup_application_data,
        restore_application_data,
        fetch_igdb_data, # CORRECTED: Use the new function name
        BASE_DIR
    )
    core_import_successful = True
except ImportError as e:
    core_import_successful = False
    print(f"\n--- CRITICAL: Core Import FAILED: {e} ---")

# Import UI creation functions from separate files
from .utils.theme_utils import apply_widget_theme_recursive
from .ui.emuman_tab import create_emulator_manager_tab
from .ui.webapp_setup_tab import create_webapp_setup_tab
from .ui.scan_tab import create_scan_tab
from .ui.settings_tab import create_settings_tab
from .ui.scan_review_dialog import ScanReviewDialog
from .ui.library_tab import create_library_tab


def log_message(widget, message, tag=None):
    """Appends a message to a ScrolledText widget with optional color-coding."""
    if not widget:
        return
    try:
        widget.tag_config("error", foreground="red")
        widget.tag_config("success", foreground="green")
        widget.tag_config("warning", foreground="orange")
        widget.tag_config("info", foreground="#007acc")
        widget.config(state=tk.NORMAL)
        if not message.endswith('\n'):
            message += '\n'
        if tag in ("error", "success", "warning", "info"):
            widget.insert(tk.END, message, (tag,))
        else:
            widget.insert(tk.END, message)
        widget.see(tk.END)
        widget.config(state=tk.DISABLED)
    except tk.TclError as e:
        print(f"TclError in log_message (widget likely destroyed): {e}")
    except Exception as e:
        print(f"Error in log_message: {e}")


class ScannerGUI:
    """Main class for the Game Library Manager GUI."""
    def __init__(self, master):
        self.master = master
        master.title("Game Library Manager")
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            self.style.theme_use('default')
        master.geometry("950x750") # Increased width for new tab
        master.minsize(800, 600)

        if not core_import_successful:
            messagebox.showerror("Fatal Error", "A critical component failed to load. Check console for errors.")
            master.destroy()
            return

        self.settings = self.load_settings()

        # --- Variable Declarations ---
        self.scan_path = tk.StringVar()
        self.import_mode = tk.StringVar(value=self.settings.get("import_mode", "copy"))
        self.dark_mode_enabled = tk.BooleanVar(value=self.settings.get("dark_mode", False))
        self.log_window_visible_var = tk.BooleanVar(value=not self.settings.get("hide_log_output", True))
        
        self.supported_systems = []
        self.last_selected_tab_text = None

        self.igdb_client_id = tk.StringVar(value=self.settings.get("igdb_client_id", ""))
        self.igdb_client_secret = tk.StringVar(value=self.settings.get("igdb_client_secret", ""))

        self.base_dir = BASE_DIR
        self.EMULATORS = EMULATORS

        # --- Log Window Management ---
        self.log_window = None
        self.output_text = None
        self.log_buffer = []

        # --- GUI Layout ---
        main_frame = ttk.Frame(master, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=0)
        main_frame.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        self.status_label = ttk.Label(main_frame, text="Ready.", anchor="w", font=('TkDefaultFont', 9))
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(5,5), padx=5)

        # Call UI creation functions to build the tabs
        create_scan_tab(self.notebook, self)
        create_library_tab(self.notebook, self)
        create_webapp_setup_tab(self.notebook, self)
        create_emulator_manager_tab(self.notebook, self)
        create_settings_tab(self.notebook, self)

        # --- Final Setup ---
        master.after(100, self.load_systems_from_db)
        self.apply_dark_mode()
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        if self.log_window_visible_var.get():
            self.toggle_log_window()

    def on_closing(self):
        self.save_settings()
        self.master.destroy()

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f: return json.load(f)
            except json.JSONDecodeError: return {}
        return {}

    def save_settings(self):
        settings_data = {
            "dark_mode": self.dark_mode_enabled.get(),
            "hide_log_output": not self.log_window_visible_var.get(),
            "import_mode": self.import_mode.get(),
            "igdb_client_id": self.igdb_client_id.get(),
            "igdb_client_secret": self.igdb_client_secret.get(),
        }
        with open(SETTINGS_FILE, 'w') as f: json.dump(settings_data, f, indent=4)

    def on_tab_change(self, event):
        """Refresh data when switching to certain tabs."""
        selected_tab_index = self.notebook.index(self.notebook.select())
        current_tab_text = self.notebook.tab(selected_tab_index, "text")
        
        if current_tab_text != self.last_selected_tab_text:
            if current_tab_text == "Emulator Manager":
                from .ui.emuman_tab import refresh_emulator_statuses
                refresh_emulator_statuses(self, force_refresh=True)
            elif current_tab_text == "Library Management":
                from .ui.library_tab import refresh_library_view
                refresh_library_view(self)

        self.last_selected_tab_text = current_tab_text

    def log(self, message, tag=None):
        self.log_buffer.append({'message': message, 'tag': tag})
        if len(self.log_buffer) > 500: self.log_buffer.pop(0)
        if self.log_window and self.output_text:
            self.master.after(0, log_message, self.output_text, message, tag)

    def update_main_status(self, message, status_type="info", duration_ms=5000):
        color_map = {"info": "#007acc", "success": "green", "error": "red", "warning": "orange"}
        status_fg = color_map.get(status_type, self.style.lookup('TLabel', 'foreground'))
        self.master.after(0, lambda: self.status_label.config(text=message, foreground=status_fg))
        if duration_ms > 0:
            self.master.after(duration_ms, lambda: self.status_label.config(text=""))

    def apply_dark_mode(self):
        is_dark = self.dark_mode_enabled.get()
        self.log(f"Applying {'dark' if is_dark else 'light'} theme.", "info")
        if is_dark:
            bg, fg, entry_bg, btn_bg, active_bg, sel_bg, sel_fg = "#2e2e2e", "#d0d0d0", "#3c3c3c", "#555555", "#666666", "#005a9e", "#ffffff"
        else:
            bg, fg, entry_bg, btn_bg, active_bg, sel_bg, sel_fg = "#f0f0f0", "#000000", "#ffffff", "#e1e1e1", "#c0c0c0", "#0078d7", "#ffffff"
        self.style.configure('.', background=bg, foreground=fg, borderwidth=1)
        self.style.configure('TFrame', background=bg)
        self.style.configure('TLabel', background=bg, foreground=fg)
        self.style.configure('TButton', background=btn_bg, foreground=fg, relief="raised")
        self.style.map('TButton', background=[('active', active_bg)])
        self.style.configure('TEntry', fieldbackground=entry_bg, foreground=fg, borderwidth=1, relief="flat")
        self.style.configure('TCombobox', fieldbackground=entry_bg, foreground=fg, selectbackground=sel_bg, selectforeground=sel_fg)
        self.style.map('TCombobox', fieldbackground=[('readonly', entry_bg)])
        self.style.configure('TNotebook', background=bg, borderwidth=0)
        self.style.configure('TNotebook.Tab', background=btn_bg, foreground=fg, padding=[5, 2])
        self.style.map('TNotebook.Tab', background=[('selected', sel_bg), ('active', active_bg)], foreground=[('selected', sel_fg)])
        self.style.configure('TLabelframe', background=bg, borderwidth=1, relief="groove")
        self.style.configure('TLabelframe.Label', background=bg, foreground=fg)
        self.style.configure('TCheckbutton', background=bg, foreground=fg)
        self.style.configure('TRadiobutton', background=bg, foreground=fg)
        self.style.configure('Treeview', background=entry_bg, fieldbackground=entry_bg, foreground=fg, rowheight=25)
        self.style.map('Treeview', background=[('selected', sel_bg)], foreground=[('selected', sel_fg)])
        self.style.configure('Treeview.Heading', background=btn_bg, foreground=fg, font=('TkDefaultFont', 9, 'bold'), relief="raised")
        self.style.map('Treeview.Heading', background=[('active', active_bg)])
        self.master.config(bg=bg)
        if self.output_text: self.output_text.config(bg=entry_bg, fg=fg, insertbackground=fg)
        apply_widget_theme_recursive(self.master, bg, fg, entry_bg)
        if self.log_window: self.log_window.config(bg=bg)
        self.master.update_idletasks()

    def toggle_log_window(self):
        if self.log_window_visible_var.get():
            if not self.log_window or not self.log_window.winfo_exists():
                self._create_log_window()
        else:
            if self.log_window and self.log_window.winfo_exists():
                self._destroy_log_window()

    def _create_log_window(self):
        self.log_window = tk.Toplevel(self.master)
        self.log_window.title("Log Output")
        self.log_window.transient(self.master)
        self.master.update_idletasks()
        main_x, main_y, main_w, main_h = self.master.winfo_x(), self.master.winfo_y(), self.master.winfo_width(), self.master.winfo_height()
        self.log_window.geometry(f"{main_w}x200+{main_x}+{main_y + main_h}")
        log_frame = ttk.Frame(self.log_window, padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.output_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=('Consolas', 9), state=tk.DISABLED)
        self.output_text.pack(fill=tk.BOTH, expand=True, side=tk.TOP, pady=(0, 5))
        copy_button = ttk.Button(log_frame, text="Copy Log", command=self.copy_log_to_clipboard)
        copy_button.pack(anchor="e")
        for entry in self.log_buffer:
            log_message(self.output_text, entry['message'], entry['tag'])
        self.log_window.protocol("WM_DELETE_WINDOW", self._on_log_window_close)
        self.apply_dark_mode()

    def _destroy_log_window(self):
        if self.log_window: self.log_window.destroy()
        self.log_window = None
        self.output_text = None

    def _on_log_window_close(self):
        self.log_window_visible_var.set(False)
        self._destroy_log_window()

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select Folder to Scan")
        if folder:
            self.scan_path.set(folder)
            self.log(f"Scan path set to: {folder}", "info")

    def load_systems_from_db(self):
        self.log("Fetching system list from database...")
        try:
            conn = get_db_connection()
            self.supported_systems = [row['name'] for row in conn.execute("SELECT name FROM systems ORDER BY name").fetchall()]
            conn.close()
            self.log(f"Successfully fetched {len(self.supported_systems)} systems.", "success")
        except Exception as e:
            self.log(f"Error fetching system list: {e}", "error")
            messagebox.showerror("Database Error", f"Failed to load system list: {e}")

    def start_scan_thread(self):
        folder = self.scan_path.get()
        if not folder:
            messagebox.showwarning("Input Error", "Please select a folder to scan.")
            return
        self.log(f"--- Starting Scan of '{folder}' ---", "info")
        self.update_main_status(f"Scanning '{folder}'...", "info", duration_ms=0)
        self.scan_button.config(state=tk.DISABLED)
        threading.Thread(target=self._run_scan, args=(folder,), daemon=True).start()

    def _run_scan(self, scan_path):
        found_games = []
        try:
            for game in scan_directory(scan_path, self.log):
                found_games.append(game)
            self.log(f"--- Scan Complete: Found {len(found_games)} new potential games. ---", "success")
            self.update_main_status(f"Scan Complete: Found {len(found_games)} games.", "success")
            if found_games:
                self.master.after(0, lambda: self._open_scan_review_dialog(found_games))
            else:
                self.log("No new games found.", "info")
        except Exception as e:
            self.log(f"Error during scan: {e}", "error")
            self.update_main_status(f"Scan Failed: {e}", "error")
        finally:
            self.master.after(0, self.scan_button.config, {'state': tk.NORMAL})

    def _open_scan_review_dialog(self, scanned_games):
        self.log("Opening scan review dialog...", "info")
        dialog = ScanReviewDialog(self.master, self, scanned_games, self.supported_systems)
        self.master.wait_window(dialog)
        self.log("Scan review dialog closed.", "info")

    def copy_log_to_clipboard(self):
        try:
            self.master.clipboard_clear()
            content = self.output_text.get(1.0, tk.END) if self.output_text else "".join(f"{entry['message']}" for entry in self.log_buffer)
            self.master.clipboard_append(content)
            self.log("--- Log content copied to clipboard! ---", "success")
            self.update_main_status("Log copied to clipboard.", "success")
        except Exception as e:
            self.log(f"Failed to copy log: {e}", "error")
            self.update_main_status("Failed to copy log.", "error")
