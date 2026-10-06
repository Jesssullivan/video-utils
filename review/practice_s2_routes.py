"""Read-only S2 practice bundle routes for scripts/review_server.py (stdlib only).

Root wires these helpers into the review server (see REVIEW_UI_S2 section 9):

* ``load(bundle_dir, session, media_factory)`` verifies the bundle binding
  against the session's original source and manifest hashes, then
  hash-verifies each media file through ``media_factory(path, sha256)``
  (``review_server.Media``: an fd pinned by signature). It never raises; a
  refusal is kept as a reason and the server still starts.
* ``api_response(bundle)`` -> ``(status, json_value)`` for ``GET /api/practice-s2``.
* ``media_for(bundle, name)`` -> a verified media object or ``None`` for
  ``GET /media/s2/<name>``.
* ``close(bundle)`` releases media descriptors.

There is no write route; labelling uses the existing ``/api/annotations-v2``.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

SCHEMA_ID = "video-utils.practice-s2.bundle"
SCHEMA_VERSION = 1
MAX_BUNDLE_BYTES = 20_000_000
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
API_PATH = "/api/practice-s2"
MEDIA_PREFIX = "/media/s2/"
ASSET = "/practice_s2.js"


class PracticeBundle:
    def __init__(self, status, reason=None, document=None, media=None, media_status=None, root=None):
        self.status = status
        self.reason = reason
        self.document = document
        self.media = media or {}
        self.media_status = media_status or {}
        self.root = root

    @property
    def available(self):
        return self.status == "available"


def refused(reason):
    return PracticeBundle("refused", reason)


def read_bundle(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BUNDLE_BYTES:
            raise ValueError("practice_s2_bundle_unreadable")
        chunks, remaining = [], info.st_size
        while remaining:
            chunk = os.read(fd, min(remaining, 1 << 20))
            if not chunk:
                raise ValueError("practice_s2_bundle_unreadable")
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    if not isinstance(value, dict):
        raise ValueError("practice_s2_bundle_unreadable")
    return value, hashlib.sha256(data).hexdigest()


def load(bundle_dir, session, media_factory):
    """Verify and open a bundle for one review session. Never raises."""
    if bundle_dir is None:
        return refused("practice_s2_bundle_not_configured")
    try:
        root = Path(bundle_dir).resolve(strict=True)
        if not root.is_dir():
            return refused("practice_s2_bundle_unreadable")
        document, digest = read_bundle(root / "bundle.json")
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return refused("practice_s2_bundle_unreadable")
    if document.get("schema_id") != SCHEMA_ID or document.get("schema_version") != SCHEMA_VERSION:
        return refused("practice_s2_bundle_schema_unknown")
    binding = document.get("session_binding")
    if not isinstance(binding, dict) or binding.get("original_source_sha256") != session.source_hash \
            or binding.get("manifest_sha256") != session.manifest_hash:
        return refused("practice_s2_bundle_foreign_recording")
    media, media_status = {}, {}
    records = document.get("media") if isinstance(document.get("media"), dict) else {}
    try:
        for name, record in records.items():
            if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(record, dict) \
                    or record.get("file") != "media/" + name or not isinstance(record.get("sha256"), str) \
                    or not SHA.fullmatch(record["sha256"]):
                media_status[str(name)[:96]] = "invalid_media_record_omitted"
                continue
            path = root / "media" / name
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                media_status[name] = "unsafe_or_missing_media_omitted"
                continue
            try:
                media[name] = media_factory(path.resolve(), record["sha256"])
                media_status[name] = "hash_verified"
            except Exception:  # Media raises ReviewError or OSError; either way it is omitted.
                media_status[name] = "modified_or_unavailable_omitted"
    except BaseException:
        for item in media.values():
            item.close()
        raise
    return PracticeBundle("available", None, document, media, media_status, root)


def api_response(bundle):
    if bundle is None:
        return 404, {"error": "practice_s2_bundle_not_configured"}
    if not bundle.available:
        return 404, {"error": bundle.reason or "practice_s2_bundle_not_configured"}
    served = {"media_urls": {name: MEDIA_PREFIX + name for name in bundle.media},
              "media_status": bundle.media_status, "route": "read_only"}
    return 200, {**bundle.document, "served": served}


def media_for(bundle, name):
    if bundle is None or not bundle.available or not isinstance(name, str) or not NAME.fullmatch(name):
        return None
    return bundle.media.get(name)


def close(bundle):
    if bundle is None:
        return
    for item in bundle.media.values():
        try:
            item.close()
        except OSError:
            pass
    bundle.media.clear()
