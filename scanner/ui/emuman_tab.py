# scanner/ui/emuman_tab.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading
import os

# Import from core - FIX: Removed get_db_connection as core functions manage their own connections
from ..core import get_emulator_statuses, download_and_setup_emulator, save_emulator_path_to_db, delete_emulator_from_db

def create_emulator_manager_tab(notebook, app):
    emu_man_frame = ttk.Frame(notebook, padding="10")
    notebook.add(emu_man_frame, text="Emulator Manager")

    # Treeview for emulators
    columns = ("Emulator Name", "Supported Systems", "Status")
    app.emu_tree = ttk.Treeview(emu_man_frame, columns=columns, show="headings")

    for col in columns:
        app.emu_tree.heading(col, text=col, anchor=tk.W)
        app.emu_tree.column(col, width=150, stretch=tk.YES)

    app.emu_tree.pack(fill=tk.BOTH, expand=True, pady=10)

    # Context Menu for Treeview
    app.emu_tree_context_menu = tk.Menu(app.master, tearoff=0)
    app.emu_tree_context_menu.add_command(label="Associate Systems", command=lambda: open_associate_dialog(app))
    app.emu_tree_context_menu.add_command(label="Update Path", command=lambda: update_emulator_path(app))
    app.emu_tree_context_menu.add_command(label="Delete Emulator", command=lambda: delete_emulator_entry(app))
    app.emu_tree.bind("<Button-3>", lambda event: app.emu_tree_context_menu.post(event.x_root, event.y_root)) # Right-click

    # Refresh Button
    refresh_button = ttk.Button(emu_man_frame, text="Refresh Status", command=lambda: refresh_emulator_statuses(app, force_refresh=True))
    refresh_button.pack(pady=5, side=tk.RIGHT)

    # Download Emulator Button
    download_button = ttk.Button(emu_man_frame, text="Download Emulator", command=lambda: start_download_emulator_thread(app))
    download_button.pack(pady=5, side=tk.LEFT)

    # Store button references if needed (e.g., to disable during operations)
    app.emu_refresh_button = refresh_button
    app.emu_download_button = download_button


def refresh_emulator_statuses(app, force_refresh=False):
    """Refreshes the statuses of all configured emulators."""
    app.log("Refreshing emulator statuses...", "info")
    app.update_main_status("Refreshing emulator statuses...", "info", duration_ms=0)
    # Disable buttons during refresh
    if hasattr(app, 'emu_refresh_button'): app.emu_refresh_button.config(state=tk.DISABLED)
    if hasattr(app, 'emu_download_button'): app.emu_download_button.config(state=tk.DISABLED)

    threading.Thread(target=_do_refresh_emulator_statuses, args=(app, force_refresh), daemon=True).start()

def _do_refresh_emulator_statuses(app, force_refresh):
    try:
        # FIX: Call get_emulator_statuses directly, without passing a connection
        statuses = get_emulator_statuses(force_refresh=force_refresh)
        app.master.after(0, lambda: populate_emu_tree(app, statuses)) # Populate on main thread
        app.update_main_status("Emulator statuses refreshed.", "success")
    except Exception as e:
        app.log(f"Error refreshing emulator statuses: {e}", "error")
        app.update_main_status(f"Error refreshing emulators: {e}", "error")
        # FIX: Capture 'e' with a default argument in the lambda
        app.master.after(0, lambda error_message=str(e): messagebox.showerror("Error", f"Failed to refresh emulator statuses: {error_message}"))
    finally:
        # Re-enable buttons
        app.master.after(0, lambda: app.emu_refresh_button.config(state=tk.NORMAL) if hasattr(app, 'emu_refresh_button') else None)
        app.master.after(0, lambda: app.emu_download_button.config(state=tk.NORMAL) if hasattr(app, 'emu_download_button') else None)


def populate_emu_tree(app, emulator_statuses):
    """
    Populates the emulator Treeview with current statuses.
    This function is called by the app.master.after to run in the main thread.
    """
    # CRITICAL FIX: CLEAR EXISTING ITEMS BEFORE INSERTING
    for item in app.emu_tree.get_children():
        app.emu_tree.delete(item)

    if not emulator_statuses:
        app.log("No emulators found in the database.", "info")
        app.update_main_status("No emulators configured.", "info")
        return

    for name, data in emulator_statuses.items():
        systems_str = ", ".join(data['systems']) if data['systems'] else "N/A"
        app.emu_tree.insert('', 'end', iid=name, values=(name, systems_str, data['status']))

    app.log(f"Emulator tree populated with {len(emulator_statuses)} entries.", "info")
    app.update_main_status(f"Emulator tree updated.", "info")


# --- Emulator Management Actions ---

def open_associate_dialog(app):
    selected_item_id = app.emu_tree.focus()
    if not selected_item_id:
        messagebox.showwarning("Selection Error", "Please select an emulator to associate systems with.")
        return

    emulator_name = app.emu_tree.item(selected_item_id, 'values')[0]
    app.log(f"Opening association dialog for {emulator_name} (Not implemented yet).", "info")
    app.update_main_status(f"Associate dialog for {emulator_name} not implemented.", "info")


def update_emulator_path(app):
    selected_item_id = app.emu_tree.focus()
    if not selected_item_id:
        messagebox.showwarning("Selection Error", "Please select an emulator to update its path.")
        return

    emulator_name = app.emu_tree.item(selected_item_id, 'values')[0]
    new_path = filedialog.askopenfilename(title=f"Select executable for {emulator_name}",
                                         filetypes=[("Executables", "*.exe"), ("All files", "*.*")])
    if new_path:
        app.log(f"Updating path for {emulator_name} to {new_path}", "info")
        app.update_main_status(f"Updating path for {emulator_name}...", "info", duration_ms=0)
        threading.Thread(target=_do_update_emulator_path, args=(app, emulator_name, new_path), daemon=True).start()
    else:
        app.log(f"Path update for {emulator_name} cancelled.", "info")
        app.update_main_status(f"Path update cancelled.", "info")

def _do_update_emulator_path(app, emulator_name, new_path):
    try:
        # FIX: Call save_emulator_path_to_db directly, without passing a connection
        save_emulator_path_to_db(emulator_name, new_path, 'local', app.log)
        app.log(f"Path for {emulator_name} updated successfully.", "success")
        app.update_main_status(f"Path for {emulator_name} updated.", "success")
        app.master.after(0, lambda: refresh_emulator_statuses(app, force_refresh=True))
    except Exception as e:
        app.log(f"Error updating path for {emulator_name}: {e}", "error")
        app.update_main_status(f"Error updating path for {emulator_name}: {e}", "error")
        # FIX: Capture 'e' with a default argument in the lambda
        app.master.after(0, lambda error_message=str(e): messagebox.showerror("Error", f"Failed to update path: {error_message}"))


def delete_emulator_entry(app):
    selected_item_id = app.emu_tree.focus()
    if not selected_item_id:
        messagebox.showwarning("Selection Error", "Please select an emulator to delete.")
        return

    emulator_name = app.emu_tree.item(selected_item_id, 'values')[0]
    confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the entry for {emulator_name}?\n"
                                                  "This will NOT delete files from your system, only the database entry.")
    if confirm:
        app.log(f"Deleting emulator entry for {emulator_name}...", "info")
        app.update_main_status(f"Deleting {emulator_name}...", "info", duration_ms=0)
        # FIX: Call the new core function delete_emulator_from_db
        threading.Thread(target=_do_delete_emulator_entry, args=(app, emulator_name, app.log), daemon=True).start()
    else:
        app.log(f"Deletion of {emulator_name} cancelled.", "info")
        app.update_main_status(f"Deletion cancelled.", "info")

def _do_delete_emulator_entry(app, emulator_name, log_callback):
    try:
        # FIX: Call core function, no direct SQL or connection management here
        delete_emulator_from_db(emulator_name, log_callback)
        app.log(f"Emulator entry for {emulator_name} deleted successfully.", "success")
        app.update_main_status(f"Deleted {emulator_name}.", "success")
        app.master.after(0, lambda: refresh_emulator_statuses(app, force_refresh=True))
    except Exception as e:
        app.log(f"Error deleting emulator entry for {emulator_name}: {e}", "error")
        app.update_main_status(f"Error deleting {emulator_name}: {e}", "error")
        # FIX: Capture 'e' with a default argument in the lambda
        app.master.after(0, lambda error_message=str(e): messagebox.showerror("Error", f"Failed to delete emulator: {error_message}"))


def start_download_emulator_thread(app):
    """Opens a dialog to select an emulator system and starts download."""
    # Assuming EMULATORS is available via app.EMULATORS (from config.py)
    downloadable_emulators = [e['name'] for e in app.EMULATORS]

    if not downloadable_emulators:
        messagebox.showinfo("No Emulators", "No emulators configured for direct download.")
        return

    selected_emu_name = simpledialog.askstring("Download Emulator",
                                               "Enter name of emulator to download (e.g., RetroArch):",
                                               parent=app.master)
    if not selected_emu_name:
        app.log("Emulator download cancelled.", "info")
        return

    # Find the full emulator data from EMULATORS based on selected_emu_name
    emu_config = next((emu for emu in app.EMULATORS if emu['name'].lower() == selected_emu_name.lower()), None)

    if not emu_config:
        messagebox.showwarning("Emulator Not Found", f"Emulator '{selected_emu_name}' not found in configurable list.")
        app.log(f"Emulator '{selected_emu_name}' not found for download.", "warning")
        return

    if not messagebox.askyesno("Confirm Download", f"Do you want to download and set up {emu_config['name']}?"):
        app.log(f"Download of {emu_config['name']} cancelled.", "info")
        return

    app.log(f"Starting download of {emu_config['name']}...", "info")
    app.update_main_status(f"Downloading {emu_config['name']}...", "info", duration_ms=0)

    threading.Thread(target=_do_download_emulator, args=(app, emu_config), daemon=True).start()

def _do_download_emulator(app, emu_config):
    try:
        download_and_setup_emulator(emu_config, lambda msg: app.log(msg), app.log) # Pass log_callback to progress_callback, then log_callback as actual log_callback
        app.log(f"Successfully downloaded and set up {emu_config['name']}.", "success")
        app.update_main_status(f"{emu_config['name']} setup complete!", "success")
        app.master.after(0, lambda: refresh_emulator_statuses(app, force_refresh=True))
        app.master.after(0, lambda: messagebox.showinfo("Download Complete", f"{emu_config['name']} setup successfully!"))
    except Exception as e:
        app.log(f"Failed to download/setup {emu_config['name']}: {e}", "error")
        app.update_main_status(f"{emu_config['name']} setup failed: {e}", "error")
        # FIX: Capture 'e' with a default argument in the lambda
        app.master.after(0, lambda error_message=str(e): messagebox.showerror("Download Error", f"Failed to download/setup {emu_config['name']}:\n{error_message}"))