"""Instagram export dimensions."""
from __future__ import annotations

import base64

import pytest

from shan.image_fan import (
    export_instagram_jpeg,
    prepare_instagram_cover,
    sample_image_b64,
)
from shan.instagram import fit_for_instagram, target_size

pytest.importorskip("PIL")


def test_instagram_square_dimensions():
    raw = base64.b64decode(sample_image_b64())
    out = fit_for_instagram(raw, "square", as_jpeg=True)
    assert out.startswith(b"\xff\xd8")
    from PIL import Image
    import io

    im = Image.open(io.BytesIO(out))
    assert im.size == target_size("square")


def test_prepare_cover_round_trip_b64():
    cover = prepare_instagram_cover(sample_image_b64(), "square")
    assert len(cover) > 100
    jpeg = export_instagram_jpeg(cover, "square")
    assert jpeg
