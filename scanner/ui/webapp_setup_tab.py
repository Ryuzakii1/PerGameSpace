# scanner/ui/webapp_setup_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import subprocess
import sys
import os
import shutil # For shutil.which

def create_webapp_setup_tab(notebook, app):
    """Creates the UI for the Web Application Setup tab."""
    webapp_tab = ttk.Frame(notebook, padding="10")
    notebook.add(webapp_tab, text="Web App Setup")

    webapp_tab.columnconfigure(0, weight=1)
    webapp_tab.rowconfigure(1, weight=0, minsize=150) # Set a minsize to ensure some height

    app.web_server_process = None # Initialize to None

    # --- Section for Setup Steps ---
    setup_frame = ttk.LabelFrame(webapp_tab, text="Web Application Setup Steps", padding="15")
    setup_frame.grid(row=0, column=0, sticky="ew", pady=10, padx=5)
    setup_frame.columnconfigure(0, weight=1)
    setup_frame.columnconfigure(1, weight=0) # Column for status icons

    ttk.Label(setup_frame, text="This tab helps you set up and manage the local web application.").grid(row=0, column=0, columnspan=2, sticky="w", pady=5)
    ttk.Label(setup_frame, text="Ensure you have Python and pip installed on your system.").grid(row=1, column=0, columnspan=2, sticky="w", pady=5)

    # Row 2: Install Python Dependencies
    btn_install_deps = ttk.Button(setup_frame, text="1. Install Python Dependencies", command=lambda: install_python_dependencies(app))
    btn_install_deps.grid(row=2, column=0, sticky="ew", pady=5, padx=(0,5))
    lbl_install_deps_status = ttk.Label(setup_frame, text="", width=2) # Status label
    lbl_install_deps_status.grid(row=2, column=1, sticky="w")

    # Row 3: Initialize/Migrate Database
    btn_init_db = ttk.Button(setup_frame, text="2. Initialize/Migrate Database", command=lambda: init_migrate_database(app))
    btn_init_db.grid(row=3, column=0, sticky="ew", pady=5, padx=(0,5))
    lbl_init_db_status = ttk.Label(setup_frame, text="", width=2) # Status label
    lbl_init_db_status.grid(row=3, column=1, sticky="w")

    # Row 4: Server Control (Start/Stop)
    server_control_frame = ttk.Frame(setup_frame)
    server_control_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=5) # Span across both columns
    server_control_frame.columnconfigure(0, weight=1)
    server_control_frame.columnconfigure(1, weight=1)
    server_control_frame.columnconfigure(2, weight=0) # For server status icon

    btn_start_server = ttk.Button(server_control_frame, text="3. Start Web Server", command=lambda: start_web_server(app))
    btn_start_server.grid(row=0, column=0, sticky="ew", padx=(0,5))

    btn_stop_server = ttk.Button(server_control_frame, text="Stop Web Server", command=lambda: stop_web_server(app))
    btn_stop_server.grid(row=0, column=1, sticky="ew", padx=(5,0))
    btn_stop_server.config(state=tk.DISABLED) # Initially disabled, no server running

    lbl_server_status = ttk.Label(server_control_frame, text="", width=2) # Status label for server
    lbl_server_status.grid(row=0, column=2, sticky="w", padx=(5,0))


    # --- Section for Command Output ---
    output_frame = ttk.LabelFrame(webapp_tab, text="Command Output", padding="10")
    output_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10), padx=5)
    output_frame.columnconfigure(0, weight=1)
    output_frame.rowconfigure(0, weight=1)

    app.webapp_output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, font=('Consolas', 9), height=10)
    app.webapp_output_text.pack(fill=tk.BOTH, expand=False, side=tk.TOP)
    app.webapp_output_text.config(state=tk.DISABLED)

    # Store references to buttons and status labels on 'app' instance
    app.btn_install_deps = btn_install_deps
    app.btn_init_db = btn_init_db
    app.btn_start_server = btn_start_server
    app.btn_stop_server = btn_stop_server
    app.lbl_install_deps_status = lbl_install_deps_status
    app.lbl_init_db_status = lbl_init_db_status
    app.lbl_server_status = lbl_server_status

# --- Helper functions for web app setup operations ---

def _set_status_label(app, label_widget, status_char, color=None):
    """
    Helper to update status label with character and color,
    ensuring dark mode compatibility by explicitly setting background.
    """
    # Determine the correct background color based on the current dark mode state
    # We retrieve the state from app.dark_mode_enabled BooleanVar
    bg_color = "#2e2e2e" if app.dark_mode_enabled.get() else "#f0f0f0"
    
    app.master.after(0, lambda: label_widget.config(
        text=status_char, 
        foreground=color or "black", 
        background=bg_color # CRITICAL FIX: Explicitly set the background
    ))
def _append_to_output(widget, text, tag=None):
    """Appends text to the ScrolledText widget with an optional tag."""
    widget.config(state=tk.NORMAL)
    widget.insert(tk.END, text, tag)
    widget.see(tk.END)
    widget.config(state=tk.DISABLED)

# Pre-requisite check functions
def _check_prerequisite_executable(app, executable_name, output_widget, status_label=None):
    """Checks if an executable is available in PATH or sys.executable.
    Updates status_label if provided."""
    # Special handling for 'python' and 'pip' to use sys.executable
    if executable_name == 'python':
        found_path = sys.executable
    elif executable_name == 'pip':
        # For pip, we check if 'python -m pip --version' works
        try:
            subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, check=True, text=True)
            found_path = sys.executable # Indicates pip is runnable via python -m
        except (subprocess.CalledProcessError, FileNotFoundError):
            found_path = None
    else:
        found_path = shutil.which(executable_name) # Check if other executables are in PATH

    if found_path:
        app.log(f"Prerequisite check: '{executable_name}' found at '{found_path}'.", "info")
        return True
    else:
        app.log(f"Prerequisite check: '{executable_name}' NOT found. Cannot proceed.", "error")
        app.master.after(0, lambda: _append_to_output(output_widget, f"Error: '{executable_name}' command not found. Please ensure it's installed and in your system PATH.\n", 'error'))
        if status_label:
            _set_status_label(app, status_label, "❌", "red")
        app.master.after(0, lambda: messagebox.showerror("Prerequisite Missing", f"'{executable_name}' not found. Please install it or ensure it's in your system PATH."))
        return False

def _check_prerequisite_file(app, file_path_relative_to_base, output_widget, file_description="file", status_label=None):
    """Checks if a specific file exists in the base directory.
    Updates status_label if provided."""
    full_path = os.path.join(app.base_dir, file_path_relative_to_base)
    if os.path.exists(full_path):
        app.log(f"Prerequisite check: Required {file_description} '{file_path_relative_to_base}' found.", "info")
        return True
    else:
        app.log(f"Prerequisite check: Required {file_description} '{file_path_relative_to_base}' NOT found at '{full_path}'. Cannot proceed.", "error")
        app.master.after(0, lambda: _append_to_output(output_widget, f"Error: Required {file_description} '{file_path_relative_to_base}' not found. Please ensure it exists in the project root.\n", 'error'))
        if status_label:
            _set_status_label(app, status_label, "❌", "red")
        app.master.after(0, lambda: messagebox.showerror("Prerequisite Missing", f"Required {file_description} '{file_path_relative_to_base}' not found in '{app.base_dir}'."))
        return False


def _run_command_in_thread(app, command_parts, output_widget, success_msg, error_msg, control_buttons=None, status_label=None):
    """
    Runs a short-lived shell command in a separate thread and logs its output.
    Disables specified buttons during execution and re-enables them after.
    Updates an optional status_label.
    """
    if control_buttons is None:
        control_buttons = [app.btn_install_deps, app.btn_init_db]

    def _execute():
        # Disable specified buttons
        app.master.after(0, lambda: [btn.config(state=tk.DISABLED) for btn in control_buttons])
        # Set status to pending
        if status_label:
            _set_status_label(app, status_label, "⏳", "orange")

        # Clear output area and set to normal temporarily
        app.master.after(0, lambda: output_widget.config(state=tk.NORMAL))
        app.master.after(0, lambda: output_widget.delete(1.0, tk.END))
        app.master.after(0, lambda: output_widget.insert(tk.END, f"Running: {' '.join(command_parts)}\n\n"))
        app.master.after(0, lambda: output_widget.config(state=tk.DISABLED))

        try:
            app.log(f"Starting web app setup command: {' '.join(command_parts)}", "info")

            process = subprocess.Popen(
                command_parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=app.base_dir
            )

            for line in iter(process.stdout.readline, ''):
                app.master.after(0, lambda l=line: _append_to_output(output_widget, l, 'stdout'))
            for line in iter(process.stderr.readline, ''):
                app.master.after(0, lambda l=line: _append_to_output(output_widget, l, 'stderr'))

            return_code = process.wait()

            if return_code == 0:
                app.master.after(0, lambda: _append_to_output(output_widget, f"\n{success_msg}\n", 'success'))
                app.log(f"Command successful: {' '.join(command_parts)}", "success")
                if status_label:
                    _set_status_label(app, status_label, "✅", "green") # Success
            else:
                app.master.after(0, lambda: _append_to_output(output_widget, f"\n{error_msg} (Exit Code: {return_code})\n", 'error'))
                app.log(f"Command failed: {' '.join(command_parts)} (Exit Code: {return_code})", "error")
                if status_label:
                    _set_status_label(app, status_label, "❌", "red") # Failure

        except FileNotFoundError:
            app.master.after(0, lambda: _append_to_output(output_widget, f"\nError: Command '{command_parts[0]}' not found. Is it in your PATH?\n", 'error'))
            app.log(f"Error: Command '{command_parts[0]}' not found.", "error")
            if status_label:
                _set_status_label(app, status_label, "❌", "red")
        except Exception as e:
            app.master.after(0, lambda: _append_to_output(output_widget, f"\nAn unexpected error occurred: {e}\n", 'error'))
            app.log(f"An unexpected error occurred running command: {e}", "error")
            if status_label:
                _set_status_label(app, status_label, "❌", "red")
        finally:
            # Re-enable specified buttons
            app.master.after(0, lambda: [btn.config(state=tk.NORMAL) for btn in control_buttons])

    threading.Thread(target=_execute, daemon=True).start()


def install_python_dependencies(app):
    """Installs Python dependencies from requirements.txt."""
    if not hasattr(app, 'base_dir'):
        app.log("Error: base_dir attribute not found on app object. Please ensure app.base_dir is set in app.py.", "error")
        messagebox.showerror("Setup Error", "Application base directory not configured.")
        return

    # --- Pre-flight Checks for Install Dependencies ---
    if not _check_prerequisite_executable(app, "python", app.webapp_output_text, app.lbl_install_deps_status):
        return
    if not _check_prerequisite_executable(app, "pip", app.webapp_output_text, app.lbl_install_deps_status):
        return
    if not _check_prerequisite_file(app, "requirements.txt", app.webapp_output_text, "requirements file", app.lbl_install_deps_status):
        return

    command = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
    app.update_main_status("Installing Python dependencies...", "info", duration_ms=0)
    _run_command_in_thread(
        app, command, app.webapp_output_text,
        "Python dependencies installed successfully!",
        "Failed to install Python dependencies.",
        control_buttons=[app.btn_install_deps, app.btn_init_db],
        status_label=app.lbl_install_deps_status
    )

def init_migrate_database(app):
    """Initializes or migrates the web application's database."""
    if not hasattr(app, 'base_dir'):
        app.log("Error: base_dir attribute not found on app object. Please ensure app.base_dir is set in app.py.", "error")
        messagebox.showerror("Setup Error", "Application base directory not configured.")
        return

    # --- Pre-flight Checks for Init/Migrate Database ---
    if not _check_prerequisite_executable(app, "python", app.webapp_output_text, app.lbl_init_db_status):
        return
    db_script_name = "init_db.py" # Adjust this to your actual DB script name if different
    if not _check_prerequisite_file(app, db_script_name, app.webapp_output_text, "database initialization script", app.lbl_init_db_status):
        return

    command = [sys.executable, db_script_name]
    app.update_main_status("Initializing/Migrating Database...", "info", duration_ms=0)
    _run_command_in_thread(
        app, command, app.webapp_output_text,
        "Database initialized/migrated successfully!",
        "Failed to initialize/migrate database.",
        control_buttons=[app.btn_install_deps, app.btn_init_db],
        status_label=app.lbl_init_db_status
    )

def start_web_server(app):
    """Starts the web application server as a long-running process."""
    if not hasattr(app, 'base_dir'):
        app.log("Error: base_dir attribute not found on app object. Please ensure app.base_dir is set in app.py.", "error")
        messagebox.showerror("Setup Error", "Application base directory not configured.")
        return

    # Check if server is already running
    if app.web_server_process and app.web_server_process.poll() is None:
        app.log("Web server is already running.", "warning")
        messagebox.showwarning("Server Running", "Web server is already running.")
        return

    # --- Pre-flight Checks for Start Web Server ---
    if not _check_prerequisite_executable(app, "python", app.webapp_output_text, app.lbl_server_status):
        return
    webapp_script_name = "run_webapp.py" # Adjust this to your actual web app script name if different
    if not _check_prerequisite_file(app, webapp_script_name, app.webapp_output_text, "web application run script", app.lbl_server_status):
        return

    command = [sys.executable, webapp_script_name]

    app.log("Attempting to start web server...", "info")
    app.update_main_status("Starting web server...", "info", duration_ms=0)
    _set_status_label(app, app.lbl_server_status, "⏳", "orange") # Set status to pending

    app.btn_start_server.config(state=tk.DISABLED)
    app.btn_stop_server.config(state=tk.DISABLED) # Temporarily disable stop button too, until server is confirmed running

    app.webapp_output_text.config(state=tk.NORMAL)
    app.webapp_output_text.delete(1.0, tk.END)
    app.webapp_output_text.insert(tk.END, f"Starting server: {' '.join(command)}\n\n", 'info')
    app.webapp_output_text.config(state=tk.DISABLED)

    def _start_server_thread():
        try:
            app.web_server_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=app.base_dir
            )

            app.log("Web server process initiated. Check 'Command Output' for logs.", "info")
            app.master.after(0, lambda: _append_to_output(app.webapp_output_text, "Server process started. Output:\n", 'info'))

            threading.Thread(target=_read_process_output, args=(app.web_server_process.stdout, app.webapp_output_text, 'stdout', app), daemon=True).start()
            threading.Thread(target=_read_process_output, args=(app.web_server_process.stderr, app.webapp_output_text, 'stderr', app), daemon=True).start()

            _set_status_label(app, app.lbl_server_status, "🟢", "green") # Server initiated successfully (running)
            app.update_main_status("Web server started successfully!", "success")

            threading.Thread(target=_monitor_server_process_termination, args=(app,), daemon=True).start()

            app.master.after(0, app.btn_start_server.config, {'state': tk.DISABLED})
            app.master.after(0, app.btn_stop_server.config, {'state': tk.NORMAL})

        except FileNotFoundError:
            app.log(f"Error: Command '{command[0]}' not found. Is it in your PATH?", "error")
            app.master.after(0, lambda: _append_to_output(app.webapp_output_text, f"\nError: Command '{command[0]}' not found. Is it in your PATH?\n", 'error'))
            app.master.after(0, app.btn_start_server.config, {'state': tk.NORMAL})
            app.master.after(0, app.btn_stop_server.config, {'state': tk.DISABLED})
            _set_status_label(app, app.lbl_server_status, "❌", "red")
            app.update_main_status("Server failed to start: Command not found.", "error")
        except Exception as e:
            app.log(f"An unexpected error occurred trying to start web server: {e}", "error")
            app.master.after(0, lambda: _append_to_output(app.webapp_output_text, f"\nAn unexpected error occurred: {e}\n", 'error'))
            app.master.after(0, app.btn_start_server.config, {'state': tk.NORMAL})
            app.master.after(0, app.btn_stop_server.config, {'state': tk.DISABLED})
            _set_status_label(app, app.lbl_server_status, "❌", "red")
            app.update_main_status(f"Server failed to start: {e}", "error")
        finally:
            if not (app.web_server_process and app.web_server_process.poll() is None):
                 app.master.after(0, app.btn_start_server.config, {'state': tk.NORMAL})
                 app.master.after(0, app.btn_stop_server.config, {'state': tk.DISABLED})

    threading.Thread(target=_start_server_thread, daemon=True).start()

def _read_process_output(pipe, output_widget, tag, app):
    """Reads output from a process pipe and appends to the widget in the main thread."""
    for line in iter(pipe.readline, ''):
        app.master.after(0, lambda l=line: _append_to_output(output_widget, l, tag))
    pipe.close()

def _monitor_server_process_termination(app):
    """Monitors the web server process and updates button states and status on termination."""
    if app.web_server_process:
        return_code = app.web_server_process.wait() # Wait for process to terminate
        app.log(f"Web server process terminated with exit code: {return_code}", "info")
        app.master.after(0, lambda: _append_to_output(app.webapp_output_text, f"\nWeb server stopped (Exit Code: {return_code}).\n", 'info'))
        app.web_server_process = None # Clear the process reference
        app.master.after(0, app.btn_start_server.config, {'state': tk.NORMAL})
        app.master.after(0, app.btn_stop_server.config, {'state': tk.DISABLED})
        _set_status_label(app, app.lbl_server_status, "⚪", "gray") # Server stopped (neutral/inactive)

def stop_web_server(app):
    """Stops the running web application server."""
    if not app.web_server_process or app.web_server_process.poll() is not None:
        messagebox.showinfo("No Server", "Web server is not running or already stopped.")
        _set_status_label(app, app.lbl_server_status, "⚪", "gray") # Ensure neutral status
        app.btn_start_server.config(state=tk.NORMAL) # Ensure start button is enabled
        app.btn_stop_server.config(state=tk.DISABLED) # Ensure stop button is disabled
        return

    app.log("Attempting to stop web server...", "info")
    app.update_main_status("Stopping web server...", "info", duration_ms=0)
    _set_status_label(app, app.lbl_server_status, "⏳", "orange") # Set status to pending while stopping
    app.btn_start_server.config(state=tk.DISABLED)
    app.btn_stop_server.config(state=tk.DISABLED) # Disable both while stopping

    def _stop_server_thread():
        try:
            app.web_server_process.terminate() # Send SIGTERM (graceful shutdown)
            app.web_server_process.wait(timeout=5) # Give it 5 seconds to terminate gracefully
            if app.web_server_process.poll() is None: # Still running after timeout?
                app.web_server_process.kill() # Force kill (SIGKILL)
                app.log("Web server did not terminate gracefully, forced kill.", "warning")
            app.log("Web server stopped successfully.", "success")
            app.update_main_status("Web server stopped successfully.", "success")
        except Exception as e:
            app.log(f"Error stopping web server: {e}", "error")
            app.update_main_status(f"Failed to stop web server: {e}", "error")
            messagebox.showerror("Server Control Error", f"Could not stop server: {e}")
        finally:
            # The _monitor_server_process_termination thread will detect the actual exit and update UI.
            # No explicit button/status updates here, as monitor thread handles post-exit states.
            pass

    threading.Thread(target=_stop_server_thread, daemon=True).start()