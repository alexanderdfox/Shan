"""QFan half-truth quantum fan cipher."""
from __future__ import annotations

from shan.fan_cipher import (
    FanEnvelope,
    combine_half,
    collapse_rib_truths,
    decrypt,
    encrypt,
    fan_decrypt,
    fan_encrypt,
)
from shan.values import Span, Truth


def test_collapse_truths():
    assert collapse_rib_truths([Truth.YES, Truth.YES]) is Truth.YES
    assert collapse_rib_truths([Truth.NO, Truth.NO]) is Truth.NO
    assert collapse_rib_truths([Truth.YES, Truth.NO]) is Truth.HALF
    assert combine_half(Truth.HALF, Truth.YES) is Truth.HALF
    assert combine_half(Truth.YES, Truth.YES) is Truth.YES


def test_roundtrip_string_key():
    msg = "Fan security: ½ + ribs + span decay"
    sealed = fan_encrypt(msg, "test-key", ribs=8)
    back = fan_decrypt(sealed, "test-key", ribs=8)
    assert back == msg


def test_roundtrip_span_contracts():
    key = Span(value="span-master", uses_left=100)
    msg = "Observe-driven keystream blocks"
    env = encrypt(msg, key, ribs=4)
    assert env.span_remaining < 1.0
    back = decrypt(env, Span(value="span-master", uses_left=100))
    assert back == msg


def test_binary_envelope():
    msg = "binary envelope"
    env = encrypt(msg, b"bytes-key", ribs=6)
    raw = env.to_bytes()
    env2 = FanEnvelope.from_bytes(raw)
    assert decrypt(env2, b"bytes-key") == msg


def test_wrong_key_fails():
    sealed = fan_encrypt("secret", "key-a", ribs=8)
    wrong = fan_decrypt(sealed, "key-b", ribs=8)
    assert wrong != "secret"
