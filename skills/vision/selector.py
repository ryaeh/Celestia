"""Drag a rectangle to select screen region (Windows)."""

from __future__ import annotations


def select_region() -> tuple[int, int, int, int]:
    import tkinter as tk

    box = {"x1": 0, "y1": 0, "x2": 0, "y2": 0, "done": False}

    root = tk.Tk()
    root.withdraw()
    overlay = tk.Toplevel(root)
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-topmost", True)
    overlay.attributes("-alpha", 0.35)
    overlay.configure(bg="black", cursor="cross")
    overlay.overrideredirect(True)

    canvas = tk.Canvas(overlay, cursor="cross", bg="grey", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    rect_id = None
    start = {"x": 0, "y": 0}

    def on_press(event):
        nonlocal rect_id
        start["x"], start["y"] = event.x, event.y
        if rect_id:
            canvas.delete(rect_id)
        rect_id = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#00aaff", width=2
        )

    def on_drag(event):
        if rect_id:
            canvas.coords(rect_id, start["x"], start["y"], event.x, event.y)

    def on_release(event):
        box["x1"], box["y1"] = start["x"], start["y"]
        box["x2"], box["y2"] = event.x, event.y
        box["done"] = True
        overlay.destroy()
        root.quit()

    def on_escape(_event=None):
        box["done"] = False
        overlay.destroy()
        root.quit()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    overlay.bind("<Escape>", on_escape)

    print("[vision] Drag a rectangle. Esc to cancel.")
    root.mainloop()
    root.destroy()

    if not box["done"]:
        raise RuntimeError("Screen selection cancelled")

    x1, y1 = min(box["x1"], box["x2"]), min(box["y1"], box["y2"])
    x2, y2 = max(box["x1"], box["x2"]), max(box["y1"], box["y2"])
    return x1, y1, x2 - x1, y2 - y1
