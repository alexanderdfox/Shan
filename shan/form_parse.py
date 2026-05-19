"""Parse POST bodies for Shàn serve (urlencoded + multipart)."""
from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qs


def parse_form_body(
    body: bytes,
    content_type: str | None,
    *,
    max_file_bytes: int = 2 * 1024 * 1024,
) -> tuple[dict[str, str], dict[str, bytes]]:
    """
    Returns (fields, files) where files maps field name → raw bytes.
    """
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype == "multipart/form-data":
        return _parse_multipart(body, content_type or "", max_file_bytes=max_file_bytes)
    text = body.decode("utf-8", errors="replace")
    fields: dict[str, str] = {}
    for key, vals in parse_qs(text, keep_blank_values=True).items():
        fields[key] = vals[-1] if vals else ""
    return fields, {}


def _parse_multipart(body: bytes, content_type: str, *, max_file_bytes: int) -> tuple[dict[str, str], dict[str, bytes]]:
    msg = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8", errors="replace") + b"\r\n\r\n" + body
    )
    fields: dict[str, str] = {}
    files: dict[str, bytes] = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = part.get_payload()
            if isinstance(payload, str):
                payload = payload.encode("utf-8", errors="replace")
            else:
                payload = b""
        if not isinstance(payload, bytes):
            payload = bytes(payload)
        filename = part.get_filename()
        if filename or (part.get_content_type() or "").startswith("image/"):
            if len(payload) > max_file_bytes:
                raise ValueError(f"upload too large: {name}")
            files[name] = payload
        else:
            fields[name] = payload.decode("utf-8", errors="replace")
    return fields, files
