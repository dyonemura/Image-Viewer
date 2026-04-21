import datetime
import os
import shutil
import tkinter as tk
from bisect import bisect_left
from tkinter import Button, Entry, Label, Toplevel, filedialog, messagebox

from PIL import Image, ImageEnhance, ImageFilter, ImageTk
from PIL.ExifTags import TAGS
from send2trash import send2trash

from DuplicateDetector import DuplicateDetectorMain
from autolabeler import CLIPLabeler
from Crop import CropOverlay
from MassDeleteDialog import MassDeleteDialog


class ImageFunctions:
    __slots__ = ("root", "image_canvas", "status_label", "confirm_deletes", "fast_delete",
                  "labels", "image_files", "current_index", "original_image", "stack_undo",
                  "stack_redo", "current_rotation", "current_filter", "duplicate_detector",
                  "autolabeler", "current_crop", "_last_resize_dims","_crop_overlay", "_thumb_cache",
                 "zoom_level", "fit_zoom_level", "zoom_label", "zoom_level_raw", "zoom_var", "zoom_slider", "drag_start")

    def __init__(self, root, image_canvas, status_label, settings, zoom_label=None):
        # UI references
        self.root = root
        self.image_canvas = image_canvas
        self.status_label = status_label

        # Initialize Previous Settings
        self.apply_settings(settings)

        # Image state
        self.image_files = []
        self.current_index = 0
        self.current_rotation = 0
        self.current_crop = None
        self.current_filter = None
        self.original_image = None
        self._last_resize_dims = None
        self._thumb_cache = {}

        # Undo/Redo stacks
        self.stack_redo = []
        self.stack_undo = []

        # Subsystems
        self.autolabeler = None
        self.duplicate_detector = None
        self._crop_overlay = CropOverlay(
            parent=self.image_canvas.master,
            root=self.root,
            image_canvas=self.image_canvas,  # pass canvas instead of label
            status_label=self.status_label,
            on_confirm=self._apply_crop,
        )

        # Initialize Keybindings
        self.root.bind("<Left>", lambda e: self.navigate(-1))
        self.root.bind("<Right>", lambda e: self.navigate(1))

        # Mousewheel Zoom
        # Windows / MacOS
        self.root.bind("<MouseWheel>", self.zoom_image_scroll)
        # Linux
        self.root.bind("<Button-4>", self.zoom_image_scroll)
        self.root.bind("<Button-5>", self.zoom_image_scroll)

        # Zoom Initializers
        self.zoom_level = tk.DoubleVar(value=1.0)
        self.zoom_var = tk.DoubleVar(value=100.0)
        self.fit_zoom_level = None
        self.zoom_level_raw = 1.0          # raw scale factor used for rendering
        self.zoom_label = zoom_label
        self.zoom_slider = None
        self.drag_start = None

        # Dragging buttons
        self.image_canvas.bind("<ButtonPress-1>", self.drag_start_handler)
        self.image_canvas.bind("<B1-Motion>", self.drag_move_handler)

    # --- Backend Functions -------------------------------------------------------------

    def apply_settings(self, settings):
        """Apply a settings dict to the instance."""
        self.confirm_deletes = settings.get("confirm_deletes", True)
        self.fast_delete = settings.get("fast_delete", False)
        self.labels = settings.get("image_labels", [])

        # Apply fast delete behavior immediately
        self.fast_delete_func()

    def load_folder(self, file_path):
        """Load all images in the same folder as the selected image, using bisect for efficient indexing."""
        file_path = os.path.normpath(file_path)
        folder = os.path.dirname(file_path)
        exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico"}

        with os.scandir(folder) as entries:
            self.image_files = sorted(
                entry.path
                for entry in entries
                if entry.is_file(follow_symlinks=False)
                and entry.name.lower().endswith(tuple(exts))
            )

        self.current_index = bisect_left(self.image_files, file_path)

        if self.current_index >= len(self.image_files) or self.image_files[self.current_index] != file_path:
            raise ValueError(f"File not found in folder: {file_path}")

    @staticmethod
    def unique_dest(folder, filename):
        """Generate a unique destination path if filename already exists."""
        base_name, ext = os.path.splitext(filename)
        dest = os.path.join(folder, filename)
        counter = 1

        if not os.path.exists(dest):
            return dest

        while os.path.exists(dest):
            dest = os.path.join(folder, f"{base_name}_{counter}{ext}")
            counter += 1

        return dest

    # --- Basic Image Functions -------------------------------------------------------------

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

    def save_image_overwrite(self):
        """Save the currently displayed image, overwriting the original file."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return

        current_file = self.image_files[self.current_index]

        try:
            self.original_image.save(current_file)
            self.status_label.config(text=f"Image saved: {current_file}")
        except Exception as e:
            self.status_label.config(text=f"Error saving image: {e}")

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
            self.image_canvas.delete("image")
            self.status_label.config(text="No images left in folder.")

    def get_metadata(self):
        """Extract metadata including EXIF (creation date, camera info, bit depth)."""
        if not self.image_files:
            messagebox.showinfo("Image Metadata", "No image loaded.")
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

            messagebox.showinfo("Image Metadata", (
                f"Dimensions: {width} x {height}\n"
                f"File Size: {file_size}\n"
                f"Created: {human}\n"
                f"Camera Make: {camera_make}\n"
                f"Camera Model: {camera_model}\n"
                f"Path: {file_path}"
            ))

        except Exception:
            messagebox.showinfo("Image Metadata", "Metadata unavailable.")

    # --- Displaying Images -------------------------------------------------------------

    def display_image(self, file_path):
        self.stack_undo.clear()
        self.stack_redo.clear()
        self.current_crop = None
        self.current_rotation = 0
        self.current_filter = None

        self._render_image(Image.open(file_path))
        self._sync_slider(100.0)
        self.status_label.config(text=os.path.basename(file_path))
        # Reset pan
        orig_w, orig_h = self.original_image.size if self.original_image else (0, 0)
        cx = self.image_canvas.winfo_width() // 2
        cy = self.image_canvas.winfo_height() // 2
        self.image_canvas.coords("image", cx, cy)

    def _render_image(self, image=None):
        if image is None:
            image = Image.open(self.image_files[self.current_index])

        self.original_image = image
        self._last_resize_dims = None
        self.resize_image()

    def _display_photo(self, photo, reset_pan=False):
        if reset_pan:
            cx = self.image_canvas.winfo_width() // 2
            cy = self.image_canvas.winfo_height() // 2
        else:
            coords = self.image_canvas.coords("image")
            cx = coords[0] if coords else self.image_canvas.winfo_width() // 2
            cy = coords[1] if coords else self.image_canvas.winfo_height() // 2

        self.image_canvas.delete("image")
        self.image_canvas.create_image(cx, cy, anchor="center", image=photo, tags="image")
        self.image_canvas.photo = photo

    def resize_image(self, event=None):
        """Resize the currently displayed image to fit within the window while preserving aspect ratio."""
        if self.original_image is None:
            return

        window_w = self.root.winfo_width()
        window_h = self.root.winfo_height()

        if window_w < 200 or window_h < 200:
            return
        if (window_w, window_h) == getattr(self, '_last_resize_dims', None):
            return

        available_h = max(50, window_h - 100)
        target_w = window_w - 40

        orig_w, orig_h = self.original_image.size
        scale = min(target_w / orig_w, available_h / orig_h)
        self.fit_zoom_level = scale

        display_img = self.original_image if scale >= 1.0 else \
            self.original_image.resize(
                (int(orig_w * scale), int(orig_h * scale)),
                Image.LANCZOS
            )

        self._display_photo(ImageTk.PhotoImage(display_img), reset_pan=True)

        self._last_resize_dims = (window_w, window_h)

    # --- Zoom Functions --------------------------------------------

    def zoom_image_scroll(self, event):
        if self.original_image is None:
            return
        delta = 1 if event.delta > 0 else -1
        self.set_zoom(self.zoom_level.get() * (1.1 ** delta))

    def set_zoom(self, level):
        """Set zoom by raw scale factor."""
        if self.original_image is None:
            return

        self.zoom_level_raw = max(0.01, level)

        orig_w, orig_h = self.original_image.size
        new_w = max(1, int(orig_w * self.zoom_level_raw))
        new_h = max(1, int(orig_h * self.zoom_level_raw))

        display_img = self.original_image.resize((new_w, new_h), Image.BILINEAR)
        self._display_photo(ImageTk.PhotoImage(display_img))

        if self.zoom_label is not None and self.fit_zoom_level:
            percent = (self.zoom_level_raw / self.fit_zoom_level) * 100
            self.zoom_label.config(text=f"{int(percent)}%")
            self._sync_slider(percent)

    def set_zoom_percent(self, percent):
        """Set zoom from a fit-relative percentage. Called by the slider."""
        if self.fit_zoom_level is None:
            return
        self.set_zoom(self.fit_zoom_level * (percent / 100.0))

    def _sync_slider(self, percent):
        clamped = max(10.0, min(800.0, percent))
        self.zoom_label.config(text=f"{int(clamped)}%")
        if hasattr(self, 'zoom_slider'):
            self.zoom_slider.set(clamped)

    def drag_start_handler(self, event):
        self.drag_start = (event.x, event.y)

    def drag_move_handler(self, event):
        if self.drag_start is None:
            return
        if self.zoom_level_raw <= self.fit_zoom_level:
            self.drag_start = (event.x, event.y)
            return

        dx = event.x - self.drag_start[0]
        dy = event.y - self.drag_start[1]
        self.image_canvas.move("image", dx, dy)
        self.drag_start = (event.x, event.y)

        # Clamp so image edges can't be dragged past canvas edges
        canvas_w = self.image_canvas.winfo_width()
        canvas_h = self.image_canvas.winfo_height()

        orig_w, orig_h = self.original_image.size
        img_w = int(orig_w * self.zoom_level_raw)
        img_h = int(orig_h * self.zoom_level_raw)

        x, y = self.image_canvas.coords("image")

        # x, y is the center of the image (anchor="center")
        half_w = img_w // 2
        half_h = img_h // 2

        clamped_x = max(half_w - max(0, img_w - canvas_w), min(canvas_w - half_w + max(0, img_w - canvas_w), x))
        clamped_y = max(half_h - max(0, img_h - canvas_h), min(canvas_h - half_h + max(0, img_h - canvas_h), y))

        if clamped_x != x or clamped_y != y:
            self.image_canvas.coords("image", clamped_x, clamped_y)

    # --- Navigation -------------------------------------------------------------

    def navigate(self, direction):
        """Display the next or previous image in the folder. Pass 1 for next, -1 for prev."""
        if self.image_files:
            self.current_index = (self.current_index + direction) % len(self.image_files)
            self.display_image(self.image_files[self.current_index])

    # --- Duplicate Handling -------------------------------------------------------------

    def check_duplicate(self):
        """Check for duplicates of the currently displayed image in the same folder and move them to a /Duplicates subfolder."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return

        loading = Toplevel(self.root)
        loading.title("Please Wait")
        Label(loading, text="Sorting duplicates...", padx=20, pady=20).pack()
        loading.update()

        if self.duplicate_detector is None:
            self.duplicate_detector = DuplicateDetectorMain()

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

    # --- Filter Functions -------------------------------------------------------------

    def apply_filter(self, filter_type, push_undo=True):
        if not self.image_files:
            return
        if push_undo:
            self.stack_undo.append(("filter", self.current_filter))

        self.current_filter = None if filter_type == "reset" else filter_type
        self._render_image(self._get_edited_image())

    def _get_edited_image(self):
        image = Image.open(self.image_files[self.current_index])
        if self.current_crop:
            image = image.crop(self.current_crop)
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

    # --- Rotate Functions -------------------------------------------------------------

    def rotate_image(self, angle, push_undo=True, absolute=True):
        if not self.image_files:
            return
        if push_undo:
            self.stack_undo.append(("rotate", self.current_rotation))

        self.current_rotation = angle if absolute else (self.current_rotation + angle) % 360
        self._render_image(self._get_edited_image())

    def rotate_custom(self):
        """Open a dialog to enter a custom rotation angle between 0 and 360 degrees."""
        if not self.image_files:
            return

        dialog = Toplevel(self.root)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.title("Rotate Image")
        dialog.geometry("250x140")
        dialog.resizable(False, False)

        Label(dialog, text="Enter angle (0-360):").pack(pady=10)

        def validate(value):
            return value.isdigit() or value == ""

        vcmd = dialog.register(validate)

        angle_entry = Entry(
            dialog,
            validate="key",
            validatecommand=(vcmd, "%P")
        )
        angle_entry.pack()
        angle_entry.focus()

        error_label = Label(dialog, text="", fg="red")
        error_label.pack()

        def apply():
            value = angle_entry.get()
            angle = int(value) if value else 0

            if angle > 360:
                error_label.config(text="Angle must be between 0 and 360.")
                return

            dialog.destroy()
            self.rotate_image(angle)

        dialog.bind("<Return>", lambda _: apply())
        Button(dialog, text="Rotate", command=apply).pack(pady=5)

    # --- Undo/Redo Functions -------------------------------------------------------------

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
        elif last_action == "crop":
            self.stack_redo.append(("crop", self.current_crop))
            self.current_crop = value
            self.status_label.config(text="Undid crop.")
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
        elif action == "crop":
            self.stack_undo.append(("crop", self.current_crop))
            self.current_crop = value
            self.status_label.config(text="Redid crop.")
        else:
            self.status_label.config(text="Unknown action to redo.")
            return

        self._render_image(self._get_edited_image())

    # --- Fast Delete Mode -------------------------------------------------------------

    def fast_delete_func(self):
        """Toggle fast delete mode — left arrow deletes, right arrow moves."""
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
            self.image_canvas.delete("image")
            self.status_label.config(text="No images left.")

    # --- Auto Sort Function -------------------------------------------------------------

    def auto_sort_images(self, nsfw_mode=False):
        """Sorts images into subfolders based on their labels using CLIP. If nsfw_mode is True, sorts into NSFW vs SFW instead."""
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return
        if not nsfw_mode and not self.labels:
            self.status_label.config(text="No labels defined. Please add labels with Manage Labels.")
            return
        if self.autolabeler is None:
            self.autolabeler = CLIPLabeler()

        labels = self.labels if not nsfw_mode else ["NSFW photo", "SFW photo"]

        loading = Toplevel(self.root)
        loading.title("Please Wait")
        loading.transient(self.root)
        loading.grab_set()

        if nsfw_mode:
            Label(loading, text="Sorting NSFW images...", padx=20, pady=20).pack()
        else:
            Label(loading, text="Sorting images by label...", padx=20, pady=20).pack()
        loading.update()

        folder = os.path.dirname(self.image_files[0])
        count = len(self.image_files)
        text_tokens = self.autolabeler.initialize_clip_labels(labels)

        for subfolder in set(labels):
            os.makedirs(os.path.join(folder, subfolder), exist_ok=True)

        for file in self.image_files:
            label = self.autolabeler.get_clip_label(file, labels, text_tokens)
            labeled_folder = os.path.join(folder, label)
            shutil.move(file, self.unique_dest(labeled_folder, os.path.basename(file)))

        loading.destroy()
        self.image_files.clear()
        self.current_index = 0
        self.original_image = None
        self.image_canvas.delete("image")
        self.status_label.config(text=f"Sorted {count} images into {len(labels)} label(s).")

    # --- Crop Functions -------------------------------------------------------------

    def start_crop_mode(self):
        if not self.image_files or self.original_image is None:
            self.status_label.config(text="No image loaded.")
            return
        self._crop_overlay.start(self.original_image, self.current_crop)

    def _apply_crop(self, x1, y1, x2, y2):
        self.stack_undo.append(("crop", self.current_crop))
        self.stack_redo.clear()
        self.current_crop = (x1, y1, x2, y2)
        self._render_image(self._get_edited_image())
        self.status_label.config(text=f"Cropped to {x2 - x1}×{y2 - y1}.")

    # --- Multi-Image View --------------------------------------------------------------

    def open_mass_delete(self):
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return
        MassDeleteDialog(
            parent=self.root,
            image_files=self.image_files,
            thumb_cache=self._thumb_cache,
            confirm_deletes=self.confirm_deletes,
            on_confirm=self._on_mass_delete,
        )

    def _on_mass_delete(self, to_delete):
        for path in to_delete:
            send2trash(path)
        self.image_files = [p for p in self.image_files if p not in to_delete]
        if self.image_files:
            self.current_index = min(self.current_index, len(self.image_files) - 1)
            self.display_image(self.image_files[self.current_index])
        else:
            self.original_image = None
            self.image_canvas.delete("image")
        self.status_label.config(text=f"Trashed {len(to_delete)} image(s).")

    # --- Rename Photo Function -------------------------------------------------------------

    def rename_photo(self):
        if not self.image_files:
            self.status_label.config(text="No image loaded.")
            return

        current_file = self.image_files[self.current_index]
        folder = os.path.dirname(current_file)
        old_name = os.path.basename(current_file)
        old_stem, ext = os.path.splitext(old_name)

        dialog = Toplevel(self.root)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.title("Rename Photo")
        dialog.resizable(False, False)

        Label(dialog, text="Enter new name:").pack(pady=(10, 5))

        # Entry row
        row = tk.Frame(dialog)
        row.pack()
        name_entry = Entry(row, width=22)
        name_entry.insert(0, old_stem)
        name_entry.pack(side="left")
        Label(row, text=ext).pack(side="left")
        name_entry.focus()

        # Reuse one label for all errors
        error_label = Label(dialog, text="", fg="red")
        error_label.pack(pady=5)

        def apply():
            new_stem = name_entry.get().strip()
            if not new_stem:
                error_label.config(text="Name cannot be empty.")
                return

            if new_stem == old_stem:
                error_label.config(text="Name is unchanged.")
                return

            new_name = new_stem + ext
            new_path = os.path.join(folder, new_name)

            if os.path.exists(new_path):
                error_label.config(text="File already exists.")
                return

            os.rename(current_file, new_path)
            self.image_files[self.current_index] = new_path
            self.display_image(new_path)
            self.status_label.config(text=f"Renamed to: {new_name}")
            dialog.destroy()

        dialog.bind("<Return>", lambda _: apply())
        Button(dialog, text="Rename", command=apply).pack(pady=(5, 10))
