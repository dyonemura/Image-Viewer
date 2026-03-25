import os
import shutil
from bisect import bisect_left
from tkinter import Button, Entry, Label, Toplevel, filedialog, messagebox

from PIL import Image, ImageEnhance, ImageFilter, ImageTk
from PIL.ExifTags import TAGS
from send2trash import send2trash

from DuplicateDetector import duplicate_check

class ImageFunctions:
    def __init__(self, root, image_label, status_label):
        self.root = root
        self.image_label = image_label
        self.status_label = status_label
        self.image_files = []
        self.current_index = 0
        self.original_image = None
        self.fast_delete = False
        self.dupe_recycle_bin = False

    def load_folder(self, file_path):
        """Load all images in the same folder as the selected image, using bisect for efficient indexing."""
        file_path = os.path.normpath(file_path)
        folder = os.path.dirname(file_path)
        exts = frozenset((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico"))

        with os.scandir(folder) as entries:
            self.image_files = sorted(
                entry.path
                for entry in entries
                if entry.is_file(follow_symlinks=False)
                and os.path.splitext(entry.name)[1].lower() in exts
            )

        self.current_index = bisect_left(self.image_files, file_path)

        if self.current_index >= len(self.image_files) or self.image_files[self.current_index] != file_path:
            raise ValueError(f"File not found in folder: {file_path}")
    
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
        self.resize_image()
        self.status_label.config(text=f"Image loaded: {os.path.basename(file_path)}")

    def resize_image(self, event=None):
        """Resize the currently displayed image to fit within the window while preserving aspect ratio."""
        if self.original_image is None:
            return

        window_w = self.root.winfo_width()
        window_h = self.root.winfo_height()

        if window_w < 200 or window_h < 200:
            return

        available_h = max(50, window_h - 100)
        target_w = window_w - 40

        orig_w, orig_h = self.original_image.size
        scale = min(target_w / orig_w, available_h / orig_h)

        if scale >= 1.0:
            img = self.original_image.copy()
        else:
            new_size = (int(orig_w * scale), int(orig_h * scale))
            img = self.original_image.resize(new_size, Image.LANCZOS)

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
        if not messagebox.askyesno("Delete Image", f"Are you sure you want to delete {os.path.basename(file_to_delete)}?"):
            return

        send2trash(file_to_delete)
        self.image_files.pop(self.current_index)

        if self.image_files:
            self.current_index = min(self.current_index, len(self.image_files) - 1)
            self.display_image(self.image_files[self.current_index])
            self.status_label.config(text=f"Trashed: {os.path.basename(file_to_delete)}")
        else:
            self.original_image = None
            self.image_label.config(image="")
            self.status_label.config(text="No images left in folder.")

    def unique_dest(self, folder, filename):
        """Helper function to generate a unique destination path if a file with the same name already exists in the target folder."""
        dest = os.path.join(folder, filename)
        if not os.path.exists(dest):
            return dest
        name, ext = os.path.splitext(filename)
        counter = 1
        while True:
            dest = os.path.join(folder, f"{name}_{counter}{ext}")
            if not os.path.exists(dest):
                return dest
            counter += 1

    def check_duplicate(self):
        """Check for duplicates of the currently displayed image in the same folder and move them to a /Duplicates subfolder."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return

        current_image = self.image_files[self.current_index]
        folder = os.path.dirname(current_image)

        loading = Toplevel(self.root)
        loading.title("Please Wait")
        Label(loading, text="Sorting duplicates...", padx=20, pady=20).pack()
        loading.update()

        duplicates = []

        for i, img in enumerate(self.image_files):
            if i != self.current_index:
                is_dupe, reason = duplicate_check(current_image, img)
                if is_dupe:
                    duplicates.append((img, reason))

        if duplicates:
            dupes_folder = os.path.join(folder, "Duplicates")
            os.makedirs(dupes_folder, exist_ok=True)
            for img, reason in duplicates:
                print(reason)
                shutil.move(img, self.unique_dest(dupes_folder, os.path.basename(img)))
            self.status_label.config(text=f"Moved {len(duplicates)} duplicate(s) to /Duplicates")
        else:
            self.status_label.config(text="No duplicates found.")

        loading.destroy()
        self.load_folder(current_image)

    def get_metadata(self):
        """Extract metadata including EXIF (creation date, camera info, bit depth)."""
        if not self.image_files:
            messagebox.showinfo("Metadata", "No image loaded.")
            return

        file_path = self.image_files[self.current_index]

        try:
            with Image.open(file_path) as img:
                width, height = img.size
                file_size = os.path.getsize(file_path)

                # --- EXIF extraction ---
                exif_data = img.getexif()
                readable_exif = {}

                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    readable_exif[tag] = value

                # Common useful EXIF fields
                creation_time = readable_exif.get("DateTimeOriginal", "Unknown")
                camera_model = readable_exif.get("Model", "Unknown")
                camera_make = readable_exif.get("Make", "Unknown")
                print(readable_exif)
                
                info = (
                    f"Dimensions: {width} x {height}\n"
                    f"File Size: {file_size // 1024} KB\n"
                    f"Created: {creation_time}\n"
                    f"Camera Make: {camera_make}\n"
                    f"Camera Model: {camera_model}\n"
                    f"Path: {file_path}"
                )

                messagebox.showinfo("Metadata", info)

        except Exception as e:
            messagebox.showinfo("Metadata", "Metadata unavailable.")

    
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

    def apply_filter(self, filter_type):
        if not self.image_files:
            return
        if filter_type == "reset":
            self._render_image()
            return

        image = Image.open(self.image_files[self.current_index])

        if filter_type == "grayscale":
            image = image.convert("L").convert("RGB")
        elif filter_type == "blur":
            image = image.filter(ImageFilter.BLUR)
        elif filter_type == "sharpen":
            image = image.filter(ImageFilter.SHARPEN)
        elif filter_type == "brightness":
            image = ImageEnhance.Brightness(image).enhance(1.5)
        elif filter_type == "contour":
            image = image.filter(ImageFilter.CONTOUR)

        self._render_image(image)

    def _render_image(self, image=None):
        if image is None:
            image = Image.open(self.image_files[self.current_index])
        
        self.original_image = image
        self.resize_image()
    
    def rotate_image(self, angle):
        """Rotate the current image by the specified angle and re-render it."""
        if not self.image_files:
            return
        
        image = Image.open(self.image_files[self.current_index])
        rotated = image.rotate(angle, expand=True)
        self._render_image(rotated)
    
    def rotate_custom(self):
        """Open a dialog to enter a custom rotation angle, then rotate the image accordingly."""
        if not self.image_files:
            return

        dialog = Toplevel(self.root)
        dialog.title("Rotate Image")
        dialog.geometry("250x140")
        dialog.resizable(False, False)

        Label(dialog, text="Enter angle (0-360):").pack(pady=10)

        def validate(P):
            return P.isdigit() or P == ""
        
        vcmd = (dialog.register(validate), "%P")
        angle_entry = Entry(dialog, validate="key", validatecommand=vcmd)
        angle_entry.pack()
        angle_entry.focus()

        error_label = Label(dialog, text="", fg="red")
        error_label.pack()

        def apply():
            angle = int(angle_entry.get()) if angle_entry.get() else 0
            if not 0 <= angle <= 360:
                error_label.config(text="Angle must be between 0 and 360.")
                return
            dialog.destroy()
            self.rotate_image(angle)

        dialog.bind("<Return>", lambda e: apply())
        Button(dialog, text="Rotate", command=apply).pack(pady=5)

    def fast_delete_toggle(self):
        """Toggle fast delete mode, which allows using left/right arrow keys to quickly delete or move images without confirmation."""
        self.fast_delete = not self.fast_delete

        if self.fast_delete:
            self.root.bind("<Left>", self.fast_delete_left)
            self.root.bind("<Right>", self.fast_delete_right)
            self.status_label.config(text="Fast delete mode ON — ← Delete  |  → Move")
        else:
            self.root.unbind("<Left>")
            self.root.unbind("<Right>")
            self.status_label.config(text="Fast delete mode OFF")

    def fast_delete_left(self, event):
        """Binds left arrow to send the current image to the recycle bin without confirmation."""
        if not self.image_files:
            return
        file = self.image_files[self.current_index]
        send2trash(file)
        self.image_files.pop(self.current_index)
        if self.image_files:
            self.current_index = min(self.current_index, len(self.image_files) - 1)
            self._render_image()
        else:
            self.image_label.config(image="")
            self.status_label.config(text="No images left.")

    def fast_delete_right(self, event):
        """Right arrow — move to Favs folder."""
        if not self.image_files:
            return
        file = self.image_files[self.current_index]
        favs_folder = os.path.join(os.path.dirname(file), "Favs")
        os.makedirs(favs_folder, exist_ok=True)
        dest = self.unique_dest(favs_folder, os.path.basename(file))
        shutil.move(file, dest)
        self.image_files.pop(self.current_index)
        if self.image_files:
            self.current_index = min(self.current_index, len(self.image_files) - 1)
            self._render_image()
        else:
            self.image_label.config(image="")
            self.status_label.config(text="No images left.")