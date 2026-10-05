"""Image helpers: loading, alpha handling (PS2-safe), resizing, atomic saving."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def load_rgba(path: str | Path) -> tuple[np.ndarray, np.ndarray | None]:
    """Return (rgb uint8 HxWx3, alpha uint8 HxW or None)."""
    with Image.open(path) as im:
        im.load()
        has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        if has_alpha:
            arr = np.array(im.convert("RGBA"))  # writable copy (torch.from_numpy needs it)
            return np.ascontiguousarray(arr[..., :3]), np.ascontiguousarray(arr[..., 3])
        return np.array(im.convert("RGB")), None


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_TRAILER = b"IEND\xaeB`\x82"


def looks_complete(path: str | Path) -> bool:
    """Cheap completeness check so we never upscale a half-written dump.

    PNG files must end with the IEND chunk; for other formats we only require a non-empty file.
    """
    p = Path(path)
    try:
        size = p.stat().st_size
        if size == 0:
            return False
        if p.suffix.lower() != ".png":
            return True
        with open(p, "rb") as fh:
            if fh.read(8) != PNG_SIGNATURE:
                return size > 8  # not a PNG after all – let PIL decide
            fh.seek(-8, os.SEEK_END)
            return fh.read(8) == PNG_TRAILER
    except OSError:
        return False


def image_size(path: str | Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size  # (w, h)


def is_uniform(a: np.ndarray) -> bool:
    return bool(a.size) and bool((a == a.flat[0]).all())


def resize_alpha(alpha: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    """Upscale the alpha mask WITHOUT altering its value range.

    PCSX2 dumps store PS2 alpha (128 == fully opaque, 255 == 2.0). Replacements must keep
    exactly that convention, so a plain resampling (which keeps flat regions bit-exact) is
    the safe default. Uniform masks are short-circuited.
    """
    if is_uniform(alpha):
        return np.full((out_h, out_w), alpha.flat[0], dtype=np.uint8)
    im = Image.fromarray(alpha, mode="L").resize((out_w, out_h), Image.Resampling.BICUBIC)
    out = np.asarray(im, dtype=np.uint8)
    # Bicubic overshoots at hard edges; never leave the source range (e.g. > 128 would mean > 1.0 on PS2).
    return np.clip(out, int(alpha.min()), int(alpha.max()))


def alpha_to_model_input(alpha: np.ndarray) -> tuple[np.ndarray, float]:
    """Prepare alpha for running through an RGB model.

    Returns (rgb-like uint8 HxWx3, scale) where scale re-maps the model output back into the
    original PS2 alpha range. If the mask only uses the 0..128 range we stretch it to 0..255
    so the model sees full contrast, then divide back afterwards.
    """
    amax = int(alpha.max()) if alpha.size else 0
    scale = 255.0 / 128.0 if 0 < amax <= 128 else 1.0
    a = np.clip(alpha.astype(np.float32) * scale, 0, 255).astype(np.uint8)
    return np.repeat(a[..., None], 3, axis=2), scale


def alpha_from_model_output(out_rgb: np.ndarray, scale: float, lo: int = 0, hi: int = 255) -> np.ndarray:
    gray = out_rgb.astype(np.float32).mean(axis=2)
    return np.clip(np.rint(gray / scale), lo, hi).astype(np.uint8)


def resize_rgb(rgb: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    im = Image.fromarray(rgb, mode="RGB").resize((out_w, out_h), Image.Resampling.LANCZOS)
    return np.asarray(im, dtype=np.uint8)


def merge(rgb: np.ndarray, alpha: np.ndarray | None) -> Image.Image:
    if alpha is None:
        return Image.fromarray(rgb, mode="RGB")
    rgba = np.dstack((rgb, alpha))
    return Image.fromarray(rgba, mode="RGBA")


def save_png_atomic(img: Image.Image, dest: str | Path, compress_level: int = 1) -> None:
    """Write to a temp file in the same directory, then rename, so PCSX2 never sees a half file."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".texup_tmp")
    try:
        img.save(tmp, format="PNG", compress_level=int(compress_level))
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
