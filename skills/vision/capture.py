from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import mss
from PIL import Image

from celestia_core.config import ROOT, get


def _temp_dir() -> Path:
    rel = get("vision.temp_dir", "temp/vision")
    d = Path(rel) if Path(rel).is_absolute() else Path(ROOT) / rel
    d.mkdir(parents=True, exist_ok=True)
    return d


def _new_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return _temp_dir() / f"screen_{stamp}.png"


def _resize(img: Image.Image) -> Image.Image:
    max_edge = int(get("vision.max_edge_px", 1280))
    w, h = img.size
    if max(w, h) <= max_edge:
        return img
    scale = max_edge / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)


def _save(img: Image.Image) -> Path:
    out = _new_path()
    _resize(img).save(out, format="PNG", compress_level=1)
    return out


def capture_fullscreen() -> Path:
    with mss.mss() as sct:
        mon = sct.monitors[0]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return _save(img)


def capture_bbox(left: int, top: int, width: int, height: int) -> Path:
    if width < 8 or height < 8:
        raise ValueError("Selection too small")
    with mss.mss() as sct:
        region = {"left": left, "top": top, "width": width, "height": height}
        shot = sct.grab(region)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return _save(img)


def capture_active_window() -> Path:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return capture_fullscreen()

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return capture_fullscreen()

    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width < 8 or height < 8:
        return capture_fullscreen()
    return capture_bbox(rect.left, rect.top, width, height)


def cleanup_old_files():
    minutes = int(get("vision.delete_after_minutes", 15))
    cutoff = time.time() - minutes * 60
    for p in _temp_dir().glob("screen_*.png"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass
