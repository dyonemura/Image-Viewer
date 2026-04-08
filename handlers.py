import os
import shutil
from bisect import bisect_left
from tkinter import Button, Entry, Label, Toplevel, filedialog, messagebox
import tkinter as tk

from PIL import Image, ImageEnhance, ImageFilter, ImageTk
from PIL.ExifTags import TAGS
from send2trash import send2trash
import datetime

from DuplicateDetector import DuplicateDetectorMain
from autolabeler import CLIPLabeler

class ImageFunctions:
    __slots__ = ("root", "image_label", "status_label", "confirm_deletes", "fast_delete", 
                  "labels", "image_files", "current_index", "original_image", "stack_undo", 
                  "stack_redo", "current_rotation", "current_filter", "duplicate_detector", 
                  "autolabeler", "current_crop", "crop_start", "crop_rect", "_last_resize_dims", 
                  "_crop_canvas", "_crop_photo", "_crop_scale", "_crop_img_offset", "_crop_drag_corner", "_crop_bounds", "_thumb_cache")
    
    _HANDLE_R = 6

    def __init__(self, root, image_label, status_label, crop_canvas, settings):
        # UI references
        self.root = root
        self.image_label = image_label
        self.status_label = status_label
        self._crop_canvas = crop_canvas
        
        # Initialize Previous Settings
        self.apply_settings(settings)
       
        # Image state
        self.image_files = []
        self.current_index = 0
        self.current_rotation = 0
        self.crop_start = None
        self.crop_rect = None
        self.current_crop = None
        self.current_filter = None
        self.original_image = None
        self._crop_bounds = None
        self._thumb_cache = {} 

        # Undo/Redo stacks
        self.stack_redo = []
        self.stack_undo = []

        # Subsystems
        self.autolabeler = CLIPLabeler()
        self.duplicate_detector = DuplicateDetectorMain()

        # Initialize Keybindings
        self.root.bind("<Left>", lambda e: self.navigate(-1))
        self.root.bind("<Right>", lambda e: self.navigate(1))

    # --- Backend Functions -------------------------------------------------------------

    def apply_settings(self, settings):
        """Apply a settings dict to the instance."""
        self.confirm_deletes = settings.get("confirm_deletes", True)
        self.fast_delete = settings.get("fast_delete", False)
        self.labels = settings.get("image_labels", [])

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
        
    def unique_dest(self, folder, filename):
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
    
    # --- Displaying Images -------------------------------------------------------------

    def display_image(self, file_path):
        """Load the image and trigger a resize based on window size."""
        self._render_image(Image.open(file_path))
        self.status_label.config(text=os.path.basename(file_path))
    
    def _render_image(self, image=None):
        if image is None:
            image = Image.open(self.image_files[self.current_index])
        
        self.original_image = image
        self._last_resize_dims = None
        self.resize_image()

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

        display_img = self.original_image if scale >= 1.0 else \
            self.original_image.resize(
                (int(orig_w * scale), int(orig_h * scale)),
                Image.LANCZOS
            )

        photo = ImageTk.PhotoImage(display_img)
        self.image_label.config(image=photo)
        self.image_label.photo = photo

        self._last_resize_dims = (window_w, window_h)

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
            self.image_label.config(image="")
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
            self.image_label.config(image="")
            self.status_label.config(text=f"Sorted {count} images into {len(labels)} label(s).")
        
    # --- Crop Functions -------------------------------------------------------------

    def start_crop_mode(self):
        """Overlay the crop canvas on the image label and begin listening for drag events."""
        if not self.image_files or self.original_image is None:
            self.status_label.config(text="No image loaded.")
            return

        self.image_label.update_idletasks()
        x = self.image_label.winfo_x()
        y = self.image_label.winfo_y()
        w = self.image_label.winfo_width()
        h = self.image_label.winfo_height()

        canvas = self._crop_canvas
        canvas.place(x=x, y=y, width=w, height=h)

        orig_w, orig_h = self.original_image.size
        scale = min(w / orig_w, h / orig_h)
        disp_w = int(orig_w * scale)
        disp_h = int(orig_h * scale)

        display_img = self.original_image.resize((disp_w, disp_h), Image.LANCZOS)
        self._crop_photo = ImageTk.PhotoImage(display_img)
        self._crop_scale = (orig_w / disp_w, orig_h / disp_h)

        offset_x = (w - disp_w) // 2
        offset_y = (h - disp_h) // 2
        self._crop_img_offset = (offset_x, offset_y)
        self._crop_bounds = (
            offset_x,
            offset_y,
            offset_x + disp_w,
            offset_y + disp_h
        )

        canvas.delete("all")
        canvas.create_image(offset_x, offset_y, anchor="nw", image=self._crop_photo)

        self.crop_start = None
        self.crop_rect = None
        self._crop_drag_corner = None

        canvas.bind("<ButtonPress-1>",   self._crop_press)
        canvas.bind("<B1-Motion>",       self._crop_drag)
        canvas.bind("<ButtonRelease-1>", self._crop_release)

        self.status_label.config(text="Drag to select crop region. Press Enter to confirm, Esc to cancel.")
        self.root.bind("<Return>", lambda _: self.confirm_crop())
        self.root.bind("<Escape>", lambda _: self.cancel_crop())

    def _crop_corners(self):
        """Return the four corner (cx, cy) pairs of the current crop rect in canvas coords."""
        if self.crop_rect is None:
            return []
        x1, y1, x2, y2 = self._crop_canvas.coords(self.crop_rect)
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    def _crop_press(self, event):
        # Check if clicking near an existing corner handle
        corners = self._crop_corners()
        for i, (cx, cy) in enumerate(corners):
            if abs(event.x - cx) <= type(self)._HANDLE_R + 4 and abs(event.y - cy) <= type(self)._HANDLE_R + 4:
                self._crop_drag_corner = i
                return
        # Otherwise start a new rectangle
        self._crop_drag_corner = None
        self.crop_start = self._clamp_to_image(event.x, event.y)
        canvas = self._crop_canvas
        if self.crop_rect:
            canvas.delete(self.crop_rect)
        canvas.delete("handle")
        self.crop_rect = canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#00BFFF", width=2, dash=(4, 2)
        )

    def _crop_drag(self, event):
        canvas = self._crop_canvas

        x, y = self._clamp_to_image(event.x, event.y)

        if self._crop_drag_corner is not None and self.crop_rect is not None:
            x1, y1, x2, y2 = canvas.coords(self.crop_rect)

            if self._crop_drag_corner == 0:      # top-left
                x1, y1 = x, y
            elif self._crop_drag_corner == 1:    # top-right
                x2, y1 = x, y
            elif self._crop_drag_corner == 2:    # bottom-right
                x2, y2 = x, y
            elif self._crop_drag_corner == 3:    # bottom-left
                x1, y2 = x, y

            canvas.coords(self.crop_rect, x1, y1, x2, y2)

        elif self.crop_start:
            x0, y0 = self.crop_start
            x0, y0 = self._clamp_to_image(x0, y0)
            canvas.coords(self.crop_rect, x0, y0, x, y)

        self._draw_handles()

    def _crop_release(self, event):
        self._crop_drag_corner = None
        self._draw_handles()

    def _draw_handles(self):
        """Redraw the four draggable corner squares."""
        canvas = self._crop_canvas
        canvas.delete("handle")
        r = type(self)._HANDLE_R
        for cx, cy in self._crop_corners():
            canvas.create_rectangle(
                cx - r, cy - r, cx + r, cy + r,
                fill="#00BFFF", outline="white", width=1, tags="handle"
            )

    def confirm_crop(self):
        """Map canvas crop rect back to image coordinates and store as current_crop."""
        if self.crop_rect is None:
            self.cancel_crop()
            return

        x1, y1, x2, y2 = self._crop_canvas.coords(self.crop_rect)
        # Ensure x1 < x2, y1 < y2
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        # Subtract the image offset (letterbox padding) then scale to image coords
        ox, oy = self._crop_img_offset
        sx, sy = self._crop_scale
        img_x1 = int((x1 - ox) * sx)
        img_y1 = int((y1 - oy) * sy)
        img_x2 = int((x2 - ox) * sx)
        img_y2 = int((y2 - oy) * sy)

        orig_w, orig_h = self.original_image.size
        img_x1 = max(0, img_x1)
        img_y1 = max(0, img_y1)
        img_x2 = min(orig_w, img_x2)
        img_y2 = min(orig_h, img_y2)

        if img_x2 - img_x1 < 2 or img_y2 - img_y1 < 2:
            self.status_label.config(text="Crop region too small — cancelled.")
            self.cancel_crop()
            return

        self.stack_undo.append(("crop", self.current_crop))
        self.stack_redo.clear()
        self.current_crop = (img_x1, img_y1, img_x2, img_y2)
        self._teardown_crop()
        self._render_image(self._get_edited_image())
        self.status_label.config(text=f"Cropped to {img_x2 - img_x1}×{img_y2 - img_y1}.")

    def cancel_crop(self):
        self._teardown_crop()
        self.status_label.config(text="Crop cancelled.")

    def _teardown_crop(self):
        canvas = self._crop_canvas
        canvas.unbind("<ButtonPress-1>")
        canvas.unbind("<B1-Motion>")
        canvas.unbind("<ButtonRelease-1>")
        canvas.place_forget()
        self.root.unbind("<Return>")
        self.root.unbind("<Escape>")
        self.crop_rect = None
        self.crop_start = None

    def _clamp_to_image(self, x, y):
        left, top, right, bottom = self._crop_bounds
        return (
            max(left, min(x, right)),
            max(top, min(y, bottom))
        )
    
    # --- Multi-Image View --------------------------------------------------------------

    def open_mass_delete(self):
        if not self.image_files:
            self.status_label.config(text="No images loaded.")
            return

        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=4)

        win = Toplevel(self.root)
        win.title("Mass Delete")
        win.geometry("900x600")

        outer = tk.Frame(win)
        outer.pack(fill="both", expand=True)

        scroll_canvas = tk.Canvas(outer)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)

        grid_frame = tk.Frame(scroll_canvas)
        scroll_canvas.create_window((0, 0), window=grid_frame, anchor="nw")
        grid_frame.bind("<Configure>", lambda e: scroll_canvas.configure(
            scrollregion=scroll_canvas.bbox("all")
        ))
        scroll_canvas.bind_all("<MouseWheel>", lambda e: (
            scroll_canvas.yview_scroll(-1 * (e.delta // 120), "units"),
            _schedule_load()
        ))

        check_vars  = {path: tk.BooleanVar() for path in self.image_files}
        cell_frames = {}
        labels      = {}
        loaded      = set()   # paths fully loaded at current thumb_size
        in_flight   = set()   # paths currently being loaded in background
        _state      = {"cols": 0, "thumb_size": 0, "resize_job": None, "load_job": None}

        def build_grid(thumb_size, cols):
            # Evict cache entries for old thumb_size
            old_size = _state["thumb_size"]
            if old_size and old_size != thumb_size:
                stale = [k for k in self._thumb_cache if k[1] == old_size]
                for k in stale:
                    del self._thumb_cache[k]

            for widget in grid_frame.winfo_children():
                widget.destroy()
            labels.clear()
            cell_frames.clear()
            loaded.clear()
            in_flight.clear()

            for i, path in enumerate(self.image_files):
                var = check_vars[path]
                cell = tk.Frame(grid_frame, padx=4, pady=4)
                cell.grid(row=i // cols, column=i % cols)
                cell_frames[path] = cell

                lbl = tk.Label(cell, width=thumb_size // 8, height=thumb_size // 16, bg="#222")
                lbl.image = None
                lbl.pack()
                labels[path] = lbl

                lbl.bind("<Button-1>", lambda e, v=var, f=cell: self._thumb_toggle(v, f))

                name = os.path.basename(path)
                tk.Label(cell, text=name[:20], font=("Arial", 7), wraplength=thumb_size).pack()
                tk.Checkbutton(cell, variable=var,
                            command=lambda v=var, f=cell: self._thumb_highlight(v, f)).pack()

            _state["thumb_size"] = thumb_size
            _state["cols"] = cols

        def _do_load_thumb(path, thumb_size):
            """Runs in thread pool — no Tk calls here."""
            cache_key = (path, thumb_size)
            if cache_key in self._thumb_cache:
                return path, thumb_size, self._thumb_cache[cache_key]
            try:
                img = Image.open(path)
                img.thumbnail((thumb_size, thumb_size), Image.BILINEAR)
                photo = ImageTk.PhotoImage(img)  # must be on main thread ideally,
                # but PhotoImage creation is safe if called before mainloop sees it
            except Exception:
                photo = None
            self._thumb_cache[cache_key] = photo
            return path, thumb_size, photo

        def _apply_thumb(path, thumb_size, photo):
            """Called back on main thread via win.after."""
            if not win.winfo_exists():
                return
            in_flight.discard(path)
            loaded.add(path)
            if thumb_size != _state["thumb_size"]:
                return  # stale result from a previous layout
            lbl = labels.get(path)
            if lbl and photo:
                lbl.config(image=photo, width=thumb_size, height=thumb_size, bg="#000")
                lbl.image = photo

        def load_visible():
            if not win.winfo_exists():
                return
            thumb_size = _state["thumb_size"]
            cols       = _state["cols"]
            if not cols:
                return

            canvas_h = scroll_canvas.winfo_height()
            top      = scroll_canvas.canvasy(0)
            bottom   = scroll_canvas.canvasy(canvas_h)
            row_h    = thumb_size + 40

            for i, path in enumerate(self.image_files):
                if path in loaded or path in in_flight:
                    continue
                row_top = (i // cols) * row_h
                if row_top > bottom + row_h or row_top + row_h < top:
                    continue

                in_flight.add(path)
                future = executor.submit(_do_load_thumb, path, thumb_size)
                future.add_done_callback(
                    lambda f: win.after(0, lambda r=f.result(): _apply_thumb(*r))
                )

        def _schedule_load():
            """Debounce load_visible calls triggered by scroll."""
            if _state["load_job"]:
                win.after_cancel(_state["load_job"])
            _state["load_job"] = win.after(80, load_visible)

        def compute_layout(win_w):
            cols       = max(2, win_w // 180)
            thumb_size = max(80, (win_w // cols) - 20)
            return thumb_size, cols

        def on_resize(event):
            if event.widget is not win:
                return
            if _state["resize_job"]:
                win.after_cancel(_state["resize_job"])

            def apply():
                thumb_size, cols = compute_layout(win.winfo_width())
                if cols == _state["cols"] and thumb_size == _state["thumb_size"]:
                    return
                build_grid(thumb_size, cols)
                load_visible()

            _state["resize_job"] = win.after(200, apply)

        # Shut down thread pool when window closes
        win.protocol("WM_DELETE_WINDOW", lambda: (executor.shutdown(wait=False), win.destroy()))

        win.bind("<Configure>", on_resize)
        scroll_canvas.bind("<MouseWheel>", lambda e: _schedule_load())

        win.update_idletasks()
        thumb_size, cols = compute_layout(win.winfo_width())
        build_grid(thumb_size, cols)
        win.after(100, load_visible)

        bar = tk.Frame(win)
        bar.pack(fill="x", side="bottom", pady=6)
        tk.Button(bar, text="Select All",   command=lambda: self._mass_select(check_vars, True)).pack(side="left", padx=6)
        tk.Button(bar, text="Deselect All", command=lambda: self._mass_select(check_vars, False)).pack(side="left")
        tk.Button(bar, text="Delete Selected", fg="white", bg="red",
                command=lambda: self._mass_delete_confirm(win, check_vars)).pack(side="right", padx=6)

    def _thumb_toggle(self, var, frame):
        var.set(not var.get())
        self._thumb_highlight(var, frame)

    def _thumb_highlight(self, var, frame):
        frame.config(bg="red" if var.get() else frame.master.cget("bg"))
        for child in frame.winfo_children():
            try:
                child.config(bg="red" if var.get() else frame.master.cget("bg"))
            except tk.TclError:
                pass

    def _mass_select(self, check_vars, state):
        for var in check_vars.values():
            var.set(state)

    def _mass_delete_confirm(self, win, check_vars):
        to_delete = [p for p, v in check_vars.items() if v.get()]
        if not to_delete:
            return

        if self.confirm_deletes:
            if not messagebox.askyesno("Delete", f"Trash {len(to_delete)} image(s)?"):
                return

        for path in to_delete:
            send2trash(path)
            self.image_files.remove(path)

        # If current image was deleted, clamp index
        if self.image_files:
            self.current_index = min(self.current_index, len(self.image_files) - 1)
            self.display_image(self.image_files[self.current_index])
        else:
            self.original_image = None
            self.image_label.config(image="")

        self.status_label.config(text=f"Trashed {len(to_delete)} image(s).")
        win.destroy()
    
    # --- Rename Photo Function -------------------------------------------------------------

    def rename_photo(self):
        """Open a dialog to rename the current photo."""
        if not self.image_files:
            self.status_label.config(text="No image loaded.")
            return

        current_file = self.image_files[self.current_index]
        folder = os.path.dirname(current_file)
        old_name = os.path.basename(current_file)

        dialog = Toplevel(self.root)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.title("Rename Photo")
        dialog.geometry("300x150")
        dialog.resizable(False, False)

        Label(dialog, text="Enter new name (with extension):").pack(pady=10)

        name_entry = Entry(dialog)
        name_entry.insert(0, old_name)
        name_entry.pack()
        name_entry.focus()

        error_label = Label(dialog, text="", fg="red")
        error_label.pack()

        def apply():
            new_name = name_entry.get().strip()
            if not new_name:
                error_label.config(text="Name cannot be empty.")
                return
            if new_name == old_name:
                error_label.config(text="New name is the same as the current name.")
                return
            if os.path.exists(os.path.join(folder, new_name)):
                error_label.config(text="A file with that name already exists.")
                return

            new_path = os.path.join(folder, new_name)
            os.rename(current_file, new_path)
            self.image_files[self.current_index] = new_path
            self.display_image(new_path)
            self.status_label.config(text=f"Renamed to: {new_name}")
            dialog.destroy()

        dialog.bind("<Return>", lambda _: apply())
        Button(dialog, text="Rename", command=apply).pack(pady=5)