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

# Initialize Handlers
image_functions = ImageFunctions(root, image_label, status_label)

# Menu Bar
menubar = tk.Menu(root)
root.config(menu=menubar)

# File menu
file_menu = tk.Menu(menubar, tearoff=0)
menubar.add_cascade(label="File", menu=file_menu)
file_menu.add_command(label="Open Image", command=image_functions.open_image)
file_menu.add_separator()
file_menu.add_command(label="Save As", command=image_functions.save_image)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)

# Edit Menu
edit_menu = tk.Menu(menubar, tearoff=0)
menubar.add_cascade(label="Edit", menu=edit_menu)
edit_menu.add_command(label="Rotate Image", command=image_functions.rotate_custom)

# Filter Menu
filter_menu = tk.Menu(menubar, tearoff=0)
menubar.add_cascade(label="Filters", menu=filter_menu)
filter_menu.add_command(label="Grayscale", command=lambda: image_functions.apply_filter("grayscale"))
filter_menu.add_command(label="Blur", command=lambda: image_functions.apply_filter("blur"))
filter_menu.add_command(label="Sharpen", command=lambda: image_functions.apply_filter("sharpen"))
filter_menu.add_command(label="Brightness", command=lambda: image_functions.apply_filter("brightness"))
filter_menu.add_command(label="Contour", command=lambda: image_functions.apply_filter("contour"))
filter_menu.add_command(label="Reset", command=lambda: image_functions.apply_filter("reset"))

# Image menu
image_menu = tk.Menu(menubar, tearoff=0)
menubar.add_cascade(label="Image", menu=image_menu)
image_menu.add_command(label="Information", command=image_functions.get_metadata)

# Advanced menu
advanced_menu = tk.Menu(menubar, tearoff=0)
menubar.add_cascade(label="Advanced", menu=advanced_menu)
advanced_menu.add_command(label="Sort Duplicates", command=image_functions.check_duplicate)
advanced_menu.add_separator()
advanced_menu.add_checkbutton(label="Fast Delete Mode", command=image_functions.fast_delete_toggle)

# Buttons
nav_frame = tk.Frame(root)
nav_frame.grid(row=2, column=0, pady=5)

prev_button = tk.Button(nav_frame, text="← Back", command=image_functions.prev_image)
prev_button.pack(side=tk.LEFT, padx=10)

next_button = tk.Button(nav_frame, text="Next →", command=image_functions.next_image)
next_button.pack(side=tk.LEFT, padx=10)

delete_button = tk.Button(nav_frame, text="Delete Image", command=image_functions.delete_image)
delete_button.pack(side=tk.LEFT, padx=10)

root.bind("<Configure>", image_functions.resize_image)

root.mainloop()
