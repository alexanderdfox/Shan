"""Steganography + QFan image round-trip."""
from __future__ import annotations

import base64

import pytest

pytest.importorskip("PIL")

from shan.image_fan import (
    fan_qfan_round,
    fan_seal_image,
    fan_stego_hide,
    fan_stego_reveal,
    sample_image_b64,
)
from shan.stego import embed_in_image, extract_from_image


def test_png_chunk_round_trip():
    cover = base64.b64decode(sample_image_b64())
    payload = b'{"test": true, "cipher": [1, 2, 3]}'
    stego = embed_in_image(cover, payload)
    assert stego != cover
    assert extract_from_image(stego) == payload


def test_fan_stego_qfan_round_trip():
    plain = sample_image_b64()
    r = fan_qfan_round(plain, "stego-key", ribs=8, ig_layout="square")
    assert r["stego_b64"]
    assert r["ig_stego_b64"]
    assert r["noise_b64"]
    assert r["match_ok"] == 1
    assert r["opened_b64"] == r["cover_b64"]
    assert base64.b64decode(r["stego_b64"]) != base64.b64decode(r["cover_b64"])
    assert base64.b64decode(r["stego_b64"])[:8] == b"\x89PNG\r\n\x1a\n"


def test_large_seal_uses_noise_companion():
    """Seals larger than cover LSB capacity embed in the noise PNG instead."""
    import secrets

    from shan.fan_cipher import FanEnvelope
    from shan.image_fan import prepare_instagram_cover
    from shan.stego import COMPANION_MARKER, extract_payload_from_image

    cover = prepare_instagram_cover(sample_image_b64(), "square")
    pack = fan_seal_image(cover, "big-key", ribs=8, ig_layout="square")
    # Synthetic oversized envelope (simulates a max-size upload ciphertext).
    env = FanEnvelope.from_json(base64.b64decode(pack["sealed"]).decode())
    big = FanEnvelope(
        ribs=env.ribs,
        nonce=env.nonce,
        span_remaining=env.span_remaining,
        half_bits=env.half_bits,
        data=env.data + secrets.token_bytes(600_000),
    )
    sealed = base64.b64encode(big.to_json().encode()).decode()
    stego, noise = fan_stego_hide(cover, sealed, pack["noise_b64"])
    assert extract_payload_from_image(stego) == COMPANION_MARKER
    assert extract_payload_from_image(noise) != COMPANION_MARKER


def test_stego_reveal_wrong_key_fails_match():
    plain = sample_image_b64()
    sealed = fan_seal_image(plain, "key-a", ribs=8)["sealed"]
    stego, noise = fan_stego_hide(plain, sealed)
    opened = fan_stego_reveal(stego, "key-b", noise)
    assert opened != plain
