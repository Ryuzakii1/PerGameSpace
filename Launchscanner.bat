@echo off
REM Change to the directory where scanner_gui.py is located
cd /d "%~dp0"
REM Run the Python script using pythonw.exe to suppress the console window
start "" pythonw scanner_gui.py