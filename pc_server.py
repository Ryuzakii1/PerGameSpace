import os
import sqlite3
import json
import socket
from pathlib import Path

# --- Integration with your existing project ---
try:
    from config import Config
except ImportError:
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!!! ERROR: Could not find config.py.")
    print("!!! Please make sure this script is in the root of your")
    print("!!! PerGameSpace project folder.")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    input("Press Enter to exit.")
    exit()

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    db_path = Path(Config.DATABASE)
    if not db_path.exists():
        print(f"!!! ERROR: Database not found at '{db_path}'")
        return None
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_systems_data():
    """Fetches the list of systems and their game counts."""
    data = []
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute('SELECT system, COUNT(*) as total FROM games GROUP BY system ORDER BY system')
            data = [dict(row) for row in cursor.fetchall()]
            conn.close()
    except Exception as e:
        print(f"Database error in get_systems_data: {e}")
    return data

def get_games_for_system(system_name):
    """Fetches the list of games for a given system."""
    data = []
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, filepath FROM games WHERE system = ? ORDER BY title", (system_name,))
            data = [dict(row) for row in cursor.fetchall()]
            conn.close()
    except Exception as e:
        print(f"Database error in get_games_for_system: {e}")
    return data

def get_all_games_for_systems(systems_str):
    """Fetches all games for a comma-separated list of systems."""
    data = []
    system_list = [s.strip() for s in systems_str.split(',')]
    if not system_list: return []
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in system_list)
            query = f"SELECT id, title, filepath, system FROM games WHERE system IN ({placeholders}) ORDER BY system, title"
            cursor.execute(query, system_list)
            data = [dict(row) for row in cursor.fetchall()]
            conn.close()
    except Exception as e:
        print(f"Database error in get_all_games_for_systems: {e}")
    return data

def send_game_file(conn, game_id):
    """Finds a game by ID, uses its absolute path, and sends the file."""
    try:
        db_conn = get_db_connection()
        if not db_conn:
            conn.sendall(b'ERROR:Database connection failed.')
            return

        game = db_conn.execute("SELECT filepath FROM games WHERE id = ?", (game_id,)).fetchone()
        db_conn.close()

        if not game or not game['filepath']:
            conn.sendall(b'ERROR:Game not found in database.')
            return

        # --- CORRECTED PATH LOGIC ---
        # The database now stores the full, absolute path. We use it directly.
        full_rom_path = game['filepath']
        
        print("\n--- DOWNLOAD DEBUG ---")
        print(f"  Path from Database: {full_rom_path}")
        
        if not os.path.exists(full_rom_path):
            print(f"  File Check: FAILED. File does not exist at this path.")
            print("----------------------\n")
            conn.sendall(b'ERROR:ROM file not found on server disk.')
            return
        
        print(f"  File Check: SUCCESS. File found.")
        print("----------------------\n")
        
        rom_path = Path(full_rom_path)
        file_size = rom_path.stat().st_size
        print(f"Sending file: {rom_path.name}, Size: {file_size} bytes")

        header = f"SIZE:{file_size}\n".encode('utf-8')
        conn.sendall(header)

        with open(rom_path, 'rb') as f:
            while chunk := f.read(4096):
                conn.sendall(chunk)
        print("File sending complete.")

    except Exception as e:
        print(f"Error during file send for game ID {game_id}: {e}")
        try:
            conn.sendall(f'ERROR:{str(e)}'.encode('utf-8'))
        except:
            pass

def main():
    """The main server loop with a non-blocking socket for graceful shutdown."""
    host = '0.0.0.0'
    port = 8081
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((host, port))
        server_socket.listen(5)
        server_socket.settimeout(1.0) # Set a 1-second timeout
        
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); local_ip = s.getsockname()[0]; s.close()
        print("============================================================")
        print(f"SUCCESS! Anbernic server is listening on {local_ip}:{port}")
        print("Press Ctrl+C to stop the server.")
        print("============================================================")

        while True:
            try:
                conn, addr = server_socket.accept()
                print(f"Connection from {addr}")
                with conn:
                    request = conn.recv(1024).decode('utf-8').strip()
                    
                    if request == 'GET_SYSTEMS':
                        data = get_systems_data()
                        conn.sendall(json.dumps(data).encode('utf-8'))
                    elif request.startswith('GET_GAMES:'):
                        system_name = request.split(':', 1)[1]
                        data = get_games_for_system(system_name)
                        conn.sendall(json.dumps(data).encode('utf-8'))
                    elif request.startswith('GET_ALL_GAMES_FOR_SYSTEMS:'):
                        systems_str = request.split(':', 1)[1]
                        data = get_all_games_for_systems(systems_str)
                        conn.sendall(json.dumps(data).encode('utf-8'))
                    elif request.startswith('DOWNLOAD_GAME:'):
                        game_id = request.split(':', 1)[1]
                        send_game_file(conn, game_id)

            except socket.timeout:
                continue # This is expected, just loop again
            except Exception as e:
                print(f"Error handling client connection: {e}")
    
    except KeyboardInterrupt:
        print("\nCtrl+C received. Shutting down server.")
    except Exception as e:
        print(f"A fatal server error occurred: {e}")
    finally:
        if server_socket:
            server_socket.close()
            print("Server socket closed.")

if __name__ == '__main__':
    main()
