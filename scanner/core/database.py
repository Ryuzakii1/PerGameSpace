# scanner/core/database.py
import os
import sqlite3
from ..config import DATABASE_PATH

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    if not os.path.exists(DATABASE_PATH):
        raise FileNotFoundError(f"Database not found at '{DATABASE_PATH}'.\nPlease run the main web app (run.py) once to create it.")
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn
