# run_webapp.py (in your project root)
import time
import sys

print("Starting web application server simulation...")
print("Web server is running at http://127.0.0.1:5000/ (simulated)")
sys.stdout.flush() # Ensure output is flushed, especially for subprocess
try:
    while True:
        # print("Server heartbeat...", file=sys.stderr) # Optional: for more output
        time.sleep(1) # Keep alive
except KeyboardInterrupt:
    print("\nServer received Ctrl+C. Shutting down gracefully.", file=sys.stderr)
    sys.stdout.flush()
except Exception as e:
    print(f"\nServer encountered error: {e}", file=sys.stderr)
    sys.stdout.flush()
finally:
    print("Web server process exiting.", file=sys.stderr)
    sys.stdout.flush()