"""Stage keys (docs/spec/NARRATED_VIDEO.md, "Stage keys and the store").

A stage key is the SHA-256 of the canonical JSON of a key document: the stage id, the segment, a hand-bumped impl,
the tool identity (name, version, binary digest), the FFmpeg identity on render stages, the resolved knobs, the
edition and the sorted inputs. The git commit is recorded in the stage manifest and kept out of the key, so a
commit that changes no stage leaves every stage fresh.

Canonical JSON: sorted keys, no whitespace, UTF-8. dhall-to-json writes the Double -16.0 as -16, so a number
that is integral is written as an integer whatever its Python type, and any other float as its repr string. A
non-finite number is refused. Booleans stay booleans.
"""

import hashlib
import json
import math

KEY_SCHEMA = 1
KEY16 = 16
VOLATILE = ("run_dir", "created_utc", "content_sha256", "commit")


class KeyDocumentError(ValueError):
    """A key document holds a value with no canonical form."""


def normalise(value):
    """The value every digest is taken over: integral numbers as int, other floats as repr strings."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise KeyDocumentError(f"non-finite number {value!r}")
        return int(value) if value.is_integer() else repr(value)
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise KeyDocumentError("a key document's object keys are strings")
        return {k: normalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalise(v) for v in value]
    raise KeyDocumentError(f"{type(value).__name__} has no canonical form")


def canonical(value):
    return json.dumps(normalise(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def key_document(stage, segment, impl, tool, ffmpeg, knobs, edition, inputs):
    """The document a stage key hashes. inputs: [{slot, stage, digest}] or [{slot, stage, value}] (a projection of
    an upstream measurement); they are sorted, so their order never changes the key."""
    rows = sorted((normalise(dict(i)) for i in inputs), key=lambda i: canonical(i))
    return {
        "key_schema": KEY_SCHEMA,
        "stage": stage,
        "segment": segment,
        "impl": impl,
        "tool": {"name": tool["name"], "version": tool["version"], "binary_sha256": tool.get("binary_sha256")},
        "ffmpeg": ffmpeg,
        "knobs": knobs,
        "edition": edition,
        "inputs": rows,
    }


def stage_key(document):
    return digest(document)


def key16(key):
    return key[:KEY16]


def content_digest(manifest):
    """A stage manifest's content_sha256: the digest of the manifest without its volatile fields (as narrate's
    render.content_digest does for narration runs). An output the manifest lists under volatile_outputs is still
    re-hashed for freshness but left out of this digest: its bytes differ between identical runs only by a run id
    and a time (a narrate run's own manifest.json, whose content digest the stage records in its measurements)."""
    body = {k: v for k, v in manifest.items() if k not in VOLATILE}
    skip = set(manifest.get("volatile_outputs") or ())
    if skip and isinstance(body.get("outputs"), dict):
        body["outputs"] = {name: value for name, value in body["outputs"].items() if name not in skip}
    return digest(body)
