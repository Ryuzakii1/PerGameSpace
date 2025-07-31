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
from .config import SETTINGS_FILE, EMULATORS, BASE_DIR

# --- Core Function Imports ---
# We use a try-except here so the application can report a clear error if core components are missing.
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
        fetch_igdb_metadata
    )
    core_import_successful = True
except ImportError as e:
    core_import_successful = False
    # This print is for command-line debugging if the GUI fails to launch.
    print(f"\n--- CRITICAL: Core Import FAILED: {e} ---")
    # We will show a messagebox later if the GUI manages to start.

# Import UI creation functions from separate files
from .utils.theme_utils import apply_widget_theme_recursive
from .ui.emuman_tab import create_emulator_manager_tab
from .ui.webapp_setup_tab import create_webapp_setup_tab
from .ui.scan_tab import create_scan_tab
from .ui.settings_tab import create_settings_tab
from .ui.scan_review_dialog import ScanReviewDialog


def log_message(widget, message, tag=None):
    """
    Appends a message to a ScrolledText widget with optional color-coding.
    This function is robust against being called before tags are created or after the widget is destroyed.
    """
    if not widget:
        print(f"LOG (widget not ready): [{tag or 'INFO'}] {message}")
        return

    try:
        # It's safe to configure tags every time. This creates them if they don't exist
        # and avoids the error from checking a non-existent tag.
        widget.tag_config("error", foreground="red")
        widget.tag_config("success", foreground="green")
        widget.tag_config("warning", foreground="orange")
        widget.tag_config("info", foreground="#007acc")

        widget.config(state=tk.NORMAL)
        
        if not message.endswith('\n'):
            message += '\n'

        # Use the tag only if it's one of the pre-defined ones.
        if tag in ("error", "success", "warning", "info"):
            widget.insert(tk.END, message, (tag,))
        else:
            widget.insert(tk.END, message)

        widget.see(tk.END)  # Scroll to the end
        widget.config(state=tk.DISABLED)
    except tk.TclError as e:
        # This can happen if the widget is destroyed while a log is pending via .after()
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
            # Using a theme that is more likely to exist on all platforms
            self.style.theme_use('clam')
        except tk.TclError:
            self.style.theme_use('default') # Fallback
        master.geometry("850x750")
        master.minsize(700, 600)

        # Critical check for core functions
        if not core_import_successful:
            messagebox.showerror(
                "Fatal Error",
                "A critical component of the application failed to load. "
                "The program cannot continue. Please check the console for import errors."
            )
            master.destroy()
            return

        self.settings = self.load_settings()

        # --- Variable Declarations ---
        self.scan_path = tk.StringVar()
        self.import_mode = tk.StringVar(value=self.settings.get("import_mode", "copy"))
        self.dark_mode_enabled = tk.BooleanVar(value=self.settings.get("dark_mode", False))
        self.hide_log_output_var = tk.BooleanVar(value=self.settings.get("hide_log_output", False))
        self.supported_systems = []
        self.last_selected_tab_text = None

        # Store BASE_DIR and EMULATORS config on the app object for easy access by other modules
        self.base_dir = BASE_DIR
        self.EMULATORS = EMULATORS

        # --- GUI Layout ---
        main_frame = ttk.Frame(master, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(0, weight=1) # Notebook row
        main_frame.rowconfigure(1, weight=0) # Status label row
        main_frame.rowconfigure(2, weight=1, minsize=150) # Log frame row
        main_frame.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        self.status_label = ttk.Label(main_frame, text="Ready.", anchor="w", font=('TkDefaultFont', 9))
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(5,5), padx=5)

        # Log frame creation
        self.log_frame = ttk.LabelFrame(main_frame, text="Log Output", padding="10")
        self.log_frame.grid(row=2, column=0, sticky="nsew")
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(0, weight=1)

        self.output_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, font=('Consolas', 9), state=tk.DISABLED)
        self.output_text.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self.copy_log_button = ttk.Button(self.log_frame, text="Copy Log", command=self.copy_log_to_clipboard)
        self.copy_log_button.pack(pady=(5, 0), anchor="e")

        # Call UI creation functions to build the tabs
        create_scan_tab(self.notebook, self)
        create_webapp_setup_tab(self.notebook, self)
        create_emulator_manager_tab(self.notebook, self)
        create_settings_tab(self.notebook, self)

        # --- Final Setup ---
        master.after(100, self.load_systems_from_db)
        self.apply_dark_mode()
        self.toggle_log_output_visibility() # Set initial state
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

    def on_closing(self):
        """Handle window close event."""
        self.save_settings()
        self.master.destroy()

    def load_settings(self):
        """Load GUI settings from a JSON file."""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def save_settings(self):
        """Save GUI settings to a JSON file."""
        settings_data = {
            "dark_mode": self.dark_mode_enabled.get(),
            "hide_log_output": self.hide_log_output_var.get(),
            "import_mode": self.import_mode.get(),
        }
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings_data, f, indent=4)

    def on_tab_change(self, event):
        """Refresh data when switching to certain tabs."""
        selected_tab_index = self.notebook.index(self.notebook.select())
        current_tab_text = self.notebook.tab(selected_tab_index, "text")

        # Refresh emulator statuses only if the tab has changed to "Emulator Manager"
        if current_tab_text == "Emulator Manager" and current_tab_text != self.last_selected_tab_text:
            # Import locally to avoid circular dependency issues at startup
            from .ui.emuman_tab import refresh_emulator_statuses
            refresh_emulator_statuses(self, force_refresh=True)

        self.last_selected_tab_text = current_tab_text

    def log(self, message, tag=None):
        """Public log method for other modules to use."""
        # Ensure this runs on the main GUI thread
        self.master.after(0, log_message, self.output_text, message, tag)

    def update_main_status(self, message, status_type="info", duration_ms=5000):
        """Updates the main status label with a message and color."""
        color_map = {
            "info": "#007acc",
            "success": "green",
            "error": "red",
            "warning": "orange",
        }
        status_fg = color_map.get(status_type, self.style.lookup('TLabel', 'foreground'))

        self.master.after(0, lambda: self.status_label.config(text=message, foreground=status_fg))

        # If duration is positive, schedule the label to be cleared.
        if duration_ms > 0:
            self.master.after(duration_ms, lambda: self.status_label.config(text=""))

    def apply_dark_mode(self):
        """Applies a dark or light theme to the entire application."""
        is_dark = self.dark_mode_enabled.get()
        self.log(f"Applying {'dark' if is_dark else 'light'} theme.", "info")

        # Define color palettes
        if is_dark:
            bg, fg, entry_bg, btn_bg, active_bg, sel_bg, sel_fg = \
            "#2e2e2e", "#d0d0d0", "#3c3c3c", "#555555", "#666666", "#005a9e", "#ffffff"
        else:
            bg, fg, entry_bg, btn_bg, active_bg, sel_bg, sel_fg = \
            "#f0f0f0", "#000000", "#ffffff", "#e1e1e1", "#c0c0c0", "#0078d7", "#ffffff"

        # Apply styles to all ttk widgets
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

        # Treeview specific styling
        self.style.configure('Treeview', background=entry_bg, fieldbackground=entry_bg, foreground=fg, rowheight=25)
        self.style.map('Treeview', background=[('selected', sel_bg)], foreground=[('selected', sel_fg)])
        self.style.configure('Treeview.Heading', background=btn_bg, foreground=fg, font=('TkDefaultFont', 9, 'bold'), relief="raised")
        self.style.map('Treeview.Heading', background=[('active', active_bg)])

        # Apply to non-ttk widgets
        self.master.config(bg=bg)
        self.output_text.config(bg=entry_bg, fg=fg, insertbackground=fg)

        # Recursively apply theme to all standard tk widgets
        apply_widget_theme_recursive(self.master, bg, fg, entry_bg)
        self.master.update_idletasks()

    def toggle_log_output_visibility(self):
        """Shows or hides the log output frame."""
        if self.hide_log_output_var.get():
            if self.log_frame.winfo_ismapped():
                # Store grid info before hiding
                self._log_frame_grid_info = self.log_frame.grid_info()
                self.log_frame.grid_remove()
                self.log("Log output hidden.", "info")
        else:
            if not self.log_frame.winfo_ismapped():
                # Restore using stored info or default
                info = getattr(self, '_log_frame_grid_info', {'row': 2, 'column': 0, 'sticky': 'nsew'})
                self.log_frame.grid(**info)
                self.log("Log output shown.", "info")

    def browse_folder(self):
        """Open a dialog to select a folder for scanning."""
        folder = filedialog.askdirectory(title="Select Folder to Scan")
        if folder:
            self.scan_path.set(folder)
            self.log(f"Scan path set to: {folder}", "info")

    def load_systems_from_db(self):
        """Loads the list of supported game systems from the database."""
        self.log("Connecting to database to fetch system list...")
        try:
            conn = get_db_connection()
            systems = [row['name'] for row in conn.execute("SELECT name FROM systems ORDER BY name").fetchall()]
            conn.close()
            self.supported_systems = systems
            self.log(f"Successfully fetched {len(systems)} systems from DB.", "success")
        except Exception as e:
            self.log(f"Error fetching system list: {e}", "error")
            self.update_main_status(f"Error: Failed to load system list. {e}", "error")
            messagebox.showerror("Database Error", f"Failed to load system list from database: {e}")

    def start_scan_thread(self):
        """Starts the game scanning process in a background thread."""
        folder = self.scan_path.get()
        if not folder:
            messagebox.showwarning("Input Error", "Please select a folder to scan.")
            return

        self.log(f"--- Starting Scan of '{folder}' ---", "info")
        self.update_main_status(f"Scanning '{folder}'...", "info", duration_ms=0)
        self.scan_button.config(state=tk.DISABLED)

        threading.Thread(target=self._run_scan, args=(folder,), daemon=True).start()

    def _run_scan(self, scan_path):
        """The actual scanning logic that runs in the thread."""
        found_games = []
        try:
            for game in scan_directory(scan_path, self.log):
                found_games.append(game)
            self.log(f"--- Scan Complete: Found {len(found_games)} new potential games. ---", "success")
            self.update_main_status(f"Scan Complete: Found {len(found_games)} games.", "success")

            if found_games:
                # Open the review dialog on the main thread
                self.master.after(0, lambda: self._open_scan_review_dialog(found_games))
            else:
                self.log("No new potential games found in this scan.", "info")
                self.update_main_status("Scan complete: No new games found.", "info")

        except Exception as e:
            self.log(f"Error during scan: {e}", "error")
            self.update_main_status(f"Scan Failed: {e}", "error")
        finally:
            # Re-enable the scan button on the main thread
            self.master.after(0, self.scan_button.config, {'state': tk.NORMAL})

    def _open_scan_review_dialog(self, scanned_games):
        """Opens the modal dialog for reviewing and editing scanned games."""
        self.log("Opening scan review dialog...", "info")
        # The dialog will be modal, so the code here will wait until it's closed.
        dialog = ScanReviewDialog(self.master, self, scanned_games, self.supported_systems)
        self.master.wait_window(dialog)
        self.log("Scan review dialog closed.", "info")

    def copy_log_to_clipboard(self):
        """Copies the content of the log to the clipboard."""
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(self.output_text.get(1.0, tk.END))
            self.log("--- Log content copied to clipboard! ---", "success")
            self.update_main_status("Log copied to clipboard.", "success")
        except Exception as e:
            self.log(f"Failed to copy log to clipboard: {e}", "error")
            self.update_main_status("Failed to copy log.", "error")

