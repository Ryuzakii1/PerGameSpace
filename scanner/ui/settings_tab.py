# scanner/ui/settings_tab.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os

# Import the necessary core functions for backup/restore
from ..core import backup_application_data, restore_application_data

def create_settings_tab(notebook, app):
    """Creates the UI for the main Settings tab."""
    settings_tab = ttk.Frame(notebook, padding="10")
    notebook.add(settings_tab, text="Settings")

    # --- Create a Canvas with a Scrollbar to make the content area scrollable ---
    # Get the current background color from the style to prevent the "white box" effect.
    bg_color = app.style.lookup("TFrame", "background")
    canvas = tk.Canvas(settings_tab, borderwidth=0, highlightthickness=0, background=bg_color)
    scrollbar = ttk.Scrollbar(settings_tab, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)

    # This binding updates the scrollregion for the VERTICAL scrollbar
    # when the content of the frame changes size.
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")
        )
    )

    # Place the scrollable frame inside the canvas and get its ID
    frame_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

    # This binding updates the width of the frame to match the canvas width
    # when the canvas itself is resized. This fixes the horizontal sizing issue.
    def on_canvas_resize(event):
        canvas.itemconfig(frame_id, width=event.width)

    canvas.bind("<Configure>", on_canvas_resize)

    canvas.configure(yscrollcommand=scrollbar.set)

    # Pack the canvas and scrollbar to fill the tab
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")


    # --- Application Settings (placed inside the scrollable_frame) ---
    app_settings_frame = ttk.LabelFrame(scrollable_frame, text="Application Settings", padding="15")
    app_settings_frame.pack(fill=tk.X, pady=10, padx=10, expand=True)

    dark_mode_checkbox = ttk.Checkbutton(
        app_settings_frame,
        text="Enable Dark Mode",
        variable=app.dark_mode_enabled,
        command=app.apply_dark_mode
    )
    dark_mode_checkbox.pack(anchor=tk.W, pady=5)

    hide_log_output_checkbox = ttk.Checkbutton(
        app_settings_frame,
        text="Hide Log Output Panel",
        variable=app.hide_log_output_var,
        command=app.toggle_log_output_visibility
    )
    hide_log_output_checkbox.pack(anchor=tk.W, pady=5)

    # --- IGDB API Settings (placed inside the scrollable_frame) ---
    igdb_frame = ttk.LabelFrame(scrollable_frame, text="IGDB API Settings", padding="15")
    igdb_frame.pack(fill=tk.X, pady=10, padx=10, expand=True)
    igdb_frame.columnconfigure(1, weight=1)

    ttk.Label(igdb_frame, text="Client ID:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
    igdb_id_entry = ttk.Entry(igdb_frame, textvariable=app.igdb_client_id)
    igdb_id_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

    ttk.Label(igdb_frame, text="Client Secret:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
    igdb_secret_entry = ttk.Entry(igdb_frame, textvariable=app.igdb_client_secret, show="*")
    igdb_secret_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

    ttk.Label(igdb_frame, text="Credentials are saved when the application is closed.", wraplength=400, justify=tk.LEFT).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(10,0))


    # --- Backup & Restore Section (placed inside the scrollable_frame) ---
    backup_frame = ttk.LabelFrame(scrollable_frame, text="Backup & Restore", padding="15")
    backup_frame.pack(fill=tk.X, pady=10, padx=10, expand=True)
    backup_frame.columnconfigure(1, weight=1)

    ttk.Label(backup_frame, text="Backup Location:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    
    app.backup_path_var = tk.StringVar(value=os.path.join(str(app.base_dir), "backup"))
    app.backup_entry = ttk.Entry(backup_frame, textvariable=app.backup_path_var)
    app.backup_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

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
            backup_application_data(backup_location, app.log, app.base_dir)
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
            restore_application_data(restore_location, app.log, app.base_dir)
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
