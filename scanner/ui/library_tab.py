# scanner/ui/library_tab.py

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import os
from pathlib import Path
import requests
import io

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from ..core import get_all_games_from_db, update_game_metadata_in_db, delete_games_from_db, set_game_cover_image, fetch_igdb_data, download_and_set_cover_image

def create_library_tab(notebook, app):
    """Creates the UI for the Library Management tab."""
    library_frame = ttk.Frame(notebook, padding="10")
    notebook.add(library_frame, text="Library Management")

    app.library_tree = None
    app.library_detail_widgets = {}
    app.modified_games = {}

    # --- Top Frame: Controls ---
    controls_frame = ttk.Frame(library_frame)
    controls_frame.pack(fill=tk.X, pady=(0, 10))
    
    app.library_search_var = tk.StringVar()
    search_entry = ttk.Entry(controls_frame, textvariable=app.library_search_var, width=30)
    search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
    search_entry.bind("<KeyRelease>", lambda e: filter_library_view(app))

    scan_all_button = ttk.Button(controls_frame, text="Scan All Metadata", command=lambda: scan_all_metadata(app))
    scan_all_button.pack(side=tk.LEFT, padx=5)

    delete_button = ttk.Button(controls_frame, text="Delete Selected", command=lambda: delete_selected_games(app))
    delete_button.pack(side=tk.RIGHT, padx=(5, 0))
    
    save_button = ttk.Button(controls_frame, text="Save Changes", command=lambda: save_all_changes(app))
    save_button.pack(side=tk.RIGHT, padx=(5, 0))

    refresh_button = ttk.Button(controls_frame, text="Refresh", command=lambda: refresh_library_view(app))
    refresh_button.pack(side=tk.RIGHT)

    # --- Main Content PanedWindow ---
    paned_window = ttk.PanedWindow(library_frame, orient=tk.HORIZONTAL)
    paned_window.pack(fill=tk.BOTH, expand=True)

    # --- Left Pane: Games Treeview ---
    tree_frame = ttk.Frame(paned_window)
    columns = ("Title", "System", "Genre", "Year", "Play Status")
    app.library_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
    for col in columns: app.library_tree.heading(col, text=col, anchor=tk.W)
    app.library_tree.column("Title", width=250, stretch=True)
    app.library_tree.column("System", width=120)
    app.library_tree.pack(fill=tk.BOTH, expand=True)
    paned_window.add(tree_frame, weight=3)

    # --- Right Pane: Detail Editor ---
    detail_container = ttk.Frame(paned_window)
    detail_container.columnconfigure(0, weight=1)
    detail_container.rowconfigure(1, weight=1)
    
    cover_frame = ttk.LabelFrame(detail_container, text="Cover Art", padding=5)
    cover_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
    cover_frame.columnconfigure(0, weight=1)
    if PIL_AVAILABLE:
        app.cover_image_label = ttk.Label(cover_frame, text="No Cover Art", anchor=tk.CENTER)
        app.cover_image_label.pack(pady=5)
        
        cover_buttons_frame = ttk.Frame(cover_frame)
        cover_buttons_frame.pack(pady=5)
        ttk.Button(cover_buttons_frame, text="Set from File...", command=lambda: change_cover_art(app)).pack(side=tk.LEFT, padx=5)
        ttk.Button(cover_buttons_frame, text="Fetch from IGDB...", command=lambda: fetch_cover_from_igdb(app)).pack(side=tk.LEFT, padx=5)
    else:
        ttk.Label(cover_frame, text="Pillow library not found.\n'pip install Pillow'", wraplength=200).pack()

    detail_frame = ttk.LabelFrame(detail_container, text="Selected Game Details", padding="10")
    detail_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
    detail_frame.columnconfigure(1, weight=1)
    
    fields = ["Title", "System", "Genre", "Release Year", "Developer", "Publisher", "Play Status"]
    app.library_detail_widgets['entries'] = {}
    for i, field in enumerate(fields):
        ttk.Label(detail_frame, text=f"{field}:").grid(row=i, column=0, sticky="w", padx=5, pady=2)
        var = tk.StringVar()
        entry = ttk.Entry(detail_frame, textvariable=var)
        entry.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
        field_key = field.lower().replace(" ", "_")
        app.library_detail_widgets['entries'][field_key] = var
        var.trace_add("write", lambda n, i, m, fk=field_key: on_detail_edit(app, fk))
    
    ttk.Label(detail_frame, text="Description:").grid(row=len(fields), column=0, sticky="nw", padx=5, pady=2)
    app.library_detail_widgets['description'] = scrolledtext.ScrolledText(detail_frame, wrap=tk.WORD, height=8, font=('Consolas', 9))
    app.library_detail_widgets['description'].grid(row=len(fields), column=1, sticky="nsew", padx=5, pady=2)
    app.library_detail_widgets['description'].bind("<KeyRelease>", lambda e: on_detail_edit(app, 'description'))
    detail_frame.rowconfigure(len(fields), weight=1)
    paned_window.add(detail_container, weight=2)

    app.library_tree.bind("<<TreeviewSelect>>", lambda e: on_library_game_select(app))

def refresh_library_view(app, preserve_selection=True):
    selected_id = None
    if preserve_selection and app.library_tree.selection():
        selected_iid = app.library_tree.selection()[0]
        if selected_iid in app.library_tree_data:
             selected_id = app.library_tree_data[selected_iid]['id']
    threading.Thread(target=_do_refresh, args=(app, selected_id), daemon=True).start()

def _do_refresh(app, selected_id=None):
    try:
        all_games = get_all_games_from_db()
        app.master.after(0, lambda: _populate_library_tree(app, all_games, selected_id))
    except Exception as e:
        app.log(f"Error refreshing library: {e}", "error")

def _populate_library_tree(app, games, selected_id=None):
    for item in app.library_tree.get_children(): app.library_tree.delete(item)
    app.library_tree_data = {}
    app.full_library_data = games
    iid_to_select = None
    for game in games:
        iid = f"game_{game['id']}"
        app.library_tree_data[iid] = game
        app.library_tree.insert('', 'end', iid=iid, values=(game.get('title', ''), game.get('system', ''), game.get('genre', ''), game.get('release_year', ''), game.get('play_status', 'Not Played')))
        if selected_id and game['id'] == selected_id: iid_to_select = iid
    if iid_to_select:
        app.library_tree.selection_set(iid_to_select)
        app.library_tree.focus(iid_to_select)
        app.library_tree.see(iid_to_select)
    filter_library_view(app)
    app.log(f"Library view populated with {len(games)} games.", "success")

def on_library_game_select(app):
    if not app.library_tree.selection(): return
    selected_iid = app.library_tree.selection()[0]
    game_data = app.library_tree_data.get(selected_iid)
    if not game_data: return
    app._populating_details = True
    for key, var in app.library_detail_widgets['entries'].items(): var.set(game_data.get(key, ''))
    app.library_detail_widgets['description'].delete(1.0, tk.END)
    app.library_detail_widgets['description'].insert(tk.END, game_data.get('description') or '')
    if PIL_AVAILABLE: load_cover_image(app, game_data.get('cover_image_path'))
    app._populating_details = False

def on_detail_edit(app, field_key):
    if getattr(app, '_populating_details', False): return
    if not app.library_tree.selection(): return
    selected_iid = app.library_tree.selection()[0]
    game_id = app.library_tree_data[selected_iid]['id']
    if field_key == 'description': new_value = app.library_detail_widgets['description'].get(1.0, tk.END).strip()
    else: new_value = app.library_detail_widgets['entries'][field_key].get()
    if game_id not in app.modified_games: app.modified_games[game_id] = {}
    app.modified_games[game_id][field_key] = new_value

def save_all_changes(app):
    if not app.modified_games: return
    games_to_update = dict(app.modified_games)
    app.modified_games.clear()
    threading.Thread(target=_do_save, args=(app, games_to_update), daemon=True).start()

def _do_save(app, games_to_update):
    try:
        for game_id, changes in games_to_update.items(): update_game_metadata_in_db(game_id, changes)
        app.master.after(0, lambda: messagebox.showinfo("Success", f"Saved changes for {len(games_to_update)} games."))
        app.master.after(0, lambda: refresh_library_view(app))
    except Exception as e:
        app.log(f"Error saving changes: {e}", "error")

def delete_selected_games(app):
    selected_iids = app.library_tree.selection()
    if not selected_iids: return
    game_titles = "\n".join([app.library_tree_data[iid]['title'] for iid in selected_iids])
    if not messagebox.askyesno("Confirm Delete", f"Permanently delete {len(selected_iids)} game(s)?\n\n{game_titles}"): return
    game_ids_to_delete = [app.library_tree_data[iid]['id'] for iid in selected_iids]
    threading.Thread(target=_do_delete, args=(app, game_ids_to_delete), daemon=True).start()

def _do_delete(app, game_ids):
    try:
        delete_games_from_db(game_ids, app.log)
        app.master.after(0, lambda: refresh_library_view(app, preserve_selection=False))
    except Exception as e:
        app.log(f"Error deleting games: {e}", "error")

def filter_library_view(app):
    search_term = app.library_search_var.get().lower()
    for item in app.library_tree.get_children(): app.library_tree.delete(item)
    for game in app.full_library_data:
        if search_term in game.get('title', '').lower() or search_term in game.get('system', '').lower():
            iid = f"game_{game['id']}"
            app.library_tree.insert('', 'end', iid=iid, values=(game.get('title', ''), game.get('system', ''), game.get('genre', ''), game.get('release_year', ''), game.get('play_status', 'Not Played')))

def load_cover_image(app, image_path, max_size=(200, 200)):
    if not image_path or not os.path.exists(image_path):
        app.cover_image_label.config(image='', text="No Cover Art")
        app.cover_image_label.image = None
        return
    try:
        img = Image.open(image_path)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        app.cover_image_label.config(image=photo, text="")
        app.cover_image_label.image = photo
    except Exception as e:
        app.cover_image_label.config(image='', text="Error Loading")
        app.cover_image_label.image = None

def change_cover_art(app):
    if not app.library_tree.selection(): return
    selected_iid = app.library_tree.selection()[0]
    game_id = app.library_tree_data[selected_iid]['id']
    filepath = filedialog.askopenfilename(title="Select Cover Image", filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
    if not filepath: return
    threading.Thread(target=_do_change_cover, args=(app, game_id, filepath), daemon=True).start()

def _do_change_cover(app, game_id, new_image_path):
    try:
        new_db_path = set_game_cover_image(game_id, new_image_path)
        app.master.after(0, lambda: load_cover_image(app, new_db_path))
        app.master.after(0, lambda: refresh_library_view(app))
    except Exception as e:
        app.log(f"Error changing cover art: {e}", "error")

def scan_all_metadata(app):
    if not messagebox.askyesno("Scan All Metadata", f"Scan IGDB for metadata for all {len(app.full_library_data)} games in the library? This may take a long time and consume API credits."):
        return
    threading.Thread(target=_do_scan_all, args=(app,), daemon=True).start()

def _do_scan_all(app):
    client_id, client_secret = app.igdb_client_id.get(), app.igdb_client_secret.get()
    if not client_id or not client_secret:
        app.master.after(0, lambda: messagebox.showerror("API Keys Missing", "Set IGDB credentials in Settings."))
        return
    
    for i, game in enumerate(app.full_library_data):
        app.master.after(0, app.update_main_status, f"Scanning... {i+1}/{len(app.full_library_data)}: {game['title']}", "info", 0)
        metadata, _ = fetch_igdb_data(game['title'], game['system'], app.log, client_id, client_secret)
        if metadata:
            update_game_metadata_in_db(game['id'], metadata)
        time.sleep(0.3) # Rate limit
    app.master.after(0, app.update_main_status, "Full metadata scan complete!", "success")
    app.master.after(0, lambda: refresh_library_view(app))

def fetch_cover_from_igdb(app):
    if not app.library_tree.selection(): return
    selected_iid = app.library_tree.selection()[0]
    game = app.library_tree_data[selected_iid]
    threading.Thread(target=_do_fetch_cover, args=(app, game), daemon=True).start()

def _do_fetch_cover(app, game):
    client_id, client_secret = app.igdb_client_id.get(), app.igdb_client_secret.get()
    if not client_id or not client_secret:
        app.master.after(0, lambda: messagebox.showerror("API Keys Missing", "Set IGDB credentials in Settings."))
        return
    
    _, image_urls = fetch_igdb_data(game['title'], game['system'], app.log, client_id, client_secret)
    if not image_urls:
        app.master.after(0, lambda: messagebox.showinfo("No Covers Found", "No covers found on IGDB for this game."))
        return
    
    app.master.after(0, lambda: CoverSelectionDialog(app, game['id'], image_urls))

class CoverSelectionDialog(tk.Toplevel):
    def __init__(self, app, game_id, image_urls):
        super().__init__(app.master)
        self.app = app
        self.game_id = game_id
        self.image_urls = image_urls
        self.title("Select a Cover from IGDB")
        self.geometry("800x600")
        self.transient(app.master)
        self.grab_set()

        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.image_labels = []
        threading.Thread(target=self._load_images, args=(scrollable_frame,), daemon=True).start()

    def _load_images(self, parent_frame):
        for url in self.image_urls:
            try:
                response = requests.get(url, stream=True, timeout=5)
                response.raise_for_status()
                img_data = response.content
                img = Image.open(io.BytesIO(img_data))
                img.thumbnail((150, 200), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                
                def on_click(u=url):
                    self._select_cover(u)

                self.app.master.after(0, self._create_image_label, parent_frame, photo, on_click)
            except Exception as e:
                print(f"Failed to load image {url}: {e}")

    def _create_image_label(self, parent, photo, callback):
        label = ttk.Label(parent, image=photo, cursor="hand2")
        label.image = photo
        label.pack(side=tk.LEFT, padx=5, pady=5)
        label.bind("<Button-1>", lambda e: callback())

    def _select_cover(self, url):
        threading.Thread(target=self._do_set_cover, args=(url,), daemon=True).start()
        self.destroy()

    def _do_set_cover(self, url):
        try:
            new_path = download_and_set_cover_image(self.game_id, url, self.app.log)
            self.app.master.after(0, lambda: load_cover_image(self.app, new_path))
            self.app.master.after(0, lambda: refresh_library_view(self.app))
        except Exception as e:
            self.app.log(f"Failed to set cover from URL: {e}", "error")
