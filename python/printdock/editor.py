import io
import logging
import math
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageEnhance, ImageTk

from .crop import Crop
from .imaging import encode_crop, initial_crop, load_image

logger = logging.getLogger(__name__)
MAX_ZOOM = 8.0
CANVAS_MARGIN = 36


class CropEditor:
    def __init__(self, root: tk.Tk, image: Image.Image, crop: Crop, *, quality: int, action: str):
        self.root, self.image, self.crop = root, image, crop
        self.quality = quality
        self.result: bytes | None = None
        self.jpeg: bytes | None = None
        self.pending = None
        self.drag_origin = None
        self.frame = (0, 0, 1, 1)
        self.context = image.copy()
        self.context.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        self.zoom_value = tk.StringVar(value=f"{crop.zoom * 100:.2f}")
        self.grid = tk.BooleanVar(value=True)
        self.details = tk.StringVar()
        root.title("Print Dock — Choose crop")
        root.geometry(f"{min(1000, root.winfo_screenwidth() - 80)}x{min(880, root.winfo_screenheight() - 100)}")
        root.minsize(620, 540)
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        panel = ttk.Frame(root, padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Choose your crop", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(panel, text="Drag the photo · Scroll to zoom · Arrow keys nudge 1 print pixel (Shift: 10)").pack(anchor="w", pady=(4, 12))
        self.canvas = tk.Canvas(panel, background="#20242b", highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True)
        controls = ttk.Frame(panel)
        controls.pack(fill="x", pady=12)
        ttk.Button(controls, text="Fill frame", command=lambda: self.reset("cover")).pack(side="left")
        ttk.Button(controls, text="Fit whole photo", command=lambda: self.reset("contain")).pack(side="left", padx=6)
        ttk.Button(controls, text="Switch orientation", command=self.switch_orientation).pack(side="left")
        ttk.Checkbutton(controls, text="Thirds", variable=self.grid, command=self.schedule).pack(side="right")
        zoom_row = ttk.Frame(panel)
        zoom_row.pack(fill="x")
        ttk.Label(zoom_row, text="Zoom %").pack(side="left")
        self.zoom_input = ttk.Spinbox(zoom_row, from_=self.crop.fit_zoom * 100, to=MAX_ZOOM * 100, increment=1, width=8, textvariable=self.zoom_value, command=self.typed_zoom)
        self.zoom_input.pack(side="left", padx=8)
        self.zoom_input.bind("<Return>", self.typed_zoom)
        self.zoom_input.bind("<FocusOut>", self.typed_zoom)
        self.slider = ttk.Scale(zoom_row, from_=self.crop.fit_zoom * 100, to=MAX_ZOOM * 100, command=self.slider_zoom)
        self.slider.set(self.crop.zoom * 100)
        self.slider.pack(side="left", fill="x", expand=True)
        ttk.Label(panel, textvariable=self.details).pack(anchor="w", pady=(10, 4))
        footer = ttk.Frame(panel)
        footer.pack(fill="x", pady=(8, 0))
        hint = "Wake the printer before continuing." if action == "Print" else "Save the selected crop without connecting to the printer."
        ttk.Label(footer, text=hint).pack(side="left")
        ttk.Button(footer, text=action, command=self.accept).pack(side="right")
        ttk.Button(footer, text="Cancel", command=root.destroy).pack(side="right", padx=8)
        self.canvas.bind("<Configure>", self.schedule)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Button-4>", lambda event: self.wheel(event, 1))
        self.canvas.bind("<Button-5>", lambda event: self.wheel(event, -1))
        for key, delta in {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}.items():
            self.canvas.bind(f"<{key}>", lambda event, delta=delta: self.nudge(event, delta))
        root.bind("<Escape>", lambda event: root.destroy())
        self.canvas.focus_set()

    def schedule(self, event=None):
        if self.pending is None:
            self.pending = self.root.after(16, self.redraw)

    def update_crop(self, crop: Crop):
        self.crop = crop.clamped()
        self.zoom_value.set(f"{self.crop.zoom * 100:.2f}")
        self.slider.configure(from_=self.crop.fit_zoom * 100)
        self.zoom_input.configure(from_=self.crop.fit_zoom * 100)
        self.slider.set(self.crop.zoom * 100)
        self.schedule()

    def reset(self, fit):
        crop = Crop(self.image.size, self.crop.landscape)
        self.update_crop(crop.zoomed(crop.fit_zoom) if fit == "contain" else crop)

    def switch_orientation(self):
        crop = replace(self.crop, landscape=not self.crop.landscape)
        self.update_crop(crop.zoomed(max(crop.fit_zoom, crop.zoom)))

    def set_zoom(self, value, anchor=(0.5, 0.5)):
        value = min(MAX_ZOOM, max(self.crop.fit_zoom, value))
        if value != self.crop.zoom:
            self.update_crop(self.crop.zoomed(value, anchor))

    def typed_zoom(self, event=None):
        try:
            text = self.zoom_value.get()
            # Don't quantize a wheel/slider zoom to its rounded display value.
            value = self.crop.zoom if text == f"{self.crop.zoom * 100:.2f}" else float(text) / 100
            if not math.isfinite(value):
                raise ValueError
        except ValueError:
            self.zoom_value.set(f"{self.crop.zoom * 100:.2f}")
        else:
            self.set_zoom(value)
            self.zoom_value.set(f"{self.crop.zoom * 100:.2f}")
        return "break" if event and event.keysym == "Return" else None

    def slider_zoom(self, value):
        self.set_zoom(float(value) / 100)

    def start_drag(self, event):
        self.canvas.focus_set()
        self.drag_origin = (event.x, event.y)

    def drag(self, event):
        if self.drag_origin is None:
            return
        x0, _, x1, _ = self.frame
        left, _, right, _ = self.crop.box
        scale = (right - left) / (x1 - x0)
        dx, dy = event.x - self.drag_origin[0], event.y - self.drag_origin[1]
        self.drag_origin = (event.x, event.y)
        self.update_crop(self.crop.moved(-dx * scale, -dy * scale))

    def wheel(self, event, direction=None):
        self.canvas.focus_set()
        direction = direction if direction is not None else event.delta / 120
        x0, y0, x1, y1 = self.frame
        anchor = (min(1, max(0, (event.x - x0) / (x1 - x0))), min(1, max(0, (event.y - y0) / (y1 - y0))))
        self.set_zoom(self.crop.zoom * 1.08 ** direction, anchor)

    def nudge(self, event, delta):
        left, _, right, _ = self.crop.box
        step = (right - left) / self.crop.target_size[0] * (10 if event.state & 1 else 1)
        self.update_crop(self.crop.moved(-delta[0] * step, -delta[1] * step))
        return "break"

    def redraw(self):
        self.pending = None
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if min(width, height) <= 2 * CANVAS_MARGIN:
            return
        tw, th = self.crop.target_size
        scale = min((width - 2 * CANVAS_MARGIN) / tw, (height - 2 * CANVAS_MARGIN) / th)
        fw, fh = round(tw * scale), round(th * scale)
        x0, y0 = (width - fw) // 2, (height - fh) // 2
        self.frame = (x0, y0, x0 + fw, y0 + fh)
        left, top, right, bottom = self.crop.box
        context_scale = self.context.width / self.image.width
        sx, sy = (right - left) / fw, (bottom - top) / fh
        surroundings = self.context.transform((width, height), Image.Transform.AFFINE,
            (sx * context_scale, 0, (left - x0 * sx) * context_scale,
             0, sy * context_scale, (top - y0 * sy) * context_scale),
            Image.Resampling.BILINEAR, fillcolor="#20242b")
        surroundings = ImageEnhance.Brightness(surroundings).enhance(0.28)
        # The crop displayed inside the frame is decoded from the exact JPEG
        # returned on approval, including its final encoding and orientation.
        self.jpeg = encode_crop(self.image, self.crop, quality=self.quality)
        with Image.open(io.BytesIO(self.jpeg)) as encoded:
            preview = encoded.transpose(Image.Transpose.ROTATE_270) if self.crop.landscape else encoded.copy()
        surroundings.paste(preview.resize((fw, fh), Image.Resampling.LANCZOS), (x0, y0))
        self.photo = ImageTk.PhotoImage(surroundings, master=self.root)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.create_rectangle(*self.frame, outline="white", width=2)
        if self.grid.get():
            for fraction in (1 / 3, 2 / 3):
                self.canvas.create_line(x0 + fw * fraction, y0, x0 + fw * fraction, y0 + fh, fill="#dddddd", dash=(3, 5))
                self.canvas.create_line(x0, y0 + fh * fraction, x0 + fw, y0 + fh * fraction, fill="#dddddd", dash=(3, 5))
        quality_hint = "  |  Upscaling source pixels" if right - left < tw else ""
        self.details.set(f"Frame {tw}:{th}  |  Source crop ({left:.2f}, {top:.2f}) → ({right:.2f}, {bottom:.2f}) px{quality_hint}")

    def accept(self):
        self.typed_zoom()
        if self.pending is not None:
            self.root.after_cancel(self.pending)
            self.pending = None
        self.redraw()
        self.result = self.jpeg
        logger.info("Crop approved: source box %s, landscape=%s, JPEG=%d bytes", self.crop.box, self.crop.landscape, len(self.result))
        self.root.destroy()


def edit_jpeg(path: Path, *, fit="cover", orientation="auto", quality=98, action="Print") -> bytes | None:
    image = load_image(path)
    root = tk.Tk()
    errors = []
    def callback_error(kind, error, traceback):
        errors.append(error)
        root.destroy()
    root.report_callback_exception = callback_error
    try:
        editor = CropEditor(root, image, initial_crop(image, fit=fit, orientation=orientation), quality=quality, action=action)
        root.mainloop()
        if errors:
            raise errors[0]
        return editor.result
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
