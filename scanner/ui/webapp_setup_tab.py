# scanner/ui/webapp_setup_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import subprocess
import sys
import os
import shutil

def create_webapp_setup_tab(notebook, app):
    """Creates the simplified UI for the Web Application Setup tab."""
    webapp_tab = ttk.Frame(notebook, padding="10")
    notebook.add(webapp_tab, text="Web App Setup")

    webapp_tab.columnconfigure(0, weight=1)
    webapp_tab.rowconfigure(1, weight=1)  # Allow the output frame to expand

    app.web_server_process = None  # Initialize to None

    # --- Section for Server Control ---
    setup_frame = ttk.LabelFrame(webapp_tab, text="Web Server Control", padding="15")
    setup_frame.grid(row=0, column=0, sticky="ew", pady=10, padx=5)
    setup_frame.columnconfigure(0, weight=1)
    setup_frame.columnconfigure(1, weight=1)

    # Simplified introductory text
    ttk.Label(setup_frame, text="Use this tab to start and stop the local web application server.").grid(row=0, column=0, columnspan=3, sticky="w", pady=5)

    # Server Control (Start/Stop)
    btn_start_server = ttk.Button(setup_frame, text="Start Web Server", command=lambda: start_web_server(app))
    btn_start_server.grid(row=1, column=0, sticky="ew", pady=5, padx=(0, 5))

    btn_stop_server = ttk.Button(setup_frame, text="Stop Web Server", command=lambda: stop_web_server(app))
    btn_stop_server.grid(row=1, column=1, sticky="ew", pady=5, padx=(5, 0))
    btn_stop_server.config(state=tk.DISABLED)  # Initially disabled

    lbl_server_status = ttk.Label(setup_frame, text="", width=2)  # Status label for server
    lbl_server_status.grid(row=1, column=2, sticky="w", padx=(5, 0))

    # --- Section for Command Output ---
    output_frame = ttk.LabelFrame(webapp_tab, text="Server Output", padding="10")
    output_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10), padx=5)
    output_frame.columnconfigure(0, weight=1)
    output_frame.rowconfigure(0, weight=1)

    app.webapp_output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, font=('Consolas', 9), height=10)
    app.webapp_output_text.pack(fill=tk.BOTH, expand=True)
    app.webapp_output_text.config(state=tk.DISABLED)

    # Store references to the necessary buttons and labels on the 'app' instance
    app.btn_start_server = btn_start_server
    app.btn_stop_server = btn_stop_server
    app.lbl_server_status = lbl_server_status

# --- Helper functions for web app setup operations ---

def _set_status_label(app, label_widget, status_char, color=None):
    """Helper to update status label with character and color."""
    bg_color = app.style.lookup("TFrame", "background")
    app.master.after(0, lambda: label_widget.config(text=status_char, foreground=color or "black", background=bg_color))

def _append_to_output(widget, text, tag=None):
    """Appends text to the ScrolledText widget."""
    widget.config(state=tk.NORMAL)
    widget.insert(tk.END, text, tag)
    widget.see(tk.END)
    widget.config(state=tk.DISABLED)

def _check_prerequisite(app, output_widget, status_label):
    """Checks for Python and the web app's run script."""
    if not shutil.which(sys.executable):
        msg = "Error: Python executable not found. Please ensure Python is installed correctly."
        app.log(msg, "error")
        app.master.after(0, lambda: _append_to_output(output_widget, msg + "\n", 'error'))
        _set_status_label(app, status_label, "❌", "red")
        return False

    # UPDATED: Point to the correct web server script
    webapp_script_name = "run.py"
    full_path = os.path.join(app.base_dir, webapp_script_name)
    if not os.path.exists(full_path):
        msg = f"Error: Web app script '{webapp_script_name}' not found in '{app.base_dir}'."
        app.log(msg, "error")
        app.master.after(0, lambda: _append_to_output(output_widget, msg + "\n", 'error'))
        _set_status_label(app, status_label, "❌", "red")
        return False
    
    return True

def start_web_server(app):
    """Starts the web application server as a long-running process."""
    if app.web_server_process and app.web_server_process.poll() is None:
        messagebox.showwarning("Server Running", "The web server is already running.")
        return

    if not _check_prerequisite(app, app.webapp_output_text, app.lbl_server_status):
        return

    # UPDATED: Point to the correct web server script
    command = [sys.executable, os.path.join(app.base_dir, "run.py")]
    app.log("Attempting to start web server...", "info")
    app.update_main_status("Starting web server...", "info", duration_ms=0)
    _set_status_label(app, app.lbl_server_status, "⏳", "orange")

    app.btn_start_server.config(state=tk.DISABLED)
    app.btn_stop_server.config(state=tk.DISABLED)

    app.webapp_output_text.config(state=tk.NORMAL)
    app.webapp_output_text.delete(1.0, tk.END)
    app.webapp_output_text.insert(tk.END, f"Starting server: {' '.join(command)}\n\n", 'info')
    app.webapp_output_text.config(state=tk.DISABLED)

    def _start_server_thread():
        try:
            # Prevent a blank console window from appearing on Windows
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            
            app.web_server_process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, cwd=app.base_dir, creationflags=creation_flags
            )

            app.log("Web server process initiated.", "info")
            threading.Thread(target=_read_process_output, args=(app.web_server_process.stdout, app.webapp_output_text, 'stdout', app), daemon=True).start()
            threading.Thread(target=_read_process_output, args=(app.web_server_process.stderr, app.webapp_output_text, 'stderr', app), daemon=True).start()
            threading.Thread(target=_monitor_server_process, args=(app,), daemon=True).start()

            _set_status_label(app, app.lbl_server_status, "🟢", "green")
            app.update_main_status("Web server started!", "success")
            app.master.after(0, app.btn_stop_server.config, {'state': tk.NORMAL})

        except Exception as e:
            app.log(f"Failed to start web server: {e}", "error")
            app.master.after(0, lambda: _append_to_output(app.webapp_output_text, f"\nError: {e}\n", 'error'))
            app.master.after(0, app.btn_start_server.config, {'state': tk.NORMAL})
            _set_status_label(app, app.lbl_server_status, "❌", "red")
            app.update_main_status(f"Server failed to start: {e}", "error")

    threading.Thread(target=_start_server_thread, daemon=True).start()

def _read_process_output(pipe, output_widget, tag, app):
    """Reads output from a process pipe and appends to the widget."""
    try:
        for line in iter(pipe.readline, ''):
            app.master.after(0, lambda l=line: _append_to_output(output_widget, l, tag))
        pipe.close()
    except Exception:
        pass # Pipe closed

def _monitor_server_process(app):
    """Monitors the web server process and updates UI on termination."""
    if app.web_server_process:
        app.web_server_process.wait() # Wait for the process to end
        return_code = app.web_server_process.returncode
        app.log(f"Web server process terminated with exit code: {return_code}", "info")
        app.web_server_process = None
        app.master.after(0, app.btn_start_server.config, {'state': tk.NORMAL})
        app.master.after(0, app.btn_stop_server.config, {'state': tk.DISABLED})
        _set_status_label(app, app.lbl_server_status, "⚪", "gray")

def stop_web_server(app):
    """Stops the running web application server."""
    if not app.web_server_process or app.web_server_process.poll() is not None:
        messagebox.showinfo("No Server", "Web server is not running.")
        return

    app.log("Attempting to stop web server...", "info")
    app.update_main_status("Stopping web server...", "info", duration_ms=0)
    _set_status_label(app, app.lbl_server_status, "⏳", "orange")
    app.btn_stop_server.config(state=tk.DISABLED)

    def _stop_server_thread():
        try:
            app.web_server_process.terminate()
            app.web_server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            app.web_server_process.kill()
            app.log("Web server did not terminate gracefully, forced kill.", "warning")
        except Exception as e:
            app.log(f"Error stopping web server: {e}", "error")
        finally:
            app.update_main_status("Web server stopped.", "success")

    threading.Thread(target=_stop_server_thread, daemon=True).start()
