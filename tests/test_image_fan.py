"""QFan image seal / open round-trip."""
from __future__ import annotations

import base64

import pytest

pytest.importorskip("PIL")

from shan.image_fan import (
    bytes_to_noise_png,
    fan_open_image,
    fan_seal_image,
    img_data_uri,
    sample_image_b64,
)


def test_sample_round_trip():
    plain = sample_image_b64()
    sealed = fan_seal_image(plain, "test-key", ribs=8, ig_layout="square")
    assert sealed["sealed"]
    assert sealed["noise_b64"]
    assert sealed["cover_b64"]
    opened = fan_open_image(sealed["sealed"], "test-key")
    assert opened == sealed["cover_b64"]


def test_fan_qfan_round():
    from shan.image_fan import fan_qfan_round

    plain = sample_image_b64()
    r = fan_qfan_round(plain, "test-key", ribs=8, ig_layout="square")
    assert r["match_ok"] == 1
    assert r["sealed"]
    assert r["noise_b64"]
    assert r["stego_b64"]
    assert r["ig_stego_b64"]
    assert r["opened_b64"] == r["cover_b64"]


def test_noise_png_and_data_uri():
    raw = base64.b64decode(sample_image_b64())
    png = bytes_to_noise_png(raw)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    uri = img_data_uri("image/png", base64.b64encode(png).decode())
    assert uri.startswith("data:image/png;base64,")
