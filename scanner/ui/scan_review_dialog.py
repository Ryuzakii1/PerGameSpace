# scanner/ui/scan_review_dialog.py

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time

# CORRECTED IMPORT: Use the new function name 'fetch_igdb_data'
from ..core import import_games, fetch_igdb_data
from ..utils.theme_utils import apply_widget_theme_recursive

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class ScanReviewDialog(tk.Toplevel):
    def __init__(self, parent, app, scanned_games_data, supported_systems_list):
        super().__init__(parent)
        self.parent = parent
        self.app = app
        self.scanned_games_data = scanned_games_data
        self.supported_systems = supported_systems_list

        self.title("Scan Review & Metadata Editor")
        self.geometry("1000x700")
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.configure(bg=self.app.style.lookup('.', 'background'))
        apply_widget_theme_recursive(self, self.app.style.lookup('.', 'background'), self.app.style.lookup('.', 'foreground'), self.app.style.lookup('TEntry', 'fieldbackground'))

        dialog_frame = ttk.Frame(self, padding="10")
        dialog_frame.pack(fill=tk.BOTH, expand=True)
        dialog_frame.rowconfigure(1, weight=1)
        dialog_frame.columnconfigure(0, weight=1)

        # --- Top Controls ---
        controls_frame = ttk.Frame(dialog_frame)
        controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.scan_metadata_button = ttk.Button(controls_frame, text="Scan Metadata (IGDB)", command=self._start_metadata_scan_thread)
        self.scan_metadata_button.pack(side=tk.LEFT, padx=(0, 5))

        self.remove_selected_button = ttk.Button(controls_frame, text="Remove Selected", command=self._remove_selected_from_view)
        self.remove_selected_button.pack(side=tk.LEFT)

        # --- Main Paned Window ---
        paned_window = ttk.PanedWindow(dialog_frame, orient=tk.HORIZONTAL)
        paned_window.grid(row=1, column=0, sticky="nsew")

        # --- Left Pane: Treeview ---
        tree_frame = ttk.Frame(paned_window)
        game_columns = ("Title", "System", "Genre", "Year")
        self.metadata_tree = ttk.Treeview(tree_frame, columns=game_columns, show="headings")
        for col in game_columns: self.metadata_tree.heading(col, text=col, anchor=tk.W)
        self.metadata_tree.column("Title", width=250, stretch=True)
        self.metadata_tree.column("System", width=120)
        self.metadata_tree.column("Genre", width=100)
        self.metadata_tree.column("Year", width=60, anchor=tk.CENTER)
        self.metadata_tree.pack(fill=tk.BOTH, expand=True)
        paned_window.add(tree_frame, weight=3)

        # --- Right Pane: Detail Editor ---
        detail_container = ttk.Frame(paned_window)
        detail_container.columnconfigure(0, weight=1)
        detail_container.rowconfigure(1, weight=1)
        
        cover_frame = ttk.LabelFrame(detail_container, text="Cover Art", padding=5)
        cover_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        cover_frame.columnconfigure(0, weight=1)
        if PIL_AVAILABLE:
            self.cover_image_label = ttk.Label(cover_frame, text="No Cover Art", anchor=tk.CENTER)
            self.cover_image_label.pack(pady=5)
        else:
            ttk.Label(cover_frame, text="Pillow library not found.", wraplength=200).pack()

        detail_frame = ttk.LabelFrame(detail_container, text="Game Details", padding="10")
        detail_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        detail_frame.columnconfigure(1, weight=1)
        
        self.detail_widgets = {'entries': {}}
        fields = ["Title", "System", "Genre", "Release Year", "Developer", "Publisher", "Play Status"]
        for i, field in enumerate(fields):
            ttk.Label(detail_frame, text=f"{field}:").grid(row=i, column=0, sticky="w", padx=5, pady=2)
            var = tk.StringVar()
            entry = ttk.Entry(detail_frame, textvariable=var)
            entry.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
            field_key = field.lower().replace(" ", "_")
            self.detail_widgets['entries'][field_key] = var
            var.trace_add("write", lambda n, i, m, fk=field_key: self._on_detail_edit(fk))
        
        ttk.Label(detail_frame, text="Description:").grid(row=len(fields), column=0, sticky="nw", padx=5, pady=2)
        self.detail_widgets['description'] = scrolledtext.ScrolledText(detail_frame, wrap=tk.WORD, height=8, font=('Consolas', 9))
        self.detail_widgets['description'].grid(row=len(fields), column=1, sticky="nsew", padx=5, pady=2)
        self.detail_widgets['description'].bind("<KeyRelease>", lambda e: self._on_detail_edit('description'))
        detail_frame.rowconfigure(len(fields), weight=1)
        paned_window.add(detail_container, weight=2)

        # --- Bottom Controls ---
        bottom_controls = ttk.Frame(dialog_frame)
        bottom_controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.discard_scan_button = ttk.Button(bottom_controls, text="Discard All", command=self._discard_scan)
        self.discard_scan_button.pack(side=tk.RIGHT, padx=5)
        self.import_metadata_button = ttk.Button(bottom_controls, text="Import Selected", command=self._import_selected_games_with_metadata)
        self.import_metadata_button.pack(side=tk.RIGHT, padx=5)

        self.metadata_tree.bind("<<TreeviewSelect>>", self._on_metadata_tree_select)
        self._populate_metadata_tree()

    def _on_closing(self):
        if messagebox.askokcancel("Quit", "Discard scan results and close?", parent=self):
            self.destroy()

    def _populate_metadata_tree(self):
        for item in self.metadata_tree.get_children(): self.metadata_tree.delete(item)
        for i, game in enumerate(self.scanned_games_data):
            # Use filepath as a unique identifier for this session
            game['iid'] = game['filepath']
            self.metadata_tree.insert('', 'end', iid=game['iid'], values=(
                game.get('title', ''), game.get('system', ''), game.get('genre', ''), game.get('release_year', '')
            ))
        self.app.log(f"Review dialog populated with {len(self.scanned_games_data)} games.", "info")

    def _on_metadata_tree_select(self, event=None):
        if not self.metadata_tree.selection(): return
        selected_iid = self.metadata_tree.selection()[0]
        game_data = next((g for g in self.scanned_games_data if g['iid'] == selected_iid), None)
        if not game_data: return

        self._populating_details = True
        for key, var in self.detail_widgets['entries'].items():
            var.set(game_data.get(key, ''))
        self.detail_widgets['description'].delete(1.0, tk.END)
        self.detail_widgets['description'].insert(tk.END, game_data.get('description') or '')
        self._populating_details = False

    def _on_detail_edit(self, field_key):
        if getattr(self, '_populating_details', False): return
        if not self.metadata_tree.selection(): return
        
        selected_iid = self.metadata_tree.selection()[0]
        game_data = next((g for g in self.scanned_games_data if g['iid'] == selected_iid), None)
        if not game_data: return

        if field_key == 'description':
            new_value = self.detail_widgets['description'].get(1.0, tk.END).strip()
        else:
            new_value = self.detail_widgets['entries'][field_key].get()
        
        game_data[field_key] = new_value
        
        # Update treeview if it's a displayed column
        if field_key in ['title', 'system', 'genre', 'release_year']:
            self._update_treeview_row(game_data)

    def _update_treeview_row(self, game_data):
        self.metadata_tree.item(game_data['iid'], values=(
            game_data.get('title', ''), game_data.get('system', ''), game_data.get('genre', ''), game_data.get('release_year', '')
        ))

    def _start_metadata_scan_thread(self):
        selected_iids = self.metadata_tree.selection()
        if not selected_iids:
            messagebox.showwarning("No Selection", "Please select games to scan.", parent=self)
            return
        
        games_to_scan = [g for g in self.scanned_games_data if g['iid'] in selected_iids]
        self._set_controls_state(tk.DISABLED)
        self.app.log(f"Starting metadata scan for {len(games_to_scan)} games...", "info")
        threading.Thread(target=self._run_metadata_scan, args=(games_to_scan,), daemon=True).start()

    def _run_metadata_scan(self, games_to_scan):
        client_id = self.app.igdb_client_id.get()
        client_secret = self.app.igdb_client_secret.get()
        if not client_id or not client_secret:
            self.app.master.after(0, lambda: messagebox.showerror("API Keys Missing", "Set IGDB credentials in Settings.", parent=self))
        else:
            for game_data in games_to_scan:
                # CORRECTED FUNCTION CALL: Use fetch_igdb_data and unpack the result
                fetched_metadata, _ = fetch_igdb_data(game_data['title'], game_data['system'], self.app.log, client_id, client_secret)
                if fetched_metadata:
                    game_data.update(fetched_metadata)
                    self.app.master.after(0, self._update_treeview_row, game_data)
                time.sleep(0.25)
        self.app.master.after(0, self._set_controls_state, tk.NORMAL)
        self.app.master.after(0, self._on_metadata_tree_select) # Refresh details for selection

    def _remove_selected_from_view(self):
        selected_iids = self.metadata_tree.selection()
        if not selected_iids: return
        for iid in selected_iids:
            self.metadata_tree.delete(iid)
        self.scanned_games_data = [g for g in self.scanned_games_data if g['iid'] not in selected_iids]
        # Clear details panel
        self._populating_details = True
        for var in self.detail_widgets['entries'].values(): var.set('')
        self.detail_widgets['description'].delete(1.0, tk.END)
        self._populating_details = False

    def _import_selected_games_with_metadata(self):
        selected_iids = self.metadata_tree.selection()
        if not selected_iids:
            messagebox.showwarning("No Selection", "Please select games to import.", parent=self)
            return
        games_to_import = [g for g in self.scanned_games_data if g['iid'] in selected_iids]
        self._set_controls_state(tk.DISABLED)
        threading.Thread(target=self._run_import, args=(games_to_import,), daemon=True).start()

    def _run_import(self, games):
        imported_filepaths = []
        for result in import_games(games, self.app.import_mode.get(), self.app.log):
            if result.get('success'):
                imported_filepaths.append(result['filepath'])
        
        # On main thread, remove imported games from view
        def update_ui_after_import():
            self.scanned_games_data = [g for g in self.scanned_games_data if g['filepath'] not in imported_filepaths]
            self._populate_metadata_tree()
            self._set_controls_state(tk.NORMAL)
            if not self.scanned_games_data:
                messagebox.showinfo("Import Complete", "All games processed.", parent=self)
                self.destroy()
        
        self.app.master.after(0, update_ui_after_import)

    def _discard_scan(self):
        if messagebox.askyesno("Discard All", "Discard all remaining games from this scan?", parent=self):
            self.destroy()

    def _set_controls_state(self, state):
        self.scan_metadata_button.config(state=state)
        self.import_metadata_button.config(state=state)
        self.discard_scan_button.config(state=state)
        self.remove_selected_button.config(state=state)
