# scanner/ui/settings_tab.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os # Make sure os is imported here for os.path.join

# Import the necessary core functions for backup/restore
from ..core import backup_application_data, restore_application_data

def create_settings_tab(notebook, app):
    """Creates the UI for the main Settings tab."""
    settings_tab = ttk.Frame(notebook, padding="10")
    notebook.add(settings_tab, text="Settings")

    # --- Application Settings ---
    app_settings_frame = ttk.LabelFrame(settings_tab, text="Application Settings", padding="15")
    app_settings_frame.pack(fill=tk.X, pady=10, padx=5)

    # Dark Mode Toggle
    # Note: A ttk.Checkbutton with a BooleanVar *is* already a toggle.
    # Clicking it automatically flips the variable's value.
    # The 'command' simply reacts to this new value.
    dark_mode_checkbox = ttk.Checkbutton(
        app_settings_frame,
        text="Enable Dark Mode", # Text remains clear
        variable=app.dark_mode_enabled,
        command=app.apply_dark_mode # Call the apply function
    )
    dark_mode_checkbox.pack(anchor=tk.W, pady=5)

    # Hide Log Output Toggle (Updated Label and Function Call)
    hide_log_output_checkbox = ttk.Checkbutton(
        app_settings_frame,
        text="Hide Log Output Toggle", # New, clearer label
        variable=app.hide_log_output_var, # Uses the renamed variable
        command=app.toggle_log_output_visibility # Calls the renamed function
    )
    hide_log_output_checkbox.pack(anchor=tk.W, pady=5)

    # --- Backup & Restore Section ---
    backup_frame = ttk.LabelFrame(settings_tab, text="Backup & Restore", padding="15")
    backup_frame.pack(fill=tk.X, pady=10, padx=5)

    ttk.Label(backup_frame, text="Backup Location:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    # Ensure app.base_dir is converted to a string for os.path.join if it's a Path object
    app.backup_path_var = tk.StringVar(value=os.path.join(str(app.base_dir), "backup"))
    app.backup_entry = ttk.Entry(backup_frame, textvariable=app.backup_path_var)
    app.backup_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
    backup_frame.columnconfigure(1, weight=1)

    btn_browse_backup = ttk.Button(backup_frame, text="Browse...", command=lambda: browse_backup_folder(app))
    btn_browse_backup.grid(row=0, column=2, padx=5, pady=5)

    btn_backup = ttk.Button(backup_frame, text="Backup Now", command=lambda: start_backup_thread(app))
    btn_backup.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)

    btn_restore = ttk.Button(backup_frame, text="Restore From Backup", command=lambda: start_restore_thread(app))
    btn_restore.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)

    # Store button references for disabling during operations
    app.btn_backup = btn_backup
    app.btn_restore = btn_restore
    app.btn_browse_backup = btn_browse_backup


# --- Helper functions for Backup/Restore UI operations ---

def _set_button_states(app, state):
    """Helper to set the state of backup/restore buttons."""
    app.master.after(0, lambda: app.btn_backup.config(state=state))
    app.master.after(0, lambda: app.btn_restore.config(state=state))
    app.master.after(0, lambda: app.btn_browse_backup.config(state=state))
    app.master.after(0, lambda: app.backup_entry.config(state=state))


def browse_backup_folder(app):
    """Allows user to select a backup location."""
    folder_selected = filedialog.askdirectory(title="Select Backup/Restore Location")
    if folder_selected:
        app.backup_path_var.set(folder_selected)


def start_backup_thread(app):
    """Initiates the backup process in a separate thread."""
    backup_location = app.backup_path_var.get()
    if not backup_location:
        messagebox.showwarning("Input Error", "Please select a backup location.")
        return

    _set_button_states(app, tk.DISABLED)
    app.log(f"Starting backup to '{backup_location}'...", "info")
    app.update_main_status(f"Backing up to '{backup_location}'...", "info", duration_ms=0)

    def do_backup():
        try:
            backup_application_data(backup_location, lambda msg, tag=None: app.log(msg, tag))
            app.master.after(0, messagebox.showinfo, "Backup Complete", f"Application data successfully backed up to:\n{backup_location}")
            app.log("Backup process completed successfully.", "success")
            app.update_main_status("Backup complete!", "success")
        except Exception as e:
            app.master.after(0, messagebox.showerror, "Backup Error", f"An error occurred during backup: {e}")
            app.log(f"Backup process failed: {e}", "error")
            app.update_main_status(f"Backup failed: {e}", "error")
        finally:
            _set_button_states(app, tk.NORMAL)

    threading.Thread(target=do_backup, daemon=True).start()


def start_restore_thread(app):
    """Initiates the restore process in a separate thread."""
    restore_location = app.backup_path_var.get()
    if not restore_location:
        messagebox.showwarning("Input Error", "Please select a restore location.")
        return

    confirm = messagebox.askyesno(
        "Confirm Restore",
        "Restoring data will OVERWRITE your current application data (games, emulators, settings).\n\n"
        "Are you sure you want to proceed?"
    )
    if not confirm:
        app.log("Restore operation cancelled by user.", "info")
        app.update_main_status("Restore cancelled.", "info")
        return

    _set_button_states(app, tk.DISABLED)
    app.log(f"Starting restore from '{restore_location}'...", "info")
    app.update_main_status(f"Restoring from '{restore_location}'...", "info", duration_ms=0)

    def do_restore():
        try:
            restore_application_data(restore_location, lambda msg, tag=None: app.log(msg, tag))
            app.master.after(0, messagebox.showinfo, "Restore Complete", "Application data successfully restored.\n\n"
                                                            "You may need to restart the application for all changes to take effect.")
            app.log("Restore process completed successfully. Please restart the app.", "success")
            app.update_main_status("Restore complete! Restart app.", "success")
        except Exception as e:
            app.master.after(0, messagebox.showerror, "Restore Error", f"An error occurred during restore: {e}")
            app.log(f"Restore process failed: {e}", "error")
            app.update_main_status(f"Restore failed: {e}", "error")
        finally:
            _set_button_states(app, tk.NORMAL)

    threading.Thread(target=do_restore, daemon=True).start()