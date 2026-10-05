"""Explicit downloads from a reviewed, checksum-bound model registry."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "program" / "models.json"
MAX_BYTES = 2 * 1024 * 1024 * 1024


def prefetch(model):
    if not REGISTRY.is_file():
        raise ValueError("No optional models are registered yet; add a reviewed program/models.json entry with official HTTPS URL, SHA-256 and byte limit.")
    registry = json.loads(REGISTRY.read_text())
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise ValueError("Model registry requires schema_version: 1")
    models = registry.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("Registry models must be an object")
    if model not in models:
        raise ValueError(f"Unregistered model: {model}; registered models: {', '.join(sorted(models)) or 'none'}")
    entry = models[model]
    if not isinstance(entry, dict):
        raise ValueError("Model registry entry must be an object")
    url, digest = entry.get("url", ""), entry.get("sha256", "")
    limit = entry.get("max_bytes")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}", model):
        raise ValueError("Invalid model identifier")
    if not isinstance(url, str) or not isinstance(digest, str):
        raise ValueError("Model URL and SHA-256 must be strings")
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.hostname or parsed_url.username or parsed_url.password or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Registered models require an HTTPS URL and lowercase SHA-256")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 0 < limit <= MAX_BYTES:
        raise ValueError("Registered models require max_bytes between 1 and 2147483648")
    destination = ROOT / "models" / f"{model}.bin"
    if destination.parent.is_symlink():
        raise ValueError("Model cache directory must not be a symlink")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink() or destination.stat().st_size > limit:
            raise ValueError("Invalid existing cache artifact")
        with destination.open("rb") as cached:
            verified = hashlib.file_digest(cached, "sha256").hexdigest() == digest
        if verified:
            return {"model": model, "status": "already_verified", "path": str(destination.relative_to(ROOT))}
        raise ValueError("Existing model checksum mismatch; remove only the named cache artifact before retrying")
    request = urllib.request.Request(url, headers={"User-Agent": "video-utils-model-prefetch/1"})
    temporary = None
    deadline = time.monotonic() + 300
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if urllib.parse.urlparse(response.geturl()).scheme != "https":
                raise ValueError("Model download redirected away from HTTPS")
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
                temporary = Path(output.name)
                hasher, size = hashlib.sha256(), 0
                while block := response.read(1024 * 1024):
                    if time.monotonic() > deadline:
                        raise ValueError("Model download exceeded 300-second time limit")
                    size += len(block)
                    if size > limit:
                        raise ValueError("Model exceeds registered byte limit")
                    hasher.update(block)
                    output.write(block)
            if hasher.hexdigest() != digest:
                raise ValueError("Downloaded model checksum mismatch")
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
            temporary = None
            return {"model": model, "status": "verified", "sha256": digest, "bytes": size, "path": str(destination.relative_to(ROOT))}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    arguments = parser.parse_args()
    try:
        print(json.dumps(prefetch(arguments.model)))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
