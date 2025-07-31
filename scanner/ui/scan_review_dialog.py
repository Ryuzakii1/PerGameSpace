# scanner/ui/scan_review_dialog.py

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time

from ..core import import_games, fetch_igdb_metadata
from ..utils.theme_utils import apply_widget_theme_recursive

class ScanReviewDialog(tk.Toplevel):
    def __init__(self, parent, app, scanned_games_data, supported_systems_list):
        super().__init__(parent)
        self.parent = parent
        self.app = app
        self.scanned_games_to_edit = scanned_games_data
        self.supported_systems = supported_systems_list

        self.title("Scan Review & Metadata Editor")
        self.geometry("900x650")
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.configure(bg=self.app.style.lookup('.', 'background'))
        apply_widget_theme_recursive(self, self.app.style.lookup('.', 'background'), self.app.style.lookup('.', 'foreground'), self.app.style.lookup('TEntry', 'fieldbackground'))

        dialog_frame = ttk.Frame(self, padding="10")
        dialog_frame.pack(fill=tk.BOTH, expand=True)
        dialog_frame.columnconfigure(0, weight=3)
        dialog_frame.columnconfigure(1, weight=2)
        dialog_frame.rowconfigure(0, weight=1)

        # --- Left Pane: Treeview ---
        game_columns = ("Title", "System", "Genre", "Year", "Developer", "Publisher", "Status")
        self.metadata_tree = ttk.Treeview(dialog_frame, columns=game_columns, show="headings")
        for col in game_columns:
            self.metadata_tree.heading(col, text=col, anchor=tk.W)
        self.metadata_tree.column("Title", width=180, stretch=tk.YES)
        self.metadata_tree.column("System", width=80, stretch=tk.YES)
        self.metadata_tree.column("Genre", width=80)
        self.metadata_tree.column("Year", width=50, anchor=tk.CENTER)
        self.metadata_tree.column("Developer", width=100)
        self.metadata_tree.column("Publisher", width=100)
        self.metadata_tree.column("Status", width=80)
        self.metadata_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self._populate_metadata_tree(self.scanned_games_to_edit)

        # --- Right Pane: Detail Editor ---
        detail_frame = ttk.LabelFrame(dialog_frame, text="Selected Game Details", padding="10")
        detail_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(3, weight=1)

        self.detail_title_label = ttk.Label(detail_frame, text="Title: (Select a game)", font=('TkDefaultFont', 10, 'bold'))
        self.detail_title_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(detail_frame, text="File Path:").grid(row=1, column=0, sticky="w", pady=(5,0))
        self.detail_filepath_label = ttk.Label(detail_frame, text="", wraplength=250, anchor=tk.W)
        self.detail_filepath_label.grid(row=2, column=0, sticky="ew")
        ttk.Label(detail_frame, text="Description/Notes:").grid(row=3, column=0, sticky="w", pady=(5,0))
        self.detail_description_text = scrolledtext.ScrolledText(detail_frame, wrap=tk.WORD, height=10, font=('Consolas', 9))
        self.detail_description_text.grid(row=4, column=0, sticky="nsew", pady=(0, 5))

        self.metadata_tree.bind("<<TreeviewSelect>>", self._on_metadata_tree_select)
        self.metadata_tree.bind("<Double-1>", self._start_inline_edit)

        # --- Bottom Controls ---
        controls_frame = ttk.Frame(dialog_frame)
        controls_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.scan_metadata_button = ttk.Button(controls_frame, text="Scan Metadata (IGDB)", command=self._start_metadata_scan_thread)
        self.scan_metadata_button.pack(side=tk.LEFT, padx=5)
        self.discard_scan_button = ttk.Button(controls_frame, text="Discard Scan", command=self._discard_scan)
        self.discard_scan_button.pack(side=tk.RIGHT, padx=5)
        self.import_metadata_button = ttk.Button(controls_frame, text="Import Selected Games", command=self._import_selected_games_with_metadata)
        self.import_metadata_button.pack(side=tk.RIGHT, padx=5)

    def _on_closing(self):
        if messagebox.askokcancel("Quit", "Discard scan results and close the editor?", parent=self):
            self.destroy()
            self.parent.grab_release()
            self.app.update_main_status("Scan review discarded.", "info")

    def _populate_metadata_tree(self, games_data):
        self.metadata_tree_data = {}
        for i, game in enumerate(games_data):
            iid = f"game_{i}"
            self.metadata_tree_data[iid] = game
            self.metadata_tree.insert('', 'end', iid=iid, values=(
                game.get('title', ''), game.get('system', ''), game.get('genre', ''),
                game.get('release_year', ''), game.get('developer', ''), game.get('publisher', ''),
                game.get('play_status', 'Not Played')
            ))
        self.app.log(f"Metadata editor populated with {len(games_data)} games.", "info")

    def _on_metadata_tree_select(self, event):
        selected_iid = self.metadata_tree.focus()
        if selected_iid and selected_iid in self.metadata_tree_data:
            game = self.metadata_tree_data[selected_iid]
            self.detail_title_label.config(text=f"Title: {game.get('title', '')} ({game.get('system', '')})")
            self.detail_filepath_label.config(text=game.get('filepath', ''))
            self.detail_description_text.delete(1.0, tk.END)
            self.detail_description_text.insert(tk.END, str(game.get('description', '')))
            self._current_selected_iid = selected_iid
            self.detail_description_text.bind("<FocusOut>", self._on_description_edit_finish)
            self.detail_description_text.bind("<Return>", lambda e: (self._on_description_edit_finish(e), "break"))
        else:
            self.detail_title_label.config(text="Title: (Select a game)")
            self.detail_filepath_label.config(text="")
            self.detail_description_text.delete(1.0, tk.END)
            self._current_selected_iid = None

    def _on_description_edit_finish(self, event=None):
        if self._current_selected_iid and self._current_selected_iid in self.metadata_tree_data:
            game = self.metadata_tree_data[self._current_selected_iid]
            new_description = self.detail_description_text.get(1.0, tk.END).strip()
            if new_description != game.get('description', ''):
                game['description'] = new_description
                self.app.log(f"Description updated for {game.get('title')}", "info")

    def _start_inline_edit(self, event):
        if self.metadata_tree.identify("region", event.x, event.y) != "cell": return
        column = self.metadata_tree.identify_column(event.x)
        column_index = int(column.replace('#', '')) - 1
        item_iid = self.metadata_tree.identify_row(event.y)
        if not item_iid: return

        metadata_keys_map = {0: "title", 1: "system", 2: "genre", 3: "release_year", 4: "developer", 5: "publisher", 6: "play_status"}
        metadata_key = metadata_keys_map.get(column_index)
        if not metadata_key: return

        x, y, width, height = self.metadata_tree.bbox(item_iid, column)
        if not all((x, y, width, height)): return

        game_data_for_item = self.metadata_tree_data[item_iid]
        current_value = str(game_data_for_item.get(metadata_key, ''))

        if metadata_key == "system":
            editor = ttk.Combobox(self.metadata_tree, values=self.supported_systems, state="normal")
            editor.set(current_value)
        else:
            editor = ttk.Entry(self.metadata_tree)
            editor.insert(0, current_value)
        
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()

        def _on_edit_finish(e=None):
            new_value = editor.get().strip()
            game_data = self.metadata_tree_data[item_iid]
            
            if metadata_key == 'release_year' and new_value:
                try:
                    new_value = int(new_value)
                except ValueError:
                    messagebox.showwarning("Invalid Year", f"'{new_value}' is not a valid year.", parent=self)
                    new_value = game_data.get(metadata_key, None)
            
            if game_data.get(metadata_key) != new_value:
                game_data[metadata_key] = new_value
                self.app.log(f"Updated '{metadata_key}' for '{game_data.get('title')}' to '{new_value}'", "info")

            values = list(self.metadata_tree.item(item_iid, 'values'))
            values[column_index] = new_value
            self.metadata_tree.item(item_iid, values=values)
            editor.destroy()

        editor.bind("<Return>", _on_edit_finish)
        editor.bind("<FocusOut>", _on_edit_finish)
        if isinstance(editor, ttk.Combobox):
            editor.bind("<<ComboboxSelected>>", _on_edit_finish)

    def _import_selected_games_with_metadata(self):
        selected_iids = self.metadata_tree.selection()
        if not selected_iids:
            messagebox.showwarning("No Selection", "Please select games to import.", parent=self)
            return
        
        games_to_import = [self.metadata_tree_data[iid] for iid in selected_iids]
        if not games_to_import: return

        self._set_controls_state(tk.DISABLED)
        self.app.log(f"\n--- Importing {len(games_to_import)} games with metadata... ---", "info")
        self.app.update_main_status(f"Importing {len(games_to_import)} games...", "info", duration_ms=0)
        threading.Thread(target=self._run_import_with_metadata, args=(games_to_import, self.app.import_mode.get()), daemon=True).start()

    def _run_import_with_metadata(self, games, import_mode):
        imported_count = 0
        try:
            for result in import_games(games, import_mode, self.app.log):
                if result.get('success'):
                    imported_count += 1
                    iid_to_delete = next((iid for iid, gd in self.metadata_tree_data.items() if gd['filepath'] == result['filepath']), None)
                    if iid_to_delete:
                        self.app.master.after(0, self.metadata_tree.delete, iid_to_delete)
                        self.app.master.after(0, self.metadata_tree_data.pop, iid_to_delete, None)
            self.app.log(f"--- Import Complete: {imported_count} of {len(games)} games added. ---", "info")
            self.app.update_main_status(f"Import Complete: {imported_count} games added.", "success")
        except Exception as e:
            self.app.log(f"Error during metadata import: {e}", "error")
            self.app.update_main_status(f"Metadata Import Failed: {e}", "error")
        finally:
            self.app.master.after(0, self._set_controls_state, tk.NORMAL)
            self.app.master.after(0, self._check_and_close_dialog_after_import)

    def _check_and_close_dialog_after_import(self):
        if not self.metadata_tree.get_children():
            messagebox.showinfo("Scan Review Complete", "All selected games have been processed.", parent=self)
            self.destroy()
            self.parent.grab_release()

    def _discard_scan(self):
        if messagebox.askyesno("Discard Scan", "Are you sure you want to discard all current scan results?", parent=self):
            self.app.log("Scan results discarded.", "info")
            self.destroy()
            self.parent.grab_release()

    def _start_metadata_scan_thread(self):
        selected_iids = self.metadata_tree.selection()
        if not selected_iids:
            messagebox.showwarning("No Selection", "Please select games to scan for metadata.", parent=self)
            return
        
        games_to_scan = [self.metadata_tree_data[iid] for iid in selected_iids]
        self._set_controls_state(tk.DISABLED)
        self.app.log(f"\n--- Starting metadata scan for {len(games_to_scan)} games... ---", "info")
        self.app.update_main_status(f"Scanning metadata for {len(games_to_scan)} games...", "info", duration_ms=0)
        self.metadata_tree.config(selectmode='none')
        self.metadata_tree.bind("<Double-1>", lambda e: "break")
        threading.Thread(target=self._run_metadata_scan, args=(games_to_scan,), daemon=True).start()

    def _run_metadata_scan(self, games_to_scan):
        client_id = self.app.igdb_client_id.get()
        client_secret = self.app.igdb_client_secret.get()

        if not client_id or not client_secret:
            self.app.master.after(0, lambda: messagebox.showerror("API Keys Missing", "IGDB Client ID or Secret is missing. Please set them in the Settings tab.", parent=self))
            self.app.log("IGDB API keys missing from settings. Metadata scan aborted.", "error")
        else:
            scanned_count = 0
            for i, game_data in enumerate(games_to_scan):
                status_msg = f"Scanning metadata for {game_data['title']}... ({i+1}/{len(games_to_scan)})"
                self.app.master.after(0, self.app.update_main_status, status_msg, "info", 0)
                try:
                    fetched_metadata = fetch_igdb_metadata(game_data['title'], game_data['system'], self.app.log, client_id, client_secret)
                    if fetched_metadata:
                        game_data.update({k: v for k, v in fetched_metadata.items() if v})
                        self.app.log(f"Successfully fetched metadata for '{game_data['title']}'.", "success")
                        scanned_count += 1
                        self.app.master.after(0, self._update_treeview_row_with_metadata, game_data)
                    else:
                        self.app.log(f"No metadata found for '{game_data['title']}'.", "warning")
                except Exception as e:
                    self.app.log(f"Error scanning metadata for '{game_data['title']}': {e}", "error")
                time.sleep(0.25) # Rate limiting
            
            self.app.log(f"--- Metadata scan complete: {scanned_count} of {len(games_to_scan)} games updated. ---", "info")
            self.app.update_main_status(f"Metadata scan complete: {scanned_count} games updated.", "success")
        
        self.app.master.after(0, self._re_enable_metadata_controls)

    def _re_enable_metadata_controls(self):
        self._set_controls_state(tk.NORMAL)
        self.metadata_tree.config(selectmode='extended')
        self.metadata_tree.bind("<Double-1>", self._start_inline_edit)

    def _set_controls_state(self, state):
        self.scan_metadata_button.config(state=state)
        self.import_metadata_button.config(state=state)
        self.discard_scan_button.config(state=state)

    def _update_treeview_row_with_metadata(self, game_data):
        iid_to_update = next((iid for iid, gd in self.metadata_tree_data.items() if gd['filepath'] == game_data['filepath']), None)
        if iid_to_update:
            self.metadata_tree.item(iid_to_update, values=(
                game_data.get('title', ''), game_data.get('system', ''), game_data.get('genre', ''),
                game_data.get('release_year', ''), game_data.get('developer', ''), game_data.get('publisher', ''),
                game_data.get('play_status', 'Not Played')
            ))
