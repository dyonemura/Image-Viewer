import os
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import Toplevel, messagebox

from PIL import Image, ImageTk


class MassDeleteDialog:
    __slots__ = ("_thumb_cache", "confirm_deletes", "on_confirm", "image_files", "_executor",
                 "win", "_check_vars", "_labels", "_cell_frames", "_loaded", "_in_flight", "_state",
                 "_grid_frame", "_scroll_canvas")

    def __init__(self, parent, image_files, thumb_cache, confirm_deletes, on_confirm):
        """
        parent          - the root Tk window
        image_files     - list of image paths (will not be mutated here)
        thumb_cache     - shared dict from the main app
        confirm_deletes - bool from app settings
        on_confirm      - callback(to_delete: set) called after user confirms
        """
        self._thumb_cache = thumb_cache
        self.confirm_deletes = confirm_deletes
        self.on_confirm = on_confirm
        self.image_files = image_files
        self._executor = ThreadPoolExecutor(max_workers=4)

        self.win = Toplevel(parent)
        self.win.title("Mass Delete")
        self.win.geometry("900x600")
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        self._check_vars = {path: tk.BooleanVar() for path in image_files}
        self._labels = {}
        self._cell_frames = {}
        self._loaded = set()
        self._in_flight = set()
        self._state = {"cols": 0, "thumb_size": 0, "resize_job": None, "load_job": None}
        self._grid_frame = None

        self._build_ui()

    # --- UI Construction -------------------------------------------------------------

    def _build_ui(self):
        outer = tk.Frame(self.win)
        outer.pack(fill="both", expand=True)

        self._scroll_canvas = tk.Canvas(outer)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

        self._grid_frame = tk.Frame(self._scroll_canvas)
        self._scroll_canvas.create_window((0, 0), window=self._grid_frame, anchor="nw")
        self._grid_frame.bind("<Configure>", lambda e: self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all")
        ))

        self.win.bind("<MouseWheel>", self._on_mousewheel)

        self._scroll_canvas.bind("<MouseWheel>", lambda e: self._schedule_load())
        self.win.bind("<Configure>", self._on_resize)

        bar = tk.Frame(self.win)
        bar.pack(fill="x", side="bottom", pady=6)
        tk.Button(bar, text="Select All", command=lambda: self._mass_select(True)).pack(side="left", padx=6)
        tk.Button(bar, text="Deselect All", command=lambda: self._mass_select(False)).pack(side="left")
        tk.Button(bar, text="Delete Selected", fg="white", bg="red",
                  command=self._confirm_delete).pack(side="right", padx=6)

        self.win.update_idletasks()
        thumb_size, cols = self._compute_layout(self.win.winfo_width())
        self._build_grid(thumb_size, cols)
        self.win.after(100, self._load_visible)

    def _on_mousewheel(self, event):
        self._scroll_canvas.yview_scroll(-1 * (event.delta // 120), "units")
        self._schedule_load()

    # --- UI Construction -------------------------------------------------------------

    def _build_grid(self, thumb_size, cols):
        old_size = self._state["thumb_size"]
        if old_size and old_size != thumb_size:
            stale = [k for k in self._thumb_cache if k[1] == old_size]
            for k in stale:
                del self._thumb_cache[k]

        for widget in self._grid_frame.winfo_children():
            widget.destroy()
        self._labels.clear()
        self._cell_frames.clear()
        self._loaded.clear()
        self._in_flight.clear()

        for i, path in enumerate(self.image_files):
            var = self._check_vars[path]
            cell = tk.Frame(self._grid_frame, padx=4, pady=4)
            cell.grid(row=i // cols, column=i % cols)
            self._cell_frames[path] = cell

            lbl = tk.Label(cell, width=thumb_size // 8, height=thumb_size // 16, bg="#222")
            lbl.image = None
            lbl.pack()
            self._labels[path] = lbl

            lbl.bind("<Button-1>", lambda e, v=var, f=cell: MassDeleteDialog._thumb_toggle(v, f))

            tk.Label(cell, text=os.path.basename(path)[:20],
                     font=("Arial", 7), wraplength=thumb_size).pack()
            tk.Checkbutton(cell, variable=var,
                           command=lambda v=var, f=cell: MassDeleteDialog._thumb_highlight(v, f)).pack()


        self._state["thumb_size"] = thumb_size
        self._state["cols"] = cols

    # --- Thumbnail Loading -------------------------------------------------------------

    def _load_visible(self):
        if not self.win.winfo_exists():
            return
        thumb_size = self._state["thumb_size"]
        cols = self._state["cols"]
        if not cols:
            return

        canvas_h = self._scroll_canvas.winfo_height()
        top = self._scroll_canvas.canvasy(0)
        bottom = self._scroll_canvas.canvasy(canvas_h)
        row_h = thumb_size + 40

        for i, path in enumerate(self.image_files):
            if path in self._loaded or path in self._in_flight:
                continue
            row_top = (i // cols) * row_h
            if row_top > bottom + row_h or row_top + row_h < top:
                continue

            self._in_flight.add(path)
            future = self._executor.submit(self._do_load_thumb, path, thumb_size)
            future.add_done_callback(lambda f: self._on_thumb_done(f))

    def _do_load_thumb(self, path, thumb_size):
        cache_key = (path, thumb_size)
        if cache_key in self._thumb_cache:
            return path, thumb_size, self._thumb_cache[cache_key]
        try:
            img = Image.open(path)
            img.thumbnail((thumb_size, thumb_size), Image.BILINEAR)
            photo = ImageTk.PhotoImage(img)
        except Exception:
            photo = None
        self._thumb_cache[cache_key] = photo
        return path, thumb_size, photo

    def _apply_thumb(self, path, thumb_size, photo):
        if not self.win.winfo_exists():
            return
        self._in_flight.discard(path)
        self._loaded.add(path)
        if thumb_size != self._state["thumb_size"]:
            return
        lbl = self._labels.get(path)
        if lbl and photo:
            lbl.config(image=photo, width=thumb_size, height=thumb_size, bg="#000")
            lbl.image = photo

    def _on_thumb_done(self, future):
        try:
            result = future.result()
        except Exception:
            return
        self.win.after(0, self._apply_thumb, *result)

    # --- Layout / Resize -------------------------------------------------------------

    @staticmethod
    def _compute_layout(win_w):
        cols = max(2, win_w // 180)
        thumb_size = max(80, (win_w // cols) - 20)
        return thumb_size, cols

    def _on_resize(self, event):
        if event.widget is not self.win:
            return
        if self._state["resize_job"]:
            self.win.after_cancel(self._state["resize_job"])

        def apply():
            thumb_size, cols = self._compute_layout(self.win.winfo_width())
            if cols != self._state["cols"]:
                self._build_grid(thumb_size, cols)  # full rebuild only when cols change
            elif thumb_size != self._state["thumb_size"]:
                self._resize_labels_only(thumb_size)  # just update width/height
            self._load_visible()

        self._state["resize_job"] = self.win.after(200, apply)

    def _schedule_load(self):
        if self._state["load_job"]:
            self.win.after_cancel(self._state["load_job"])
        self._state["load_job"] = self.win.after(80, self._load_visible)

    def _resize_labels_only(self, thumb_size):
        self._loaded.clear()
        for lbl in self._labels.values():
            lbl.config(width=thumb_size // 8, height=thumb_size // 16, image="")
            lbl.image = None
        self._state["thumb_size"] = thumb_size

    # --- Selection / Deletion ----------------------------------------------------

    def _mass_select(self, state):
        for var in self._check_vars.values():
            var.set(state)

    def _confirm_delete(self):
        to_delete = {p for p, v in self._check_vars.items() if v.get()}
        if not to_delete:
            return
        if self.confirm_deletes:
            if not messagebox.askyesno("Delete", f"Trash {len(to_delete)} image(s)?"):
                return
        self.on_confirm(to_delete)
        self._on_close()

    def _on_close(self):
        self._executor.shutdown(wait=False)
        if self.win.winfo_exists():
            self.win.destroy()

    # --- Static helpers -------------------------------------------------------------

    @staticmethod
    def _thumb_toggle(var, frame):
        var.set(not var.get())
        MassDeleteDialog._thumb_highlight(var, frame)

    @staticmethod
    def _thumb_highlight(var, frame):
        bg = "red" if var.get() else frame.master.cget("bg")
        frame.config(bg=bg)
        for child in frame.winfo_children():
            try:
                child.config(bg=bg)
            except tk.TclError:
                pass