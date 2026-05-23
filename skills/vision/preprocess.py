"""Image prep for text/terminal screenshots."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


def enhance_for_text(path: Path) -> Path:
    """Boost contrast/size so vision models read terminal text better."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    min_edge = min(w, h)
    if min_edge < 900:
        scale = 900 / min_edge
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Sharpness(img).enhance(1.4)
    out = path.with_name(path.stem + "_text.png")
    img.save(out, format="PNG", compress_level=1)
    return out
