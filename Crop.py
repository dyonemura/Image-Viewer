import tkinter as tk
from PIL import Image, ImageTk

class CropOverlay:
    """
    Manages a transparent canvas overlay for interactive cropping.

    Responsibilities:
    - Rendering the image at display scale with letterbox offset
    - Drawing and dragging the crop rectangle and corner handles
    - Mapping canvas coordinates back to image coordinates on confirm
    - Calling on_confirm(x1, y1, x2, y2) with validated image-space coords
    - Full teardown (unbinds, hides canvas) on confirm or cancel

    Deliberately does NOT:
    - Touch the undo/redo stack (caller's responsibility in on_confirm)
    - Hold a reference to the app object
    - Persist state between sessions
    """

    _HANDLE_R: int = 6  # half-size of corner drag handles in canvas pixels

    __slots__ = (
        "_canvas",
        "_root",
        "image_canvas",
        "_status_label",
        "_on_confirm",
        # per-session state (set fresh each call to start())
        "_photo",
        "_scale",
        "_img_offset",
        "_bounds",
        "_rect",
        "_drag_start",
        "_drag_corner",
    )

    def __init__(self, parent, root, image_canvas, status_label, on_confirm):
        """
        Parameters
        ----------
        parent       : tk widget that image_label lives inside (used for canvas placement)
        root         : root Tk window (for <Return>/<Escape> binds)
        image_label  : the Label widget showing the current image
        status_label : Label used to display status messages
        on_confirm   : callable(x1, y1, x2, y2) — called with image-space crop coords
        """
        self._root = root
        self.image_canvas = image_canvas
        self._status_label = status_label
        self._on_confirm = on_confirm

        self._canvas = tk.Canvas(parent, cursor="crosshair", highlightthickness=0)

        self._photo = None
        self._scale = (1.0, 1.0)
        self._img_offset = (0, 0)
        self._bounds = (0, 0, 0, 0)
        self._rect = None
        self._drag_start = None
        self._drag_corner = None

    def start(self, original_image: Image.Image, current_crop=None):
        """
        Show the crop overlay over image_label, sized and positioned to match it.

        Parameters
        ----------
        original_image : PIL.Image currently loaded in the viewer
        current_crop   : existing (x1, y1, x2, y2) in image coords, or None
        """
        if original_image is None:
            self._status_label.config(text="No image loaded.")
            return

        self.image_canvas.update_idletasks()
        x = self.image_canvas.winfo_x()
        y = self.image_canvas.winfo_y()
        w = self.image_canvas.winfo_width()
        h = self.image_canvas.winfo_height()

        canvas = self._canvas
        canvas.place(x=x, y=y, width=w, height=h)
        canvas.delete("all")

        # Compute display scale and letterbox offset
        orig_w, orig_h = original_image.size
        scale = min(w / orig_w, h / orig_h)
        disp_w = int(orig_w * scale)
        disp_h = int(orig_h * scale)
        offset_x = (w - disp_w) // 2
        offset_y = (h - disp_h) // 2

        self._scale = (orig_w / disp_w, orig_h / disp_h)
        self._img_offset = (offset_x, offset_y)
        self._bounds = (offset_x, offset_y, offset_x + disp_w, offset_y + disp_h)

        # Render image onto canvas
        display_img = original_image.resize((disp_w, disp_h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(display_img)
        canvas.create_image(offset_x, offset_y, anchor="nw", image=self._photo)

        # Reset drag state
        self._rect = None
        self._drag_start = None
        self._drag_corner = None

        # Pre-draw existing crop if present
        if current_crop is not None:
            self._draw_initial_crop(current_crop, orig_w, orig_h)

        # Bind events
        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        self._root.bind("<Return>", lambda _: self.confirm())
        self._root.bind("<Escape>", lambda _: self.cancel())

        self._status_label.config(
            text="Drag to select crop region. Press Enter to confirm, Esc to cancel."
        )

    def confirm(self):
        """Validate the crop rect, map to image coords, and fire on_confirm."""
        if self._rect is None:
            self.cancel()
            return

        x1, y1, x2, y2 = self._canvas.coords(self._rect)
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        ox, oy = self._img_offset
        sx, sy = self._scale
        img_x1 = int((x1 - ox) * sx)
        img_y1 = int((y1 - oy) * sy)
        img_x2 = int((x2 - ox) * sx)
        img_y2 = int((y2 - oy) * sy)

        # Clamp to actual image bounds using the stored scale
        max_x = int((self._bounds[2] - ox) * sx)
        max_y = int((self._bounds[3] - oy) * sy)
        img_x1 = max(0, img_x1)
        img_y1 = max(0, img_y1)
        img_x2 = min(max_x, img_x2)
        img_y2 = min(max_y, img_y2)

        if img_x2 - img_x1 < 2 or img_y2 - img_y1 < 2:
            self._status_label.config(text="Crop region too small — cancelled.")
            self._teardown()
            return

        self._teardown()
        self._on_confirm(img_x1, img_y1, img_x2, img_y2)

    def cancel(self):
        """Cancel cropping and hide the overlay without doing anything."""
        self._teardown()
        self._status_label.config(text="Crop cancelled.")

    # ------------------------------------------------------------------ #
    # Canvas event handlers                                                #
    # ------------------------------------------------------------------ #

    def _on_press(self, event):
        """Determine if user is starting a new crop or dragging an existing corner."""
        corners = self._corners()
        r = type(self)._HANDLE_R + 4  # slightly larger hit area than drawn handle
        for i, (cx, cy) in enumerate(corners):
            if abs(event.x - cx) <= r and abs(event.y - cy) <= r:
                self._drag_corner = i
                return

        self._drag_corner = None
        self._drag_start = self._clamp(event.x, event.y)

        canvas = self._canvas
        if self._rect:
            canvas.delete(self._rect)
        canvas.delete("handle")
        self._rect = canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#00BFFF", width=2, dash=(4, 2)
        )

    def _on_drag(self, event):
        """Update the crop rect as the user drags, either resizing from a corner or creating a new rect."""
        x, y = self._clamp(event.x, event.y)
        canvas = self._canvas

        if self._drag_corner is not None and self._rect is not None:
            x1, y1, x2, y2 = canvas.coords(self._rect)
            if self._drag_corner == 0:
                x1, y1 = x, y  # top-left
            elif self._drag_corner == 1:
                x2, y1 = x, y  # top-right
            elif self._drag_corner == 2:
                x2, y2 = x, y  # bottom-right
            elif self._drag_corner == 3:
                x1, y2 = x, y  # bottom-left
            canvas.coords(self._rect, x1, y1, x2, y2)

        elif self._drag_start is not None:
            x0, y0 = self._drag_start
            canvas.coords(self._rect, x0, y0, x, y)

        self._draw_handles()

    def _on_release(self, event):
        """Clear drag state on mouse release."""
        self._drag_corner = None
        self._draw_handles()

    # ------------------------------------------------------------------ #
    # Drawing helpers                                                      #
    # ------------------------------------------------------------------ #

    def _corners(self):
        """Return (x, y) for each of the four corners of the current rect."""
        if self._rect is None:
            return []
        x1, y1, x2, y2 = self._canvas.coords(self._rect)
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    def _draw_handles(self):
        """Draw corner handles on the current rect."""
        canvas = self._canvas
        canvas.delete("handle")
        r = type(self)._HANDLE_R
        for cx, cy in self._corners():
            canvas.create_rectangle(
                cx - r, cy - r, cx + r, cy + r,
                fill="#00BFFF", outline="white", width=1, tags="handle"
            )

    def _draw_initial_crop(self, crop, orig_w, orig_h):
        """
        Convert an existing image-space crop tuple to canvas coords and draw it.
        Called once during start() if current_crop is not None.
        """
        ix1, iy1, ix2, iy2 = crop
        ox, oy = self._img_offset
        sx, sy = self._scale

        # image coords → canvas coords (inverse of confirm())
        cx1 = ix1 / sx + ox
        cy1 = iy1 / sy + oy
        cx2 = ix2 / sx + ox
        cy2 = iy2 / sy + oy

        self._rect = self._canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline="#00BFFF", width=2, dash=(4, 2)
        )
        self._draw_handles()

    # ------------------------------------------------------------------ #
    # Utilities                                                            #
    # ------------------------------------------------------------------ #

    def _clamp(self, x, y):
        """Clamp canvas coordinates to the displayed image area."""
        left, top, right, bottom = self._bounds
        return max(left, min(x, right)), max(top, min(y, bottom))

    def _teardown(self):
        """Unbind events, hide canvas, and clear state after confirming or cancelling."""
        canvas = self._canvas
        canvas.unbind("<ButtonPress-1>")
        canvas.unbind("<B1-Motion>")
        canvas.unbind("<ButtonRelease-1>")
        canvas.place_forget()
        self._root.unbind("<Return>")
        self._root.unbind("<Escape>")
        self._rect = None
        self._drag_start = None
        self._drag_corner = None
        self._photo = None
