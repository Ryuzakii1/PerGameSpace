import tkinter as tk
from tkinter import messagebox

try:
    root = tk.Tk()
    root.title("Tkinter Test")
    root.geometry("300x200")
    
    label = tk.Label(root, text="If you see this, Tkinter works!")
    label.pack(pady=20)
    
    button = tk.Button(root, text="Click Me", command=lambda: messagebox.showinfo("Info", "Button Clicked!"))
    button.pack()

    print("Tkinter window should be visible now.")
    root.mainloop()
    print("Tkinter window closed.")

except Exception as e:
    print(f"An error occurred: {e}")
    # Attempt to show a messagebox even if mainloop fails, might not work if Tkinter is broken
    try:
        messagebox.showerror("Tkinter Error", f"Failed to launch Tkinter window: {e}")
    except:
        pass # If messagebox also fails, just print to console
