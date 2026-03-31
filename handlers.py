import os
import shutil
from bisect import bisect_left
from tkinter import Button, Entry, Label, Toplevel, filedialog, messagebox

from PIL import Image, ImageEnhance, ImageFilter, ImageTk
from PIL.ExifTags import TAGS
from send2trash import send2trash
import datetime

from DuplicateDetector import DuplicateDetectorMain
from autolabeler import CLIPLabeler

class ImageFunctions:
    def __init__(self, root, image_label, status_label, settings):
        self.root = root
        self.image_label = image_label
        self.status_label = status_label
        self.apply_settings(settings)
        self.image_files = []
        self.current_index = 0
        self.original_image = None
        self.stack_undo = []
        self.stack_redo = []
        self.current_rotation = 0
        self.current_filter = None
        self.duplicate_detector = DuplicateDetectorMain()
        self.autolabeler = CLIPLabeler()

    # A helper function to apply settings from the settings manager to the instance variables
    def apply_settings(self, settings):
        """Apply a settings dict to the instance."""
        self.confirm_deletes = settings.get("confirm_deletes", True)
        self.fast_delete = settings.get("fast_delete", False)
        self.labels = settings.get("image_labels", [])

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
        self.status_label.config(text=f"{os.path.basename(file_path)}")

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

    def navigate(self, direction):
        """Display the next or previous image in the folder. Pass 1 for next, -1 for prev."""
        if self.image_files:
            self.current_index = (self.current_index + direction) % len(self.image_files)
            self.display_image(self.image_files[self.current_index])
        
    def delete_image(self):
        """Sends current image to the recycle bin using send2trash, then updates the image list and display."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return

        file_to_delete = self.image_files[self.current_index]

        if not self.fast_delete and self.confirm_deletes:
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
        
        loading = Toplevel(self.root)
        loading.title("Please Wait")
        Label(loading, text="Sorting duplicates...", padx=20, pady=20).pack()
        loading.update()

        current_image, duplicates = self.duplicate_detector.find_duplicates(self.image_files, self.current_index)
        folder = os.path.dirname(current_image)

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
                raw_size = os.path.getsize(file_path)

                if raw_size < 1024:
                    file_size = f"{raw_size} bytes"
                elif raw_size < 1024 ** 2:
                    file_size = f"{raw_size / 1024:.2f} KB"
                elif raw_size < 1024 ** 3:
                    file_size = f"{raw_size / 1024 ** 2:.2f} MB"
                else:
                    file_size = f"{raw_size / 1024 ** 3:.2f} GB"

                human = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%B %d, %Y %I:%M %p")

                exif_data = img.getexif()
                camera_make = "Unknown"
                camera_model = "Unknown"
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == "Make":
                        camera_make = value
                    elif tag == "Model":
                        camera_model = value

            messagebox.showinfo("Metadata", (
                f"Dimensions: {width} x {height}\n"
                f"File Size: {file_size}\n"
                f"Created: {human}\n"
                f"Camera Make: {camera_make}\n"
                f"Camera Model: {camera_model}\n"
                f"Path: {file_path}"
            ))

        except Exception:
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

    def apply_filter(self, filter_type, push_undo=True):
        if not self.image_files:
            return

        if push_undo:
            self.stack_undo.append(("filter", self.current_filter))

        self.current_filter = None if filter_type == "reset" else filter_type
        self._render_image(self._get_edited_image())

    def _get_edited_image(self):
        image = Image.open(self.image_files[self.current_index])
        if self.current_rotation:
            image = image.rotate(self.current_rotation, expand=True)
        if self.current_filter:
            if self.current_filter == "grayscale":
                image = image.convert("L").convert("RGB")
            elif self.current_filter == "blur":
                image = image.filter(ImageFilter.BLUR)
            elif self.current_filter == "sharpen":
                image = image.filter(ImageFilter.SHARPEN)
            elif self.current_filter == "brightness":
                image = ImageEnhance.Brightness(image).enhance(1.5)
            elif self.current_filter == "contour":
                image = image.filter(ImageFilter.CONTOUR)
        return image

    def _render_image(self, image=None):
        if image is None:
            image = Image.open(self.image_files[self.current_index])
        
        self.original_image = image
        self.resize_image()
    
    def rotate_image(self, angle, push_undo=True, absolute=True):
        if not self.image_files:
            return
        if push_undo:
            self.stack_undo.append(("rotate", self.current_rotation))
        self.current_rotation = angle if absolute else (self.current_rotation + angle) % 360
        self._render_image(self._get_edited_image())
    
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
    
    def undo(self):
        if not self.stack_undo:
            self.status_label.config(text="Nothing to undo.")
            return

        last_action, value = self.stack_undo.pop()

        if last_action == "rotate":
            self.stack_redo.append(("rotate", self.current_rotation))
            self.current_rotation = value
            self.status_label.config(text=f"Undid rotation — back to {value}°.")
        elif last_action == "filter":
            self.stack_redo.append(("filter", self.current_filter))
            self.current_filter = value
            self.status_label.config(text="Undid filter.")
        else:
            self.status_label.config(text="Unknown action to undo.")
            return

        self._render_image(self._get_edited_image())
    
    def redo(self):
        """Redo the last undone transformation."""
        if not self.stack_redo:
            self.status_label.config(text="Nothing to redo.")
            return
        
        action, value = self.stack_redo.pop()
        
        if action == "rotate":
            self.stack_undo.append(("rotate", self.current_rotation))
            self.current_rotation = value
            self.status_label.config(text=f"Redid rotation of {value} degrees.")
        elif action == "filter":
            self.stack_undo.append(("filter", self.current_filter))
            self.current_filter = value
            self.status_label.config(text="Redid filter.")
        else:
            self.status_label.config(text="Unknown action to redo.")
            return

        self._render_image(self._get_edited_image())

    def fast_delete_func(self):
        """Toggle fast delete mode — left arrow deletes, right arrow moves."""
        self.root.bind("<Left>", lambda e: self.navigate(-1))
        self.root.bind("<Right>", lambda e: self.navigate(1))
        if self.fast_delete:
            self.root.bind("<Down>", lambda e: self.delete_image())
            self.root.bind("<Up>", self.fast_delete_up)
            self.status_label.config(text="Fast delete mode ON")
        else:
            self.root.unbind("<Down>")
            self.root.unbind("<Up>")
            self.status_label.config(text="Fast delete mode OFF")

    def fast_delete_up(self, event):
        """Up arrow — move current image to Favs folder."""
        if not self.image_files:
            return

        file = self.image_files[self.current_index]
        favs_folder = os.path.join(os.path.dirname(file), "Favs")
        os.makedirs(favs_folder, exist_ok=True)
        shutil.move(file, self.unique_dest(favs_folder, os.path.basename(file)))
        self.image_files.pop(self.current_index)

        if self.image_files:
            self.current_index = min(self.current_index, len(self.image_files) - 1)
            self._render_image()
        else:
            self.original_image = None
            self.image_label.config(image="")
            self.status_label.config(text="No images left.")

    def _sort_by_clip(self, labels):
        """Core sorting logic — moves all images into subfolders based on CLIP labels."""
        folder = os.path.dirname(self.image_files[0])
        count = len(self.image_files)
        text_tokens = self.autolabeler.initialize_clip_labels(labels)

        for subfolder in set(labels):
            os.makedirs(os.path.join(folder, subfolder), exist_ok=True)

        for file in self.image_files:
            label, _ = self.autolabeler.get_clip_label(file, labels, text_tokens)
            labeled_folder = os.path.join(folder, label)
            shutil.move(file, self.unique_dest(labeled_folder, os.path.basename(file)))

        self.image_files.clear()
        self.current_index = 0
        self.original_image = None
        self.image_label.config(image="")
        self.status_label.config(text=f"Sorted {count} images into {len(labels)} label(s).")

    def auto_sort_images(self):
        """Sort images into subfolders based on user-defined CLIP labels."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return
        if not self.labels:
            self.status_label.config(text="No labels defined. Please add labels with Manage Labels.")
            return
        self._sort_by_clip(self.labels)

    def auto_sort_nsfw(self):
        """Sort images into NSFW and SFW subfolders."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return
        self._sort_by_clip(["NSFW photo", "SFW photo"])

