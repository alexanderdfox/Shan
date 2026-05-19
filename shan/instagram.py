"""Resize images for Instagram feed posts (1080px-wide presets)."""
from __future__ import annotations

import io
from typing import Final, Literal

Layout = Literal["square", "portrait", "landscape"]

# Instagram feed safe zones (px)
IG_SQUARE: Final[tuple[int, int]] = (1080, 1080)
IG_PORTRAIT: Final[tuple[int, int]] = (1080, 1350)
IG_LANDSCAPE: Final[tuple[int, int]] = (1080, 566)
IG_MAX_BYTES: Final[int] = 8 * 1024 * 1024
IG_JPEG_QUALITY: Final[int] = 88

_LAYOUTS: dict[str, tuple[int, int]] = {
    "square": IG_SQUARE,
    "portrait": IG_PORTRAIT,
    "landscape": IG_LANDSCAPE,
}


def normalize_layout(layout: str | None) -> Layout:
    key = (layout or "square").strip().lower()
    if key in _LAYOUTS:
        return key  # type: ignore[return-value]
    return "square"


def target_size(layout: str | None) -> tuple[int, int]:
    return _LAYOUTS[normalize_layout(layout)]


def _require_pillow():
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(
            "Instagram image sizing requires Pillow. "
            "Install with: pip install Pillow  (or pip install -e '.[dev]')"
        ) from e
    return Image


def _crop_cover(img, target_w: int, target_h: int):
    Image = _require_pillow()
    img = img.convert("RGB")
    src_w, src_h = img.size
    if src_w < 1 or src_h < 1:
        raise ValueError("invalid image dimensions")
    scale = max(target_w / src_w, target_h / src_h)
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resample = getattr(Image, "Resampling", Image).LANCZOS
    img = img.resize((new_w, new_h), resample)
    left = max(0, (new_w - target_w) // 2)
    top = max(0, (new_h - target_h) // 2)
    return img.crop((left, top, left + target_w, top + target_h))


def fit_for_instagram(
    image: bytes,
    layout: str | None = "square",
    *,
    as_jpeg: bool = True,
) -> bytes:
    """Center-crop + resize to an Instagram aspect; return JPEG or PNG bytes."""
    Image = _require_pillow()
    target_w, target_h = target_size(layout)
    with Image.open(io.BytesIO(image)) as im:
        out = _crop_cover(im, target_w, target_h)
        buf = io.BytesIO()
        if as_jpeg:
            out.save(buf, format="JPEG", quality=IG_JPEG_QUALITY, optimize=True)
            mime_hint = "image/jpeg"
        else:
            out.save(buf, format="PNG", optimize=True)
            mime_hint = "image/png"
    data = buf.getvalue()
    if len(data) > IG_MAX_BYTES:
        raise ValueError(
            f"Instagram export exceeds {IG_MAX_BYTES // (1024 * 1024)} MiB — "
            "use a smaller source image"
        )
    del mime_hint
    return data


def layout_label(layout: str | None) -> str:
    w, h = target_size(layout)
    return f"{w}×{h}"
