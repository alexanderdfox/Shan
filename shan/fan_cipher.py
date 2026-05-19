"""
QFan — Half-Truth Quantum Fan cipher (v1).

Uses the Shàn fan model:

- **Ribs** — N parallel key streams (HMAC-SHA256 tranches), like fan blades.
- **Half (½)** — when ribs disagree on a keystream bit, that position is
  *in superposition* until decrypt observes with the same key material.
- **Span** — the master key lives in a contracting ``Span``; each block
  ``observe`` shrinks ``remaining`` (λ) and decrements ``uses_left``.

Envelope: base64 JSON or binary (MAGIC ``QFAN1``).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
from dataclasses import dataclass

from shan.values import Span, Truth

MAGIC = b"QFAN1"
VERSION = 1
DEFAULT_RIBS = 8
BLOCK_SIZE = 32
LAMBDA = 0.9


@dataclass
class FanEnvelope:
    ribs: int
    nonce: bytes
    span_remaining: float
    half_bits: bytes
    data: bytes

    def to_json(self) -> str:
        return json.dumps(
            {
                "v": VERSION,
                "ribs": self.ribs,
                "nonce": base64.b64encode(self.nonce).decode("ascii"),
                "span_remaining": round(self.span_remaining, 6),
                "half_bits": base64.b64encode(self.half_bits).decode("ascii"),
                "data": base64.b64encode(self.data).decode("ascii"),
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "FanEnvelope":
        o = json.loads(raw)
        if o.get("v") != VERSION:
            raise ValueError("unsupported QFan envelope version")
        return cls(
            ribs=int(o["ribs"]),
            nonce=base64.b64decode(o["nonce"]),
            span_remaining=float(o.get("span_remaining", 1.0)),
            half_bits=base64.b64decode(o["half_bits"]),
            data=base64.b64decode(o["data"]),
        )

    def to_bytes(self) -> bytes:
        return (
            MAGIC
            + struct.pack(">BB", VERSION, self.ribs)
            + struct.pack(">d", self.span_remaining)
            + struct.pack(">H", len(self.nonce))
            + self.nonce
            + struct.pack(">I", len(self.half_bits))
            + self.half_bits
            + struct.pack(">I", len(self.data))
            + self.data
        )

    @classmethod
    def from_bytes(cls, raw: bytes) -> "FanEnvelope":
        if not raw.startswith(MAGIC):
            raise ValueError("not a QFan binary envelope")
        off = len(MAGIC)
        ver, ribs = struct.unpack_from(">BB", raw, off)
        off += 2
        if ver != VERSION:
            raise ValueError("unsupported QFan version")
        (span_rem,) = struct.unpack_from(">d", raw, off)
        off += 8
        (nlen,) = struct.unpack_from(">H", raw, off)
        off += 2
        nonce = raw[off : off + nlen]
        off += nlen
        (hlen,) = struct.unpack_from(">I", raw, off)
        off += 4
        half_bits = raw[off : off + hlen]
        off += hlen
        (dlen,) = struct.unpack_from(">I", raw, off)
        off += 4
        data = raw[off : off + dlen]
        return cls(ribs=ribs, nonce=nonce, span_remaining=span_rem, half_bits=half_bits, data=data)


def collapse_rib_truths(truths: list[Truth]) -> Truth:
    if not truths:
        return Truth.HALF
    if all(t is Truth.YES for t in truths):
        return Truth.YES
    if all(t is Truth.NO for t in truths):
        return Truth.NO
    return Truth.HALF


def combine_half(a: Truth, b: Truth) -> Truth:
    return a.combine_and(b)


def _master_bytes(key: str | bytes | Span) -> bytes:
    if isinstance(key, Span):
        return str(key.value).encode("utf-8")
    if isinstance(key, bytes):
        return key
    return str(key).encode("utf-8")


def _contract_block(key: Span | None, contract: bool) -> float | None:
    if isinstance(key, Span) and contract:
        key.contract(LAMBDA)
        return key.remaining
    return key.remaining if isinstance(key, Span) else None


def _rib_digest(master: bytes, rib: int, nonce: bytes, block: int) -> bytes:
    return hmac.new(
        master, b"qfan/v1" + nonce + bytes([rib & 0xFF]) + block.to_bytes(4, "big"), hashlib.sha256
    ).digest()


def _rib_truth(digest: bytes, byte_index: int) -> Truth:
    b = digest[byte_index % len(digest)]
    shift = byte_index % 8
    return Truth.YES if ((b >> shift) & 1) else Truth.NO


def _rib_truths(master: bytes, ribs: int, nonce: bytes, block: int, byte_index: int) -> list[Truth]:
    return [_rib_truth(_rib_digest(master, r, nonce, block), byte_index) for r in range(ribs)]


def _keystream_byte(
    truths: list[Truth], *, tie_break: Truth | None = None
) -> tuple[int, Truth]:
    collapsed = collapse_rib_truths(truths)
    if collapsed is not Truth.HALF:
        val = sum((1 << r) for r, t in enumerate(truths) if t is Truth.YES) & 0xFF
        return val, collapsed

    if tie_break is None:
        return 0, Truth.HALF

    val = 0
    for r, t in enumerate(truths):
        bit = tie_break if t is Truth.HALF else t
        if bit is Truth.YES:
            val |= 1 << (r % 8)
    return val & 0xFF, Truth.HALF


def _set_half_bit(bitmap: bytearray, index: int) -> None:
    while len(bitmap) < (index // 8) + 1:
        bitmap.append(0)
    bitmap[index // 8] |= 1 << (index % 8)


def _get_half_bit(bitmap: bytes, index: int) -> bool:
    if index // 8 >= len(bitmap):
        return False
    return bool(bitmap[index // 8] & (1 << (index % 8)))


def encrypt(
    plaintext: str | bytes,
    key: str | bytes | Span,
    *,
    ribs: int = DEFAULT_RIBS,
    contract_span: bool = True,
) -> FanEnvelope:
    if ribs < 2 or ribs > 16:
        raise ValueError("ribs must be between 2 and 16")
    data = plaintext.encode("utf-8") if isinstance(plaintext, str) else bytes(plaintext)
    master = _master_bytes(key)
    span_rem: float | None = key.remaining if isinstance(key, Span) else None
    nonce = secrets.token_bytes(16)
    out = bytearray()
    half_map = bytearray()

    for abs_i, plain_byte in enumerate(data):
        block_idx = abs_i // BLOCK_SIZE
        if abs_i % BLOCK_SIZE == 0:
            span_rem = _contract_block(key if isinstance(key, Span) else None, contract_span) or span_rem

        truths = _rib_truths(master, ribs, nonce, block_idx, abs_i)
        ks, collapsed = _keystream_byte(truths)

        if collapsed is Truth.HALF:
            _set_half_bit(half_map, abs_i)
            k_yes, _ = _keystream_byte(truths, tie_break=Truth.YES)
            k_no, _ = _keystream_byte(truths, tie_break=Truth.NO)
            out.append(plain_byte ^ k_yes)
            out.append(plain_byte ^ k_no)
        else:
            out.append(plain_byte ^ ks)

    if isinstance(key, Span):
        span_rem = key.remaining

    return FanEnvelope(
        ribs=ribs,
        nonce=nonce,
        span_remaining=span_rem if span_rem is not None else 1.0,
        half_bits=bytes(half_map),
        data=bytes(out),
    )


def decrypt(
    envelope: FanEnvelope | str | bytes,
    key: str | bytes | Span,
    *,
    contract_span: bool = True,
) -> str:
    return decrypt_bytes(envelope, key, contract_span=contract_span).decode("utf-8", errors="replace")


def decrypt_bytes(
    envelope: FanEnvelope | str | bytes,
    key: str | bytes | Span,
    *,
    contract_span: bool = True,
) -> bytes:
    """Decrypt QFan envelope to raw bytes (images and binary)."""
    env = _parse_envelope(envelope)
    master = _master_bytes(key)
    ribs = env.ribs
    plain = bytearray()
    pos = 0
    abs_i = 0

    while pos < len(env.data):
        if abs_i % BLOCK_SIZE == 0:
            _contract_block(key if isinstance(key, Span) else None, contract_span)

        if _get_half_bit(env.half_bits, abs_i):
            if pos + 1 >= len(env.data):
                raise ValueError("truncated half-truth ciphertext")
            c_yes = env.data[pos]
            c_no = env.data[pos + 1]
            pos += 2
            block_idx = abs_i // BLOCK_SIZE
            truths = _rib_truths(master, ribs, env.nonce, block_idx, abs_i)
            k_yes, _ = _keystream_byte(truths, tie_break=Truth.YES)
            k_no, _ = _keystream_byte(truths, tie_break=Truth.NO)
            p_yes = c_yes ^ k_yes
            p_no = c_no ^ k_no
            plain.append(p_yes if p_yes == p_no else p_yes)
            abs_i += 1
        else:
            block_idx = abs_i // BLOCK_SIZE
            truths = _rib_truths(master, ribs, env.nonce, block_idx, abs_i)
            ks, collapsed = _keystream_byte(truths)
            if collapsed is Truth.HALF:
                ks, _ = _keystream_byte(truths, tie_break=Truth.YES)
            plain.append(env.data[pos] ^ ks)
            pos += 1
            abs_i += 1

    return bytes(plain)


def _parse_envelope(envelope: FanEnvelope | str | bytes) -> FanEnvelope:
    if isinstance(envelope, FanEnvelope):
        return envelope
    if isinstance(envelope, bytes):
        if envelope.startswith(MAGIC):
            return FanEnvelope.from_bytes(envelope)
        return FanEnvelope.from_json(envelope.decode("utf-8"))
    text = envelope.strip()
    if text.startswith("{"):
        return FanEnvelope.from_json(text)
    return FanEnvelope.from_bytes(base64.b64decode(text))


def fan_encrypt(plaintext: str | bytes, key: str | bytes | Span, ribs: int = DEFAULT_RIBS) -> str:
    env = encrypt(plaintext, key, ribs=ribs)
    return base64.b64encode(env.to_json().encode("utf-8")).decode("ascii")


def fan_decrypt(sealed: str | bytes, key: str | bytes | Span, ribs: int = DEFAULT_RIBS) -> str:
    del ribs  # rib count is stored in the envelope
    raw = base64.b64decode(sealed.strip() if isinstance(sealed, str) else sealed)
    env = FanEnvelope.from_json(raw.decode("utf-8"))
    return decrypt(env, key)


def fan_audit_summary(sealed: str) -> str:
    env = _parse_envelope(base64.b64decode(sealed.strip()).decode("utf-8"))
    half_count = sum(bin(b).count("1") for b in env.half_bits)
    return (
        f"ribs={env.ribs} half_positions={half_count} "
        f"span_remaining={env.span_remaining:.4f} cipher_bytes={len(env.data)}"
    )
