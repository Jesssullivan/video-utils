"""Synthetic VRM rig fixtures (docs/spec/NARRATED_VIDEO.md, "VRM external"). Standard library only.

model(spec) returns the bytes of a binary glTF 2.0 whose JSON chunk carries a VRM 1.0 (VRMC_vrm) or 0.x (VRM)
extension with synthetic meta and an empty humanoid: no mesh, texture or art. It is enough for the wrapper to read
the licence fields and for the stub renderer to accept the file; no real renderer could draw it. record(...) is the
avatars.json record that names it, with a synthetic likeness consent and appearance approval.
"""

import hashlib
import json
import struct

FIXTURE_ID = "vrm-fixture-rig"
META = {
    "1.0": {
        "name": FIXTURE_ID,
        "version": "0",
        "authors": ["synthetic fixture"],
        "licenseUrl": "fixture:vrm-public-licence-1.0",
        "avatarPermission": "onlyAuthor",
        "commercialUsage": "personalNonProfit",
        "creditNotation": "required",
        "allowRedistribution": False,
        "modification": "prohibited",
    },
    "0.x": {
        "title": FIXTURE_ID,
        "version": "0",
        "author": "synthetic fixture",
        "allowedUserName": "OnlyAuthor",
        "violentUssageName": "Disallow",
        "sexualUssageName": "Disallow",
        "commercialUssageName": "Disallow",
        "licenseName": "Redistribution_Prohibited",
    },
}


def model(spec="1.0", meta=None):
    """The bytes of a synthetic .vrm: a GLB header and one JSON chunk, padded with spaces to 4 bytes."""
    body = dict(META[spec] if meta is None else meta)
    if spec == "1.0":
        extension = {"VRMC_vrm": {"specVersion": "1.0", "meta": body, "humanoid": {"humanBones": {}}}}
    else:
        extension = {"VRM": {"specVersion": "0.0", "meta": body, "humanoid": {"humanBones": []}}}
    document = {
        "asset": {"version": "2.0", "generator": "video-utils synthetic VRM fixture"},
        "extensionsUsed": list(extension),
        "extensions": extension,
    }
    chunk = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    chunk += b" " * (-len(chunk) % 4)
    return struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(chunk)) + struct.pack("<II", len(chunk), 0x4E4F534A) + chunk


def record(data, model_id=FIXTURE_ID):
    """The avatars.json record of a synthetic model: its digest, a likeness consent and an approval, all synthetic."""
    digest = hashlib.sha256(data).hexdigest()
    return {
        "id": model_id,
        "kind": "vrm",
        "sha256": digest,
        "bytes": len(data),
        "likenessConsent": {
            "id": "likeness-fixture",
            "ruling": "SP-R13",
            "scopes": ["Avatar", "Likeness"],
            "grantedBy": "Operator",
            "grantedAt": "2026-10-29T00:00:00Z",
            "revokedAt": None,
            "evidenceSha256": hashlib.sha256(b"synthetic likeness consent").hexdigest(),
        },
        "approval": {
            "ref": "TIN-7130",
            "state": "approved",
            "decidedBy": "Operator",
            "decidedAt": "2026-10-29T00:00:00Z",
            "vrmSha256": digest,
            "evidenceSha256": hashlib.sha256(b"synthetic appearance approval").hexdigest(),
        },
        "badge": {"burnedIn": None},
    }
