# scanner/ui/scan_tab.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

def create_scan_tab(notebook, app):
    scan_frame = ttk.Frame(notebook, padding="10")
    notebook.add(scan_frame, text="Scan Collection")

    # Path selection
    path_frame = ttk.LabelFrame(scan_frame, text="1. Select Scan Folder", padding="10")
    path_frame.pack(fill=tk.X, pady=10, padx=5)

    path_entry = ttk.Entry(path_frame, textvariable=app.scan_path)
    path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

    browse_button = ttk.Button(path_frame, text="Browse...", command=app.browse_folder)
    browse_button.pack(side=tk.RIGHT)

    # Scan Button
    app.scan_button = ttk.Button(scan_frame, text="2. Start Scan", command=app.start_scan_thread)
    app.scan_button.pack(pady=10)

    # All Treeview-related code (including app.tree and its binds) has been removed from here
    # and moved to the scan_review_dialog.py.