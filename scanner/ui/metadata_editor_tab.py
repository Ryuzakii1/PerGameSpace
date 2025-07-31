# scanner/ui/metadata_editor_tab.py

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox

# We'll need access to core functions for import and possibly other DB operations
from ..core import import_games # We'll modify import_games in core to accept new metadata

def create_metadata_editor_tab(notebook, app, scanned_games_data):
    """
    Creates the UI for the Scan Review & Metadata Editor tab.
    scanned_games_data: A list of dictionaries, each representing a scanned game.
    """
    metadata_editor_frame = ttk.Frame(notebook, padding="10")
    notebook.add(metadata_editor_frame, text="Scan Review & Metadata")

    # Store the scanned_games_data on the app object or within this function's scope
    app.scanned_games_to_edit = scanned_games_data # Store on app for access by import logic

    # Configure grid layout for the metadata editor frame
    metadata_editor_frame.columnconfigure(0, weight=3) # Treeview column
    metadata_editor_frame.columnconfigure(1, weight=1) # Detail panel column
    metadata_editor_frame.rowconfigure(0, weight=1) # Treeview/Detail row
    metadata_editor_frame.rowconfigure(1, weight=0) # Controls row (buttons at bottom)

    # --- Left Pane: Scanned Games Treeview (with simulated inline editing) ---
    # Define all columns, including new metadata fields
    game_columns = ("Title", "System", "Genre", "Year", "Developer", "Publisher", "Status")
    app.metadata_tree = ttk.Treeview(metadata_editor_frame, columns=game_columns, show="headings")

    # Setup column headings
    app.metadata_tree.heading("Title", text="Title", anchor=tk.W)
    app.metadata_tree.heading("System", text="System", anchor=tk.W)
    app.metadata_tree.heading("Genre", text="Genre", anchor=tk.W)
    app.metadata_tree.heading("Year", text="Year", anchor=tk.W)
    app.metadata_tree.heading("Developer", text="Developer", anchor=tk.W)
    app.metadata_tree.heading("Publisher", text="Publisher", anchor=tk.W)
    app.metadata_tree.heading("Status", text="Play Status", anchor=tk.W) # Play Status for 'play_status'

    # Setup column widths (can be adjusted)
    app.metadata_tree.column("Title", width=180, stretch=tk.YES)
    app.metadata_tree.column("System", width=80, stretch=tk.YES)
    app.metadata_tree.column("Genre", width=80)
    app.metadata_tree.column("Year", width=60)
    app.metadata_tree.column("Developer", width=100)
    app.metadata_tree.column("Publisher", width=100)
    app.metadata_tree.column("Status", width=80)

    app.metadata_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

    # Populate the Treeview with scanned games
    _populate_metadata_tree(app, scanned_games_data)

    # --- Right Pane: Detail Editor (for Description/Notes) ---
    detail_frame = ttk.LabelFrame(metadata_editor_frame, text="Selected Game Details", padding="10")
    detail_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
    detail_frame.columnconfigure(0, weight=1)
    detail_frame.rowconfigure(2, weight=1) # Description text box should expand

    # Title label for detail panel
    app.detail_title_label = ttk.Label(detail_frame, text="Title: (Select a game)", font=('TkDefaultFont', 10, 'bold'))
    app.detail_title_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))

    # Current game's file path (read-only)
    ttk.Label(detail_frame, text="File Path:").grid(row=1, column=0, sticky="w", pady=(5,0))
    app.detail_filepath_label = ttk.Label(detail_frame, text="", wraplength=200, anchor=tk.W)
    app.detail_filepath_label.grid(row=1, column=0, sticky="ew", padx=(0,0))


    ttk.Label(detail_frame, text="Description/Notes:").grid(row=2, column=0, sticky="w", pady=(5,0))
    app.detail_description_text = scrolledtext.ScrolledText(detail_frame, wrap=tk.WORD, height=10, font=('Consolas', 9))
    app.detail_description_text.grid(row=3, column=0, sticky="nsew", pady=(0, 5))

    # Bind selection and double-click for inline editing
    app.metadata_tree.bind("<<TreeviewSelect>>", lambda event: _on_metadata_tree_select(app))
    app.metadata_tree.bind("<Double-1>", lambda event: _start_inline_edit(app, event))


    # --- Bottom Controls ---
    controls_frame = ttk.Frame(metadata_editor_frame)
    controls_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    controls_frame.columnconfigure(0, weight=1) # Stretch the first column for bulk controls

    # Import and Discard Buttons
    app.import_metadata_button = ttk.Button(controls_frame, text="Import Selected Games", command=lambda: _import_selected_games_with_metadata(app, notebook))
    app.import_metadata_button.pack(side=tk.RIGHT, padx=5)

    app.discard_scan_button = ttk.Button(controls_frame, text="Discard Scan", command=lambda: _discard_scan(app, notebook))
    app.discard_scan_button.pack(side=tk.RIGHT, padx=5)

    # Bulk Edit Controls (Example: Genre, Status)
    bulk_edit_frame = ttk.Frame(controls_frame)
    bulk_edit_frame.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    bulk_edit_frame.columnconfigure(1, weight=1) # Allow entry to expand

    ttk.Label(bulk_edit_frame, text="Bulk Genre:").grid(row=0, column=0, sticky="w", padx=(0, 5))
    app.bulk_genre_var = tk.StringVar()
    app.bulk_genre_entry = ttk.Entry(bulk_edit_frame, textvariable=app.bulk_genre_var, width=15)
    app.bulk_genre_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
    ttk.Button(bulk_edit_frame, text="Apply", command=lambda: _apply_bulk_edit(app, "genre")).grid(row=0, column=2)

    ttk.Label(bulk_edit_frame, text="Bulk Status:").grid(row=1, column=0, sticky="w", padx=(0, 5))
    play_status_options = ['Not Played', 'Playing', 'Completed', 'Backlog', 'Abandoned']
    app.bulk_play_status_var = tk.StringVar(value='Not Played')
    app.bulk_play_status_menu = ttk.OptionMenu(bulk_edit_frame, app.bulk_play_status_var, *([app.bulk_play_status_var.get()] + play_status_options))
    app.bulk_play_status_menu.grid(row=1, column=1, sticky="ew", padx=(0, 10))
    ttk.Button(bulk_edit_frame, text="Apply", command=lambda: _apply_bulk_edit(app, "play_status")).grid(row=1, column=2)


# --- Helper functions (defined within this file, not globally) ---

def _populate_metadata_tree(app, games_data):
    # Clear existing items
    for item in app.metadata_tree.get_children():
        app.metadata_tree.delete(item)

    # Store games data in a dictionary for easy lookup by iid (Treeview ID)
    # The iid will be the game's index in the original list or a unique identifier.
    app.metadata_tree_data = {} # To store the actual game dicts for editing

    for i, game in enumerate(games_data):
        iid = f"game_{i}"
        app.metadata_tree_data[iid] = game # Store the full game dict

        # Populate treeview row
        app.metadata_tree.insert('', 'end', iid=iid, values=(
            game.get('title', ''),
            game.get('system', ''),
            game.get('genre', ''),       # New metadata fields
            game.get('release_year', ''),
            game.get('developer', ''),
            game.get('publisher', ''),
            game.get('play_status', 'Not Played')
        ))
    app.log(f"Metadata editor populated with {len(games_data)} games.", "info")


def _on_metadata_tree_select(app):
    selected_iid = app.metadata_tree.focus()
    if selected_iid and selected_iid in app.metadata_tree_data:
        game = app.metadata_tree_data[selected_iid]
        app.detail_title_label.config(text=f"Title: {game.get('title', '')} ({game.get('system', '')})")
        app.detail_filepath_label.config(text=game.get('filepath', '')) # Display filepath
        app.detail_description_text.delete(1.0, tk.END)
        app.detail_description_text.insert(tk.END, game.get('description', ''))
        # Store current selected item and update description on focus out
        app._current_selected_iid = selected_iid # Store for _on_description_edit_finish
        app.detail_description_text.bind("<FocusOut>", lambda event: _on_description_edit_finish(app)) # Bind here
    else:
        app.detail_title_label.config(text="Title: (Select a game)")
        app.detail_filepath_label.config(text="")
        app.detail_description_text.delete(1.0, tk.END)
        app._current_selected_iid = None


def _on_description_edit_finish(app, event=None):
    if app._current_selected_iid and app._current_selected_iid in app.metadata_tree_data:
        game = app.metadata_tree_data[app._current_selected_iid]
        new_description = app.detail_description_text.get(1.0, tk.END).strip()
        if new_description != game.get('description', ''):
            game['description'] = new_description
            app.log(f"Description updated for {game.get('title')}", "info")


def _start_inline_edit(app, event):
    # Get item and column that was double-clicked
    region = app.metadata_tree.identify("region", event.x, event.y)
    if region != "cell": return # Only allow editing on cells

    column = app.metadata_tree.identify_column(event.x)
    column_index = int(column.replace('#', '')) - 1 # Column index (0-based)
    item_iid = app.metadata_tree.identify_row(event.y)

    if not item_iid: return

    # Mapping Treeview column index to metadata key
    # (Title and System are index 0, 1; not typically editable inline via this method)
    metadata_keys_map = {
        2: "genre",
        3: "release_year",
        4: "developer",
        5: "publisher",
        6: "play_status"
    }

    metadata_key = metadata_keys_map.get(column_index)
    if not metadata_key: return # Not an editable column

    game_data_for_item = app.metadata_tree_data[item_iid]
    current_value = str(game_data_for_item.get(metadata_key, '')) # Get current value from data store

    # Create a temporary entry widget for editing
    x, y, width, height = app.metadata_tree.bbox(item_iid, column)
    if x is None or x == '': return # Item not visible or invalid position

    entry_editor = ttk.Entry(app.metadata_tree)
    entry_editor.place(x=x, y=y, width=width, height=height)
    entry_editor.insert(0, current_value)
    entry_editor.focus_set()

    # Callback when editing finishes
    def _on_edit_finish(event_obj=None):
        new_value = entry_editor.get().strip()
        # Update underlying data
        game_data = app.metadata_tree_data[item_iid]
        
        # Special handling for Play Status (use OptionMenu if desired)
        if metadata_key == 'play_status':
            play_status_options = ['Not Played', 'Playing', 'Completed', 'Backlog', 'Abandoned']
            if new_value not in play_status_options:
                # Optionally, open an OptionMenu/Combobox here instead of entry for status
                messagebox.showwarning("Invalid Status", f"'{new_value}' is not a valid status. Please use one of: {', '.join(play_status_options)}")
                new_value = game_data.get(metadata_key, 'Not Played') # Revert or keep old value
        
        # Basic type conversion for year
        if metadata_key == 'release_year':
            try:
                new_value = int(new_value)
            except ValueError:
                if new_value: # If user entered something but it's not a number
                    messagebox.showwarning("Invalid Year", f"'{new_value}' is not a valid year. Must be a number.")
                    new_value = game_data.get(metadata_key, None) # Revert to previous valid year or None
                else: # Empty value
                    new_value = None
        
        # Update underlying data dict
        if game_data.get(metadata_key) != new_value: # Only log if value actually changed
            game_data[metadata_key] = new_value
            app.log(f"Updated '{metadata_key}' for '{game_data.get('title')}' to '{new_value}'", "info")

        # Update Treeview display
        values = list(app.metadata_tree.item(item_iid, 'values'))
        values[column_index] = new_value
        app.metadata_tree.item(item_iid, values=values)

        entry_editor.destroy()

    entry_editor.bind("<Return>", _on_edit_finish) # On Enter key
    entry_editor.bind("<FocusOut>", _on_edit_finish) # On losing focus (important!)


def _apply_bulk_edit(app, field_name):
    selected_iids = app.metadata_tree.selection()
    if not selected_iids:
        messagebox.showwarning("No Selection", "Please select games to apply bulk edit to.")
        return

    value_to_apply = None
    if field_name == "genre":
        value_to_apply = app.bulk_genre_var.get().strip()
    elif field_name == "play_status":
        value_to_apply = app.bulk_play_status_var.get()
    else:
        return # Unknown field_name

    if not value_to_apply:
        messagebox.showwarning("Empty Value", "Please enter/select a value for the bulk edit.")
        return

    # Basic validation for play_status if needed
    if field_name == "play_status":
        play_status_options = ['Not Played', 'Playing', 'Completed', 'Backlog', 'Abandoned']
        if value_to_apply not in play_status_options:
            messagebox.showwarning("Invalid Status", f"'{value_to_apply}' is not a valid status. Please use one of: {', '.join(play_status_options)}")
            return

    updated_count = 0
    for iid in selected_iids:
        game_data = app.metadata_tree_data[iid]
        if game_data.get(field_name) != value_to_apply: # Only update if changed
            game_data[field_name] = value_to_apply # Update underlying data
            updated_count += 1

            # Update Treeview display
            current_values = list(app.metadata_tree.item(iid, 'values'))
            # Map field_name back to column index
            metadata_keys_order = ["Title", "System", "genre", "release_year", "developer", "publisher", "play_status"]
            col_index = metadata_keys_order.index(field_name)
            current_values[col_index] = value_to_apply
            app.metadata_tree.item(iid, values=current_values)

    if updated_count > 0:
        app.log(f"Bulk applied '{value_to_apply}' to '{field_name}' for {updated_count} games.", "info")
    else:
        app.log(f"No changes made during bulk edit for '{field_name}'.", "info")


def _import_selected_games_with_metadata(app, notebook):
    from ..core import import_games # Import core function here

    selected_iids = app.metadata_tree.selection()
    if not selected_iids:
        messagebox.showwarning("No Selection", "Please select games to import.")
        return

    games_to_import_with_metadata = []
    for iid in selected_iids:
        # Get the latest data for each selected game
        games_to_import_with_metadata.append(app.metadata_tree_data[iid])

    if not games_to_import_with_metadata: # Should not happen if selected_iids is not empty, but defensive
        app.log("No valid games selected for import.", "warning")
        app.update_main_status("No games to import.", "warning")
        return

    app.import_metadata_button.config(state=tk.DISABLED) # Disable button during import
    app.log(f"\n--- Importing {len(games_to_import_with_metadata)} games with metadata... ---", "info")
    app.update_main_status(f"Importing {len(games_to_import_with_metadata)} games...", "info", duration_ms=0)

    threading.Thread(target=_run_import_with_metadata,
                     args=(app, games_to_import_with_metadata, app.import_mode.get(), notebook),
                     daemon=True).start()

def _run_import_with_metadata(app, games, import_mode, notebook):
    from ..core import import_games # Re-import in thread for safety

    imported_count = 0
    total_count = len(games)
    try:
        for result in import_games(games, import_mode, lambda msg, tag=None: app.log(msg, tag)):
            if result['success']:
                imported_count += 1
                # Remove successfully imported items from the metadata_tree
                # Find the iid by matching the filepath from the result
                iid_to_delete = None
                for iid, game_data in list(app.metadata_tree_data.items()): # Iterate on a copy for safe deletion
                    if game_data['filepath'] == result['filepath']:
                        iid_to_delete = iid
                        break
                if iid_to_delete:
                    app.master.after(0, app.metadata_tree.delete, iid_to_delete)
                    app.master.after(0, lambda id=iid_to_delete: app.metadata_tree_data.pop(id, None)) # Use lambda default for capture

        app.log(f"--- Import Complete: {imported_count} of {total_count} games added. ---", "info")
        if imported_count == total_count:
            app.update_main_status(f"Import Complete: {imported_count} games added.", "success")
        else:
            app.update_main_status(f"Import Complete: {imported_count}/{total_count} games added (some failed).", "warning")
    except Exception as e:
        app.log(f"Error during metadata import: {e}", "error")
        app.update_main_status(f"Metadata Import Failed: {e}", "error")
    finally:
        app.master.after(0, app.import_metadata_button.config, {'state': tk.NORMAL})
        # If all imported or discarded, switch back to scan tab
        app.master.after(0, lambda: _check_and_switch_after_import(app, notebook))


def _check_and_switch_after_import(app, notebook):
    # Only switch if all games have been processed/removed from the treeview
    if not app.metadata_tree.get_children():
        messagebox.showinfo("Scan Review Complete", "All selected games have been processed. Returning to Scan tab.")
        _switch_to_scan_tab(app, notebook)


def _discard_scan(app, notebook):
    confirm = messagebox.askyesno("Discard Scan", "Are you sure you want to discard all current scan results and return to the Scan tab?")
    if confirm:
        app.log("Scan results discarded.", "info")
        app.scanned_games_to_edit = [] # Clear data
        # Clear Treeview
        for item in app.metadata_tree.get_children():
            app.metadata_tree.delete(item)
        app.metadata_tree_data = {} # Clear data storage
        _switch_to_scan_tab(app, notebook)


def _switch_to_scan_tab(app, notebook):
    # Find the scan tab and switch to it
    scan_tab_index = -1
    for i, tab_id in enumerate(notebook.tabs()):
        if notebook.tab(tab_id, "text") == "Scan Collection":
            scan_tab_index = i
            break
    
    if scan_tab_index != -1:
        notebook.select(scan_tab_index)
        # Remove this metadata editor tab if it's not the scan tab itself
        current_tab_text = notebook.tab(notebook.select(), "text")
        if current_tab_text == "Scan Review & Metadata":
             notebook.forget(notebook.index(notebook.select()))
    else:
        # This case implies the Scan Collection tab isn't found, which shouldn't happen.
        app.log("Warning: Could not find 'Scan Collection' tab to switch back to.", "warning")

# --- End Helper Functions ---