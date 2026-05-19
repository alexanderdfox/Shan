"""QFan encryption for images — noise preview + data URIs for SSR."""
from __future__ import annotations

import base64
import struct
import zlib
from typing import Any

from shan.fan_cipher import DEFAULT_RIBS, decrypt_bytes, encrypt, fan_audit_summary
from shan.instagram import fit_for_instagram, layout_label, normalize_layout
from shan.stego import (
    COMPANION_MARKER,
    embed_sealed_in_cover,
    extract_payload_from_image,
    packed_payload_size,
)

# Instagram feed (square) — default export size
IG_LAYOUT_DEFAULT = "square"


def _make_sample_png(width: int = 512, height: int = 512) -> bytes:
    """Small color PNG used as the default original image."""
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)  # filter byte
        for x in range(width):
            t = (x + y) / max(width + height - 2, 1)
            pixels.extend(
                (
                    int(40 + 180 * t) % 256,
                    int(90 + 120 * (1 - t)) % 256,
                    int(160 + 80 * t) % 256,
                )
            )

    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(pixels), 9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


SAMPLE_PNG_B64 = base64.b64encode(_make_sample_png()).decode("ascii")

MAX_IMAGE_BYTES = 2 * 1024 * 1024


def detect_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def prepare_instagram_cover(plain_b64: str, layout: str | None = None) -> str:
    """Resize/crop cover to Instagram dimensions (PNG, for stego + encrypt)."""
    layout = normalize_layout(layout or IG_LAYOUT_DEFAULT)
    raw = base64.b64decode(plain_b64.strip())
    fitted = fit_for_instagram(raw, layout, as_jpeg=False)
    return base64.b64encode(fitted).decode("ascii")


def bytes_to_noise_png(data: bytes, width: int = 0, height: int = 0) -> bytes:
    """Visualize ciphertext bytes as a grayscale PNG."""
    if not data:
        data = b"\x00"
    if width <= 0:
        width = max(64, min(1080, int(len(data) ** 0.5) or 128))
    width = min(1080, max(32, width))
    height = height if height > 0 else (len(data) + width - 1) // width
    pixels = bytearray(width * height)
    for i in range(len(pixels)):
        pixels[i] = data[i] if i < len(data) else 0

    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw_rows = b""
    for y in range(height):
        row_start = y * width
        raw_rows += b"\x00" + bytes(pixels[row_start : row_start + width])
    compressed = zlib.compress(raw_rows, 9)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def noise_for_instagram(cipher_bytes: bytes, layout: str | None = None) -> bytes:
    """QFan noise map cropped to Instagram dimensions."""
    from shan.instagram import target_size

    layout = normalize_layout(layout or IG_LAYOUT_DEFAULT)
    tw, th = target_size(layout)
    rough = bytes_to_noise_png(cipher_bytes, width=tw)
    return fit_for_instagram(rough, layout, as_jpeg=False)


def export_instagram_jpeg(image_b64: str, layout: str | None = None) -> str:
    """JPEG export at Instagram size (for posting to the feed)."""
    layout = normalize_layout(layout or IG_LAYOUT_DEFAULT)
    raw = base64.b64decode(image_b64.strip())
    jpeg = fit_for_instagram(raw, layout, as_jpeg=True)
    return base64.b64encode(jpeg).decode("ascii")


def img_data_uri(mime: str, b64_data: str) -> str:
    mime = (mime or "image/png").split(";")[0].strip() or "image/png"
    if not b64_data:
        return ""
    return f"data:{mime};base64,{b64_data.strip()}"


def fan_seal_image(
    plain_b64: str,
    key: str,
    ribs: int = DEFAULT_RIBS,
    *,
    ig_layout: str | None = None,
) -> dict[str, Any]:
    """Encrypt Instagram-sized cover → sealed envelope + noise preview."""
    layout = normalize_layout(ig_layout or IG_LAYOUT_DEFAULT)
    cover_b64 = prepare_instagram_cover(plain_b64, layout)
    raw = base64.b64decode(cover_b64)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"image too large (max {MAX_IMAGE_BYTES // 1024} KiB)")
    env = encrypt(raw, key, ribs=ribs)
    sealed = base64.b64encode(env.to_json().encode("utf-8")).decode("ascii")
    noise = base64.b64encode(noise_for_instagram(env.data, layout)).decode("ascii")
    return {
        "sealed": sealed,
        "noise_b64": noise,
        "cover_b64": cover_b64,
        "ig_layout": layout,
        "summary": fan_audit_summary(sealed) + f" ig={layout_label(layout)}",
        "size": len(raw),
    }


def fan_noise_from_sealed(sealed: str, *, ig_layout: str | None = None) -> str:
    """Noise-preview PNG (base64) from a sealed envelope (no key required)."""
    from shan.fan_cipher import _parse_envelope

    layout = normalize_layout(ig_layout or IG_LAYOUT_DEFAULT)
    env = _parse_envelope(base64.b64decode(sealed.strip()).decode("utf-8"))
    return base64.b64encode(noise_for_instagram(env.data, layout)).decode("ascii")


def fan_open_image(sealed: str, key: str) -> str:
    """Decrypt to original image bytes (base64)."""
    text = sealed.strip()
    if not text.startswith("{"):
        text = base64.b64decode(text).decode("utf-8")
    plain = decrypt_bytes(text, key)
    return base64.b64encode(plain).decode("ascii")


def sample_image_b64() -> str:
    return SAMPLE_PNG_B64


def _sealed_payload_bytes(sealed: str) -> bytes:
    """Compact binary QFan envelope (smaller than JSON for stego)."""
    from shan.fan_cipher import FanEnvelope

    text = sealed.strip()
    if not text.startswith("{"):
        text = base64.b64decode(text).decode("utf-8")
    return FanEnvelope.from_json(text).to_bytes()


def fan_stego_hide(
    cover_b64: str, sealed: str, noise_b64: str = ""
) -> tuple[str, str]:
    """
    Hide sealed QFan data in the cover (LSB pixels when it fits).

    Large seals use split mode: tiny marker in cover LSB + full payload in the
    noise image (PNG chunk). Returns (stego_cover_b64, noise_b64).
    """
    cover = base64.b64decode(cover_b64.strip())
    payload = _sealed_payload_bytes(sealed)
    if packed_payload_size(payload) <= _lsb_limit(cover):
        stego = embed_sealed_in_cover(cover_b64, payload)
        return stego, noise_b64
    if not noise_b64:
        cap = _lsb_limit(cover)
        raise ValueError(
            f"encrypted seal too large for cover LSB ({packed_payload_size(payload)} bytes, "
            f"capacity {cap} bytes) — noise image required"
        )
    noise_stego = embed_sealed_in_cover(noise_b64, payload)
    cover_stego = embed_sealed_in_cover(cover_b64, COMPANION_MARKER)
    return cover_stego, noise_stego


def _lsb_limit(cover: bytes) -> int:
    from shan.stego import lsb_byte_capacity

    return lsb_byte_capacity(cover)


def fan_stego_reveal(stego_b64: str, key: str, noise_b64: str = "") -> str:
    """Extract hidden envelope from stego (+ noise if split) and QFan-decrypt."""
    payload = extract_payload_from_image(stego_b64)
    if payload == COMPANION_MARKER:
        if not noise_b64:
            raise ValueError(
                "cover only has a pointer — upload or keep the noise image (panel 2)"
            )
        payload = extract_payload_from_image(noise_b64)
    plain = decrypt_bytes(payload, key)
    return base64.b64encode(plain).decode("ascii")


def fan_qfan_round(
    plain_b64: str,
    key: str,
    ribs: int = DEFAULT_RIBS,
    *,
    ig_layout: str | None = None,
) -> dict[str, Any]:
    """
    Resize cover for Instagram → QFan encrypt → noise → stego → reveal round-trip.
    """
    layout = normalize_layout(ig_layout or IG_LAYOUT_DEFAULT)
    cover_b64 = prepare_instagram_cover(plain_b64.strip(), layout)
    sealed_pack = fan_seal_image(cover_b64, key, ribs=ribs, ig_layout=layout)
    stego_b64, noise_b64 = fan_stego_hide(
        sealed_pack["cover_b64"],
        sealed_pack["sealed"],
        sealed_pack["noise_b64"],
    )
    ig_stego_b64 = export_instagram_jpeg(stego_b64, layout)
    opened_b64 = fan_stego_reveal(stego_b64, key, noise_b64)
    return {
        "sealed": sealed_pack["sealed"],
        "noise_b64": noise_b64,
        "cover_b64": cover_b64,
        "stego_b64": stego_b64,
        "ig_stego_b64": ig_stego_b64,
        "ig_layout": layout,
        "summary": sealed_pack["summary"] + " stego=embedded",
        "opened_b64": opened_b64,
        "match_ok": 1 if opened_b64 == cover_b64 else 0,
    }
