import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk
import os
from pathlib import Path
import DuplicateDetector as dd
import shutil

# Global Variables
image_files = []
current_index = 0
EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico")

def load_folder(file_path):
    """Helper function to load all images in the same folder as the selected image."""
    global image_files, current_index
    file_path = os.path.normpath(file_path)
    folder = os.path.dirname(file_path)

    image_files = sorted(
        os.path.normpath(entry.path)
        for entry in os.scandir(folder)
        if entry.is_file() and entry.name.lower().endswith(EXTS)
    )
    current_index = image_files.index(file_path)

def open_image():
    """Open a file dialog to select an image, then loads all images in the same folder."""
    global image_files, current_index
    file_path = filedialog.askopenfilename(
        title="Open Image File",
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.ico")]
    )
    if not file_path:
        return
    
    load_folder(file_path)
    display_image(image_files[current_index])

def display_image(file_path):
    image = Image.open(file_path)
    
    # Scale down to half size
    display_w = image.width // 2
    display_h = image.height // 2
    image = image.resize((display_w, display_h), Image.LANCZOS)
    
    photo = ImageTk.PhotoImage(image)
    image_label.config(image=photo)
    image_label.photo = photo

    root.geometry(f"{display_w + 40}x{display_h + 120}")
    status_label.config(text=f"Image loaded: {file_path}")

def next_image():
    """Display the next image in the folder."""
    global current_index
    if image_files:
        current_index = (current_index + 1) % len(image_files)
        display_image(image_files[current_index])

def prev_image():
    """Display the previous image in the folder."""
    global current_index
    if image_files:
        current_index = (current_index - 1) % len(image_files)
        display_image(image_files[current_index])

def unique_dest(folder, filename):
    """Helper funciton to generate a unique destination path if a file with the same name already exists in the target folder."""
    dest = os.path.join(folder, filename)
    if not os.path.exists(dest):
        return dest
    name, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(folder, f"{name}_{counter}{ext}")
        counter += 1
    return dest

def check_duplicate():
    """Check for duplicates of the currently displayed image in the same folder and move them to a /Duplicates subfolder."""
    if not image_files:
        status_label.config(text="No images loaded.")
        return
    
    current_image = image_files[current_index]
    folder = os.path.dirname(current_image)
    dupes_folder = os.path.join(folder, "Duplicates")
    os.makedirs(dupes_folder, exist_ok=True)

    duplicates = []

    for i in range(len(image_files)):
        img = image_files[i]
        if i != current_index:
            is_dupe, reason = dd.duplicate_check(current_image, img)
            if is_dupe:
                duplicates.append((img, reason))

    if duplicates:
        for img, reason in duplicates:
            dest = unique_dest(dupes_folder, os.path.basename(img))
            shutil.move(img, dest)
        status_label.config(text=f"Moved {len(duplicates)} duplicate(s) to /Duplicates")
    else:
        status_label.config(text="No duplicates found.")

    load_folder(current_image)


root = tk.Tk()
root.title("Simple Image Viewer")

open_button = tk.Button(root, text="Open Image", command=open_image)
open_button.pack(padx=20, pady=10)

status_label = tk.Label(root, text="", padx=20, pady=10)
status_label.pack(side=tk.BOTTOM)

nav_frame = tk.Frame(root)
nav_frame.pack(side=tk.BOTTOM, pady=5)

prev_button = tk.Button(nav_frame, text="← Back", command=prev_image)
prev_button.pack(side=tk.LEFT, padx=10)

next_button = tk.Button(nav_frame, text="Next →", command=next_image)
next_button.pack(side=tk.LEFT, padx=10)

dup_button = tk.Button(nav_frame, text="Check Duplicates", command=check_duplicate)
dup_button.pack(side=tk.LEFT, padx=10)

# Image label packed LAST so it fills remaining space
image_label = tk.Label(root)
image_label.pack(padx=20, pady=20)
root.mainloop()
