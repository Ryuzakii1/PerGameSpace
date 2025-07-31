# scanner/utils.py
# Contains shared helper functions used by the GUI.

import tkinter as tk

def log_message(widget, message, tag=None):
    """Safely logs a message to the Tkinter ScrolledText widget from any thread."""
    if widget.winfo_exists():
        # Use a lambda to capture the current state of message and tag
        widget.master.after(0, lambda m=message, t=tag: widget.insert(tk.END, m + '\n', t))
        widget.master.after(0, lambda: widget.see(tk.END))
