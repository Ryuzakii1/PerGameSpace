# scanner/emuman.py
# Manages the UI and logic for the Emulator Manager tab.

import tkinter as tk
from tkinter import ttk, messagebox
import threading

from .core import get_emulator_statuses, download_and_setup_emulator

def create_emulator_manager_tab(notebook, app):
    """Creates and populates the Emulator Manager tab."""
    manager_tab = ttk.Frame(notebook, padding="10")
    notebook.add(manager_tab, text="Emulator Manager")
    manager_tab.columnconfigure(0, weight=1)
    manager_tab.rowconfigure(0, weight=1)

    frame = ttk.LabelFrame(manager_tab, text="Recommended Emulators", padding="10")
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)

    # Store the treeview on the main app instance so it can be accessed
    app.emu_tree = ttk.Treeview(frame, columns=('Emulator', 'Systems', 'Status'), show='headings')
    app.emu_tree.heading('Emulator', text='Emulator')
    app.emu_tree.heading('Systems', text='Manages Systems')
    app.emu_tree.heading('Status', text='Status')
    app.emu_tree.column('Emulator', width=150, anchor='w')
    app.emu_tree.column('Systems', width=300, anchor='w')
    app.emu_tree.column('Status', width=150, anchor='center')
    app.emu_tree.grid(row=0, column=0, sticky="nsew")
    
    emu_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=app.emu_tree.yview)
    app.emu_tree.configure(yscrollcommand=emu_scrollbar.set)
    emu_scrollbar.grid(row=0, column=1, sticky="ns")

    buttons_frame = ttk.Frame(manager_tab)
    buttons_frame.grid(row=1, column=0, pady=(10,0), sticky="e")
    
    app.download_button = ttk.Button(buttons_frame, text="Download Selected", command=lambda: download_selected_emulator(app))
    app.download_button.pack(side=tk.LEFT, padx=5)
    
    app.refresh_emu_button = ttk.Button(buttons_frame, text="Refresh Status", command=lambda: refresh_emulator_statuses(app))
    app.refresh_emu_button.pack(side=tk.LEFT)

def refresh_emulator_statuses(app):
    """Clears and re-populates the emulator status list."""
    for i in app.emu_tree.get_children():
        app.emu_tree.delete(i)
    
    app.log( "Checking emulator statuses...")
    
    def do_refresh():
        try:
            statuses = get_emulator_statuses()
            app.master.after(0, lambda: populate_emu_tree(app, statuses))
        except Exception as e:
            app.log(f"Error checking emulator statuses: {e}", "error")

    threading.Thread(target=do_refresh, daemon=True).start()

def populate_emu_tree(app, statuses):
    for name, data in statuses.items():
        systems_str = ", ".join(data['systems'])
        app.emu_tree.insert('', 'end', iid=name, values=(name, systems_str, data['status']))
    app.log("Emulator status check complete.")

def download_selected_emulator(app):
    selected = app.emu_tree.focus()
    if not selected:
        messagebox.showwarning("No Selection", "Please select an emulator from the list to download.")
        return
    
    status = app.emu_tree.item(selected, "values")[2]
    if status == "Installed":
        messagebox.showinfo("Already Installed", f"{selected} appears to be installed already.")
        return

    app.download_button.config(state=tk.DISABLED)
    app.refresh_emu_button.config(state=tk.DISABLED)
    
    def progress_callback(emu_name, status_text):
        app.master.after(0, app.emu_tree.item, emu_name, {'values': (emu_name, app.emu_tree.item(emu_name, "values")[1], status_text)})

    threading.Thread(target=_run_download, args=(selected, app, progress_callback), daemon=True).start()

def _run_download(emu_name, app, progress_callback):
    download_and_setup_emulator(emu_name, progress_callback, lambda msg, tag=None: app.log(msg, tag))
    app.master.after(0, refresh_emulator_statuses, app)
    app.master.after(0, app.download_button.config, {'state': tk.NORMAL})
    app.master.after(0, app.refresh_emu_button.config, {'state': tk.NORMAL})
