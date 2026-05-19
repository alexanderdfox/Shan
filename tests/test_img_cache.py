"""Preview image cache and serve route."""
from __future__ import annotations

import base64

from shan.image_fan import sample_image_b64
from shan.img_cache import img_preview_url, preview_cache


def test_preview_url_and_cache():
    b64 = sample_image_b64()
    url = img_preview_url("fan-image-web", b64, "image/png")
    assert url.startswith("/app/fan-image-web/img/")
    token = url.rsplit("/", 1)[-1]
    item = preview_cache().get(token)
    assert item is not None
    assert item[0] == base64.b64decode(b64)
