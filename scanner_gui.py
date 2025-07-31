# scanner_gui.py
# Main entry point for the scanner GUI application.
# This script checks for the database and then launches the main app.

import tkinter as tk
from tkinter import messagebox
import os
import sys

# Add the project root to the Python path to allow imports from the scanner package
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from scanner.app import ScannerGUI
from scanner.config import DATABASE_PATH

def main():
    """Main function to check for the database and launch the GUI."""
    # First, check if the database exists before creating the GUI window.
    if not os.path.exists(DATABASE_PATH):
        # Create a temporary root window just for the error message
        root = tk.Tk()
        root.withdraw() # Hide the main window
        messagebox.showerror(
            "Database Not Found",
            f"The database file was not found at:\n{os.path.abspath(DATABASE_PATH)}\n\n"
            "Please run the main web application (run.py) at least once to create it."
        )
        sys.exit(1) # Exit the script if the database is not found
    
    # If the database exists, create and run the main application window.
    root = tk.Tk()
    app = ScannerGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()