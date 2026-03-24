from tkinter import filedialog, messagebox, Toplevel, Label
from PIL import Image, ImageTk
import os
import DuplicateDetector as dd
import shutil
import send2trash

class ImageFunctions:
    def __init__(self, root, image_label, status_label):
        self.root = root
        self.image_label = image_label
        self.status_label = status_label
        self.image_files = []
        self.current_index = 0
        self.EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico")
    
    def load_folder(self, file_path):
        """Helper function to load all images in the same folder as the selected image."""
        file_path = os.path.normpath(file_path)
        folder = os.path.dirname(file_path)

        with os.scandir(folder) as entries:
            self.image_files = sorted(
                os.path.normpath(entry.path)
                for entry in entries
                if entry.is_file() and entry.name.lower().endswith(self.EXTS)
            )
        self.current_index = self.image_files.index(file_path)
    
    def open_image(self):
        """Open a file dialog to select an image, then loads all images in the same folder."""
        file_path = filedialog.askopenfilename(
            title="Open Image File",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.ico")]
        )
        if not file_path:
            return
        
        self.load_folder(file_path)
        self.display_image(self.image_files[self.current_index])
    
    def display_image(self, file_path):
        """Load the image and trigger a resize based on window size."""
        self.original_image = Image.open(file_path)
        self.current_path = file_path

        # Force an initial resize
        self.resize_image()

        self.status_label.config(text=f"Image loaded: {file_path}")

    def resize_image(self, event=None):
        """Resize the currently displayed image to fit within the window while preserving aspect ratio."""
        if not hasattr(self, "original_image"):
            return

        # Get available space inside the window
        window_w = self.root.winfo_width()
        window_h = self.root.winfo_height()

        if window_w < 200 or window_h < 200:
            return

        # Reserve space for status + buttons
        reserved_h = 100
        available_h = max(50, window_h - reserved_h)

        # Compute scale while preserving aspect ratio
        img = self.original_image.copy()
        img.thumbnail((window_w - 40, available_h), Image.LANCZOS)

        # Display resized image
        photo = ImageTk.PhotoImage(img)
        self.image_label.config(image=photo)
        self.image_label.photo = photo


    def next_image(self):
        """Display the next image in the folder."""
        if self.image_files:
            self.current_index = (self.current_index + 1) % len(self.image_files)
            self.display_image(self.image_files[self.current_index])
    
    def prev_image(self):
        """Display the previous image in the folder."""
        if self.image_files:
            self.current_index = (self.current_index - 1) % len(self.image_files)
            self.display_image(self.image_files[self.current_index])
        
    def delete_image(self):
        """Sends current image to the recycle bin using send2trash, then updates the image list and display."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return
        
        file_to_delete = self.image_files[self.current_index]
        confirm = messagebox.askyesno("Delete Image", f"Are you sure you want to delete {os.path.basename(file_to_delete)}?")
        
        if confirm:
            send2trash.send2trash(file_to_delete)
            
            # Remove from list and clamp index before reloading
            self.image_files.pop(self.current_index)
            if self.image_files:
                self.current_index = min(self.current_index, len(self.image_files) - 1)
                self.display_image(self.image_files[self.current_index])
                self.status_label.config(text=f"Trashed: {os.path.basename(file_to_delete)}")
            else:
                self.image_label.config(image="")
                self.status_label.config(text="No images left in folder.")

    def unique_dest(self, folder, filename):
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

    def check_duplicate(self):
        """Check for duplicates of the currently displayed image in the same folder and move them to a /Duplicates subfolder."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return
        
        current_image = self.image_files[self.current_index]
        folder = os.path.dirname(current_image)

        duplicates = []

        loading = Toplevel(self.root)
        loading.title("Please Wait")
        Label(loading, text="Sorting duplicates...", padx=20, pady=20).pack()
        loading.update()

        for i in range(len(self.image_files)):
            img = self.image_files[i]
            if i != self.current_index:
                is_dupe, reason = dd.duplicate_check(current_image, img)
                if is_dupe:
                    duplicates.append((img, reason))

        if duplicates:
            dupes_folder = os.path.join(folder, "Duplicates")
            os.makedirs(dupes_folder, exist_ok=True)
            for img, reason in duplicates:
                dest = self.unique_dest(dupes_folder, os.path.basename(img))
                shutil.move(img, dest)
            
            self.status_label.config(text=f"Moved {len(duplicates)} duplicate(s) to /Duplicates")
        else:
            self.status_label.config(text="No duplicates found.")

        loading.destroy()
        self.load_folder(current_image)
    
    def get_metadata(self):
        """Extract metadata from the image file, such as dimensions and file size."""
        if not self.image_files:
            return "No image loaded."
        file_path = self.image_files[self.current_index]
        try:
            with Image.open(file_path) as img:
                width, height = img.size
            file_size = os.path.getsize(file_path)
            return f"{width}x{height}, {file_size // 1024} KB"
        except Exception as e:
            return "Metadata unavailable"
    
    def save_image(self):
        """Open a file dialog to save the currently displayed image to a new location."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Save Image As",
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg;*.jpeg"), ("All files", "*.*")]
        )
        if not file_path:
            return
        
        try:
            self.original_image.save(file_path)
            self.status_label.config(text=f"Image saved as: {file_path}")
        except Exception as e:
            self.status_label.config(text=f"Error saving image: {e}")

