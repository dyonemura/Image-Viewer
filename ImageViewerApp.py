import tkinter as tk
from handlers import ImageFunctions

root = tk.Tk()
root.title("Simple Image Viewer")

# Use grid instead of pack
root.rowconfigure(0, weight=1)   # image row expands
root.rowconfigure(1, weight=0)   # buttons row stays fixed
root.columnconfigure(0, weight=1)

# Image
image_label = tk.Label(root)
image_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

status_label = tk.Label(root, text="", padx=20, pady=10)
status_label.grid(row=1, column=0, sticky="ew")

image_functions = ImageFunctions(root, image_label, status_label)

# Buttons
nav_frame = tk.Frame(root)
nav_frame.grid(row=2, column=0, pady=5)

open_button = tk.Button(nav_frame, text="Open Image", command=image_functions.open_image)
open_button.pack(side=tk.LEFT, padx=10)

prev_button = tk.Button(nav_frame, text="← Back", command=image_functions.prev_image)
prev_button.pack(side=tk.LEFT, padx=10)

next_button = tk.Button(nav_frame, text="Next →", command=image_functions.next_image)
next_button.pack(side=tk.LEFT, padx=10)

dup_button = tk.Button(nav_frame, text="Check Duplicates", command=image_functions.check_duplicate)
dup_button.pack(side=tk.LEFT, padx=10)

delete_button = tk.Button(nav_frame, text="Delete Image", command=image_functions.delete_image)
delete_button.pack(side=tk.LEFT, padx=10)

metadata_button = tk.Button(nav_frame, text="i", command=image_functions.get_metadata)
metadata_button.pack(side=tk.LEFT, padx=10)

save_button = tk.Button(nav_frame, text="Save As", command=image_functions.save_image)
save_button.pack(side=tk.LEFT, padx=10)

root.bind("<Configure>", image_functions.resize_image)


root.mainloop()
