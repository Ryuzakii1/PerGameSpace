# scanner/utils/theme_utils.py

import tkinter as tk
from tkinter import ttk, scrolledtext

def apply_widget_theme_recursive(widget, bg_main, fg_main, entry_bg):
    """
    Recursively applies background and foreground colors to Tkinter widgets.
    This function is designed to be used with a main GUI class's theme
    application logic.

    Args:
        widget: The Tkinter widget (or master window) to start applying themes from.
        bg_main (str): The main background color for frames, labels, etc.
        fg_main (str): The main foreground/text color.
        entry_bg (str): The background color for entry/text input widgets.
    """
    try:
        # Determine appropriate background/foreground based on widget type
        # tk.Frame, tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton, tk.LabelFrame
        if isinstance(widget, (tk.Frame, tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton, tk.LabelFrame)):
            widget.config(bg=bg_main, fg=fg_main)
        # tk.Entry, tk.Text, scrolledtext.ScrolledText
        elif isinstance(widget, (tk.Entry, tk.Text, scrolledtext.ScrolledText)):
            widget.config(bg=entry_bg, fg=fg_main, insertbackground=fg_main)
        # ttk.Notebook requires special handling for its tab frames
        elif isinstance(widget, ttk.Notebook):
            # No need to explicitly configure the Notebook itself here, ttk.Style handles it.
            # But we need to recurse into its tab frames.
            for tab_id in widget.tabs():
                tab_frame = widget.nametowidget(tab_id)
                # For ttk.Frame, we set its 'background' option (what ttk.Frame respects)
                # For tk.Frame, it's 'bg'
                if isinstance(tab_frame, ttk.Frame):
                    tab_frame.config(background=bg_main)
                elif isinstance(tab_frame, tk.Frame): # In case a tk.Frame is used as a tab content
                    tab_frame.config(bg=bg_main)
                # Recursively apply to children within each tab
                for child in tab_frame.winfo_children():
                    apply_widget_theme_recursive(child, bg_main, fg_main, entry_bg)

        # Continue recursion for all general child widgets
        # (This is important for frames and other containers that hold many children)
        for child in widget.winfo_children():
            apply_widget_theme_recursive(child, bg_main, fg_main, entry_bg)

    except tk.TclError:
        # Some widgets might not have 'bg' or 'fg' attributes, or might be destroyed.
        # print(f"Warning: Could not configure widget {widget.__class__.__name__}: {e}")
        pass # Suppress common errors for widgets without certain configs
    except Exception as e:
        # Catch any other unexpected errors during styling
        # print(f"An unexpected error occurred while styling {widget.__class__.__name__}: {e}")
        pass