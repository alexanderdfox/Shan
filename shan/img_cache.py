"""Short-lived in-memory image blobs for SSR previews (avoids data: URIs in HTML)."""
from __future__ import annotations

import re
import secrets
from collections import OrderedDict

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{12,32}$")
_MAX_ITEMS = 96


class PreviewImageCache:
    def __init__(self, max_items: int = _MAX_ITEMS) -> None:
        self._max = max_items
        self._items: OrderedDict[str, tuple[bytes, str]] = OrderedDict()

    def put(self, data: bytes, mime: str) -> str:
        token = secrets.token_urlsafe(12)
        self._items[token] = (data, mime.split(";")[0].strip() or "application/octet-stream")
        self._items.move_to_end(token)
        while len(self._items) > self._max:
            self._items.popitem(last=False)
        return token

    def get(self, token: str) -> tuple[bytes, str] | None:
        if not _TOKEN_RE.match(token):
            return None
        item = self._items.get(token)
        if item is None:
            return None
        self._items.move_to_end(token)
        return item


_CACHE = PreviewImageCache()


def preview_cache() -> PreviewImageCache:
    return _CACHE


def img_preview_url(stem: str, b64_data: str, mime: str) -> str:
    """Return /app/{stem}/img/{token} for base64 image bytes, or \"\"."""
    import base64

    if not b64_data:
        return ""
    try:
        raw = base64.b64decode(str(b64_data).strip())
    except (ValueError, TypeError):
        return ""
    if not raw:
        return ""
    token = _CACHE.put(raw, str(mime or "image/png"))
    return f"/app/{stem}/img/{token}"
