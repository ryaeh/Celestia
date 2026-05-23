"""Atlas-controlled screenshot preview (closes after confirm)."""

from __future__ import annotations

import threading
import time
from pathlib import Path


class PreviewWindow:
    def __init__(self, image_path: Path):
        import tkinter as tk
        from PIL import Image, ImageTk

        self._alive = True
        self.root = tk.Tk()
        self.root.withdraw()
        self.top = tk.Toplevel(self.root)
        self.top.title("Atlas — screenshot preview")
        self.top.attributes("-topmost", True)

        img = Image.open(image_path)
        max_w, max_h = 900, 700
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        tk.Label(self.top, image=self._photo).pack(padx=8, pady=8)
        tk.Label(
            self.top,
            text="Confirm in the terminal: yes / no",
            font=("Segoe UI", 10),
        ).pack(pady=(0, 8))

        self._pump = threading.Thread(target=self._pump_loop, daemon=True)
        self._pump.start()
        self.root.update()

    def _pump_loop(self):
        while self._alive:
            try:
                self.root.update()
            except Exception:
                break
            time.sleep(0.05)

    def close(self):
        self._alive = False
        time.sleep(0.1)
        try:
            self.top.destroy()
            self.root.destroy()
        except Exception:
            pass


def open_preview(image_path: Path) -> PreviewWindow | None:
    try:
        return PreviewWindow(image_path)
    except Exception as e:
        print(f"[vision] inline preview failed ({e}), opening default viewer")
        try:
            import os

            os.startfile(str(image_path))
        except OSError:
            pass
        return None
