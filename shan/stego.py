"""Hide QFan payloads inside images (LSB pixels + PNG chunk / JPEG trailer)."""
from __future__ import annotations

import base64
import io
import struct
import zlib
from typing import Final

_STEGO_MAGIC: Final[bytes] = b"QFAN"
_STEGO_VERSION: Final[int] = 1
_PNG_CHUNK: Final[bytes] = b"qFnS"
_JPEG_TRAILER: Final[bytes] = b"\xff\xd9QFANSTEG"
# Tiny marker embedded in cover LSB when the full seal lives in the noise image.
COMPANION_MARKER: Final[bytes] = b"QFAN+NOISE"


def _pack_payload(raw: bytes) -> bytes:
    body = zlib.compress(raw, 9)
    return _STEGO_MAGIC + struct.pack(">HI", _STEGO_VERSION, len(body)) + body


def _unpack_payload(data: bytes) -> bytes:
    if len(data) < 10 or data[:4] != _STEGO_MAGIC:
        raise ValueError("missing or invalid steganographic payload")
    version, clen = struct.unpack(">HI", data[4:10])
    if version != _STEGO_VERSION:
        raise ValueError(f"unsupported stego version: {version}")
    body = data[10 : 10 + clen]
    if len(body) != clen:
        raise ValueError("truncated steganographic payload")
    return zlib.decompress(body)


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def _embed_png(png: bytes, payload: bytes) -> bytes:
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("stego cover must be PNG")
    packed = _pack_payload(payload)
    iend = png.rfind(b"IEND")
    if iend < 0:
        raise ValueError("invalid PNG (no IEND)")
    insert_at = iend - 4  # length field before IEND type
    chunk = _png_chunk(_PNG_CHUNK, packed)
    return png[:insert_at] + chunk + png[insert_at:]


def _extract_png(png: bytes) -> bytes:
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")
    pos = 8
    while pos + 12 <= len(png):
        length = struct.unpack(">I", png[pos : pos + 4])[0]
        ctype = png[pos + 4 : pos + 8]
        start = pos + 8
        end = start + length
        if end + 4 > len(png):
            break
        if ctype == _PNG_CHUNK:
            return _unpack_payload(png[start:end])
        pos = end + 4
    raise ValueError("no QFan stego chunk in PNG")


def _embed_jpeg(jpeg: bytes, payload: bytes) -> bytes:
    if not jpeg.startswith(b"\xff\xd8"):
        raise ValueError("stego cover must be JPEG")
    packed = _pack_payload(payload)
    eoi = jpeg.rfind(b"\xff\xd9")
    if eoi < 0:
        raise ValueError("invalid JPEG (no EOI)")
    trailer = jpeg[: eoi + 2] + _JPEG_TRAILER + struct.pack(">I", len(packed)) + packed
    return trailer


def _extract_jpeg(jpeg: bytes) -> bytes:
    marker = _JPEG_TRAILER
    idx = jpeg.rfind(marker)
    if idx < 0:
        raise ValueError("no QFan stego trailer in JPEG")
    start = idx + len(marker)
    if start + 4 > len(jpeg):
        raise ValueError("truncated JPEG stego trailer")
    (clen,) = struct.unpack(">I", jpeg[start : start + 4])
    body = jpeg[start + 4 : start + 4 + clen]
    if len(body) != clen:
        raise ValueError("truncated JPEG stego payload")
    return _unpack_payload(body)


def lsb_byte_capacity(cover: bytes) -> int:
    """Max packed payload bytes that fit in RGB LSB at cover dimensions."""
    Image = _require_pillow()
    with Image.open(io.BytesIO(cover)) as im:
        w, h = im.size
    return (w * h * 3 - 32) // 8


def packed_payload_size(raw: bytes) -> int:
    return len(_pack_payload(raw))


def _require_pillow():
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(
            "Steganography requires Pillow. Install with: pip install Pillow"
        ) from e
    return Image


def _embed_lsb(cover: bytes, payload: bytes) -> bytes:
    """Alter cover pixels (RGB LSB) to hide the payload — visible as the 'original' image."""
    Image = _require_pillow()
    packed = _pack_payload(payload)
    byte_len = len(packed)
    header_bits = 32  # big-endian byte count
    need_bits = header_bits + byte_len * 8

    with Image.open(io.BytesIO(cover)) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        capacity = w * h * 3
        if need_bits > capacity:
            raise ValueError(
                f"message too large for cover ({len(packed)} bytes, "
                f"capacity {capacity // 8} bytes at {w}×{h})"
            )
        pixels = list(rgb.getdata())
        bits: list[int] = []
        for shift in range(31, -1, -1):
            bits.append((byte_len >> shift) & 1)
        for byte in packed:
            for shift in range(7, -1, -1):
                bits.append((byte >> shift) & 1)
        out_pixels: list[tuple[int, int, int]] = []
        bit_i = 0
        for r, g, b in pixels:
            if bit_i < len(bits):
                r = (r & 0xFE) | bits[bit_i]
                bit_i += 1
            if bit_i < len(bits):
                g = (g & 0xFE) | bits[bit_i]
                bit_i += 1
            if bit_i < len(bits):
                b = (b & 0xFE) | bits[bit_i]
                bit_i += 1
            out_pixels.append((r, g, b))
        out = Image.new("RGB", (w, h))
        out.putdata(out_pixels)
        buf = io.BytesIO()
        fmt = "PNG" if cover.startswith(b"\x89PNG") else "JPEG"
        save_kw = {"format": fmt, "optimize": True}
        if fmt == "JPEG":
            save_kw["quality"] = 95
        out.save(buf, **save_kw)
        return buf.getvalue()


def _extract_lsb(image: bytes) -> bytes:
    Image = _require_pillow()
    with Image.open(io.BytesIO(image)) as im:
        pixels = list(im.convert("RGB").getdata())
    bits: list[int] = []
    for r, g, b in pixels:
        bits.append(r & 1)
        bits.append(g & 1)
        bits.append(b & 1)
    if len(bits) < 32:
        raise ValueError("image too small for stego header")
    length = 0
    for i in range(32):
        length = (length << 1) | bits[i]
    need_bits = 32 + length * 8
    if length <= 0 or need_bits > len(bits):
        raise ValueError("invalid stego length in image")
    raw = bytearray()
    for i in range(length):
        byte = 0
        for shift in range(8):
            byte = (byte << 1) | bits[32 + i * 8 + shift]
        raw.append(byte)
    return _unpack_payload(bytes(raw))


def embed_in_image(cover: bytes, payload: bytes) -> bytes:
    """Hide payload in cover — LSB when it fits, else PNG chunk / JPEG trailer."""
    try:
        return _embed_lsb(cover, payload)
    except ValueError as e:
        if "too large" not in str(e):
            raise
    except RuntimeError:
        pass
    if cover.startswith(b"\x89PNG\r\n\x1a\n"):
        return _embed_png(cover, payload)
    if cover.startswith(b"\xff\xd8"):
        return _embed_jpeg(cover, payload)
    raise ValueError("stego requires PNG or JPEG cover image")


def extract_from_image(image: bytes) -> bytes:
    """Extract hidden payload — tries LSB pixels, then PNG chunk / JPEG trailer."""
    try:
        return _extract_lsb(image)
    except (RuntimeError, ValueError, IndexError):
        pass
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        return _extract_png(image)
    if image.startswith(b"\xff\xd8"):
        return _extract_jpeg(image)
    raise ValueError("no QFan hidden message in image")


def embed_sealed_in_cover(cover_b64: str, payload: bytes) -> str:
    """Embed raw payload bytes into cover image; return stego image base64."""
    cover = base64.b64decode(cover_b64.strip())
    out = embed_in_image(cover, payload)
    return base64.b64encode(out).decode("ascii")


def extract_payload_from_image(stego_b64: str) -> bytes:
    """Extract raw hidden payload bytes from a stego image."""
    image = base64.b64decode(stego_b64.strip())
    return extract_from_image(image)


def extract_sealed_from_image(stego_b64: str, *, companion_b64: str = "") -> str:
    """Pull sealed envelope (base64) out of a stego image (and optional noise companion)."""
    payload = extract_payload_from_image(stego_b64)
    if payload == COMPANION_MARKER:
        if not companion_b64:
            raise ValueError(
                "cover holds a pointer only — also need the noise image from panel 2"
            )
        payload = extract_payload_from_image(companion_b64)
    return base64.b64encode(payload).decode("ascii")
