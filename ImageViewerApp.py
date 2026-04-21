import tkinter as tk
from tkinter import ttk


#from handlers import ImageFunctions
from handlers import ImageFunctions
from settings_manager import load_settings, save_settings_json

# --- Root Window -------------------------------------------------------------

root = tk.Tk()
root.title("Simple Image Viewer")
root.rowconfigure(0, weight=1)  # image row expands
root.rowconfigure(1, weight=0)  # buttons row stays fixed
root.columnconfigure(0, weight=1)

# --- Widgets -----------------------------------------------------------------

#image_label = tk.Label(root)
#image_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

image_canvas = tk.Canvas(root, bg=root.cget("bg"), highlightthickness=0, bd=0)
image_canvas.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

status_label = tk.Label(root, text="", padx=20, pady=10)
status_label.grid(row=1, column=0, sticky="ew")

nav_frame = tk.Frame(root)
nav_frame.grid(row=2, column=0, pady=5)

bottom_bar = tk.Frame(root)
bottom_bar.grid(row=3, column=0, sticky="ew", padx=8, pady=4)

# --- Initializers ------------------------------------------------------------

settings = load_settings()
zoom_label = tk.Label(bottom_bar, text="100%", width=6)

image_functions = ImageFunctions(root, image_canvas, status_label, settings, zoom_label)
root.geometry(
    f'{settings["window_width"]}x{settings["window_height"]}+{settings["window_x"]}+{settings["window_y"]}')  # Restores Window Geometry

# --- Buttons -----------------------------------------------------------------

tk.Button(nav_frame, text="← Back", command=lambda: image_functions.navigate(-1)).pack(side=tk.LEFT, padx=10)
tk.Button(nav_frame, text="Next →", command=lambda: image_functions.navigate(1)).pack(side=tk.LEFT, padx=10)
tk.Button(nav_frame, text="Delete Image", command=image_functions.delete_image).pack(side=tk.LEFT, padx=10)
tk.Button(nav_frame, text="Mass Delete", command=image_functions.open_mass_delete).pack(side="left")

# --- Bottom Bar Buttons ------------------------------------------------------

tk.Button(bottom_bar, text="−", width=2,
          command=lambda: image_functions.set_zoom(image_functions._zoom_raw / 1.1)).pack(side="left")

tk.Button(bottom_bar, text="+", width=2,
          command=lambda: image_functions.set_zoom(image_functions._zoom_raw * 1.1)).pack(side="left")

# Reset button
tk.Button(bottom_bar, text="Reset", command=lambda:  image_functions.set_zoom_percent(100)).pack(side="left", padx=4)

zoom_slider = tk.Scale(
    bottom_bar,
    from_=10, to=800,
    resolution=1,
    orient="horizontal", length=200, showvalue=False,
    command=lambda val: image_functions.set_zoom_percent(float(val))
)

image_functions._zoom_slider = zoom_slider

zoom_slider.pack(side="left", padx=4)
zoom_label.pack(side="left", padx=4)


# --- Settings Menu -----------------------------------------------------------

def open_settings_menu():
    settings_win = tk.Toplevel(root)
    settings_win.title("Settings")
    settings_win.geometry("300x200")
    settings_win.grab_set()

    confirm_delete_var = tk.BooleanVar(value=settings["confirm_deletes"])

    def on_toggle_confirm_delete():
        settings["confirm_deletes"] = confirm_delete_var.get()
        image_functions.confirm_deletes = settings["confirm_deletes"]

    ttk.Label(settings_win, text="Delete Settings", font=("", 10, "bold")).pack(pady=(10, 0))
    ttk.Label(settings_win, text="Show a confirmation prompt before deleting images.").pack()
    ttk.Checkbutton(
        settings_win,
        text="Confirm Deletes",
        variable=confirm_delete_var,
        command=on_toggle_confirm_delete
    ).pack(pady=10)

    def save_settings():
        print("Confirm Deletes:", confirm_delete_var.get())
        save_settings_json(settings)
        settings_win.destroy()

    save_btn = ttk.Button(settings_win, text="Save", command=save_settings)
    save_btn.pack(pady=20)

# --- Label Manager --------------------------------------------------------------

def open_label_manager():
    win = tk.Toplevel(root)
    win.title("Label Manager")
    win.geometry("300x400")
    win.grab_set()

    # --- Input Row ---
    entry_var = tk.StringVar()
    entry_frame = ttk.Frame(win)
    entry_frame.pack(pady=10, padx=10, fill="x")

    entry = ttk.Entry(entry_frame, textvariable=entry_var)
    entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

    # --- Listbox ---
    listbox = tk.Listbox(win, selectmode=tk.SINGLE)
    listbox.pack(fill="both", expand=True, padx=10)

    # Load existing labels directly into listbox
    for label in settings.get("image_labels", []):
        listbox.insert(tk.END, label)

    # --- Actions ---
    def add_label(*_):
        text = entry_var.get().strip()
        if not text:
            return
        if text not in listbox.get(0, tk.END):
            listbox.insert(tk.END, text)
        entry_var.set("")

    entry.bind("<Return>", add_label)
    ttk.Button(entry_frame, text="Add", command=add_label).pack(side="left")

    def remove_label():
        sel = listbox.curselection()
        if sel:
            listbox.delete(sel[0])

    def remove_all():
        listbox.delete(0, tk.END)

    btn_frame = ttk.Frame(win)
    btn_frame.pack(pady=5)

    ttk.Button(btn_frame, text="Remove Selected", command=remove_label).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="Remove All", command=remove_all).pack(side="left", padx=5)

    # --- Save ---
    def on_confirm():
        settings["image_labels"] = list(listbox.get(0, tk.END))
        save_settings_json(settings)
        image_functions.apply_settings(settings)
        win.destroy()

    ttk.Button(win, text="Save", command=on_confirm).pack(pady=5)

# --- Closing Func ------------------------------------------------------------

def on_close():
    """Save window geometry and settings before closing."""
    geom = root.geometry()

    # Example: "800x600+100+100"
    w_h, x_y = geom.split("+", 1)
    width, height = map(int, w_h.split("x"))
    x, y = map(int, x_y.split("+"))

    settings.update({
        "window_width": width,
        "window_height": height,
        "window_x": x,
        "window_y": y,
    })

    save_settings_json(settings)
    root.destroy()

# --- Fast Delete Toggle ------------------------------------------------------

fast_delete_var = tk.BooleanVar(value=settings["fast_delete"])

def on_toggle_fast_delete():
    settings["fast_delete"] = fast_delete_var.get()
    save_settings_json(settings)
    image_functions.apply_settings(settings)

# --- Menu Bar ----------------------------------------------------------------

menubar = tk.Menu(root)

# --- File Menu ---------------------------------------------------------------

file_menu = tk.Menu(menubar, tearoff=0)
file_menu.add_command(label="Open Image", command=image_functions.open_image)
file_menu.add_separator()
file_menu.add_command(label="Save", command=image_functions.save_image_overwrite)
file_menu.add_command(label="Save As", command=image_functions.save_image)
file_menu.add_separator()
file_menu.add_command(label="Settings", command=open_settings_menu)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)

# --- Edit Menu --------------------------------------------------------------

edit_menu = tk.Menu(menubar, tearoff=0)
edit_menu.add_command(label="Undo", command=image_functions.undo)
edit_menu.add_command(label="Redo", command=image_functions.redo)
edit_menu.add_separator()
edit_menu.add_command(label="Crop Image", command=image_functions.start_crop_mode)
edit_menu.add_separator()
edit_menu.add_command(label="Rotate Image", command=image_functions.rotate_custom)

# --- Filter Menu -----------------------------------------------------------

filter_menu = tk.Menu(menubar, tearoff=0)

filter_lst = [("Grayscale", "grayscale"), ("Blur", "blur"), ("Sharpen", "sharpen"), ("Brightness", "brightness"), ("Contour", "contour"), ("Reset", "reset")]

for label, mode in filter_lst:
    filter_menu.add_command(label=label, command=lambda m=mode: image_functions.apply_filter(m))

# --- Image Menu ------------------------------------------------------------

image_menu = tk.Menu(menubar, tearoff=0)
image_menu.add_command(label="Information", command=image_functions.get_metadata)
image_menu.add_command(label="Rename Image", command=image_functions.rename_photo)


# --- Advanced Menu ---------------------------------------------------------

advanced_menu = tk.Menu(menubar, tearoff=0)
advanced_menu.add_command(label="Sort Duplicates", command=image_functions.check_duplicate)
advanced_menu.add_separator()
advanced_menu.add_command(label="Auto Sort From Labels", command=lambda: image_functions.auto_sort_images(False))
advanced_menu.add_command(label="Auto Sort NSFW", command=lambda: image_functions.auto_sort_images(True))
advanced_menu.add_command(label="Manage Labels", command=open_label_manager)
advanced_menu.add_separator()
advanced_menu.add_checkbutton(
    label="Fast Delete Mode",
    variable=fast_delete_var,
    command=on_toggle_fast_delete
)

# --- Help Menu ------------------------------------------------------------

help_menu = tk.Menu(menubar, tearoff=0)

# --- Menu Bar Cascades ----------------------------------------------------

menubar.add_cascade(label="File", menu=file_menu)
menubar.add_cascade(label="Edit", menu=edit_menu)
menubar.add_cascade(label="Filters", menu=filter_menu)
menubar.add_cascade(label="Image", menu=image_menu)
menubar.add_cascade(label="Advanced", menu=advanced_menu)
menubar.add_cascade(label="Help", menu=help_menu)

# --- Finalize ----------------------------------------------------------------

root.config(menu=menubar)
root.bind("<Configure>", image_functions.resize_image)
root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
