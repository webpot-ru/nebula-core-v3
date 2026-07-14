"""Bounded downloader for selected Reddit-hosted static compilation images."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


ALLOWED_HOSTS = {"i.redd.it", "preview.redd.it"}
ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGES_PER_STORY = 6
MAX_PIXELS = 40_000_000


class RedditMediaError(RuntimeError):
    pass


def _validate_magic(data: bytes, content_type: str) -> None:
    valid = {
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    }
    if not valid.get(content_type, False):
        raise RedditMediaError(f"image bytes do not match {content_type}")


def download_media_assets(
    assets: list[dict[str, Any]],
    output_dir: Path,
    *,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    if len(assets) > MAX_IMAGES_PER_STORY:
        raise RedditMediaError(f"too many source images: {len(assets)}>{MAX_IMAGES_PER_STORY}")
    output_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    downloaded: list[dict[str, Any]] = []
    for index, asset in enumerate(assets):
        url = str(asset.get("source_url") or "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in ALLOWED_HOSTS:
            raise RedditMediaError("source image must use an allowed Reddit HTTPS host")
        width = int(asset.get("width") or 0)
        height = int(asset.get("height") or 0)
        if width and height and width * height > MAX_PIXELS:
            raise RedditMediaError("source image exceeds pixel limit")
        response = client.get(url, stream=True, timeout=(10, 30), allow_redirects=False)
        if response.status_code != 200:
            raise RedditMediaError(f"image download failed with HTTP {response.status_code}")
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
        extension = ALLOWED_TYPES.get(content_type)
        if not extension:
            raise RedditMediaError(f"unsupported image Content-Type: {content_type or 'missing'}")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise RedditMediaError("source image exceeds byte limit")
            chunks.append(chunk)
        data = b"".join(chunks)
        _validate_magic(data, content_type)
        media_id = "".join(char for char in str(asset.get("media_id") or index) if char.isalnum() or char in "-_")[:60]
        if not media_id:
            media_id = f"image-{index + 1}"
        path = output_dir / f"{index + 1:02d}-{media_id}{extension}"
        path.write_bytes(data)
        copied = dict(asset)
        copied.update({
            "local_path": str(path),
            "content_type": content_type,
            "byte_size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "download_status": "verified",
        })
        downloaded.append(copied)
    return downloaded


def write_manifest(path: Path, assets: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "assets": assets}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
