"""Hand a verified narration run to a consumer that reads one WAV per page (`python -m narrate export`).

A slide-deck assembler reads `<dir>/NN-<slide-id>.wav` beside camera takes of the same stem (the TIN-7091
consumer layout). export copies a run's narration.wav there as `<stem>.wav` and prints a JSON receipt:

- The run must pass `narrate verify` first: an export never carries a run whose bytes or manifest changed.
- A run made from a markdown manuscript records its front-matter `slide`. The stem must be that slide id or end
  in `-<slide id>`, so a page cannot be handed out under another page's name.
- The stem is letters, digits, `.`, `_` and `-`, starting with a letter or digit, at most 128 characters.
- export never replaces a file. Any `<stem>.*` already in the directory (a camera take, an older render) refuses
  the export, except the same narration.wav bytes under `<stem>.wav`, which is reported as unchanged.
- The file is written under a temporary name and linked into place, so a reader never sees a partial WAV.

The receipt names the file, never the directory. It carries the run id, the manifest's content digest, the WAV's
sha256 and `synthetic: true`. The WAV itself carries no label: a consumer that needs one reads the receipt.
"""

import json
import os
import re
import tempfile
from pathlib import Path

from . import verify
from .ir import sha256_file

STEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
NARRATION = "narration.wav"


class ExportError(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def slide_of(manifest):
    meta = manifest.get("input", {}).get("meta") or {}
    slide = meta.get("slide") if isinstance(meta, dict) else None
    return slide if isinstance(slide, str) and slide else None


def export(run_dir, to_dir, stem):
    run_dir, to_dir = Path(run_dir), Path(to_dir)
    if not STEM.fullmatch(stem) or stem.endswith(".wav"):
        raise ExportError("export_stem_invalid", f"{stem!r}: letters, digits, '.', '_' or '-', without .wav")
    receipt = verify.verify(run_dir)
    if not receipt["ok"]:
        raise ExportError("export_run_unverified", receipt["reason"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    slide = slide_of(manifest)
    if slide is not None and stem != slide and not stem.endswith("-" + slide):
        raise ExportError("export_slide_mismatch", f"the run voices slide {slide!r}; the stem must end in -{slide}")
    if not to_dir.is_dir():
        raise ExportError("export_target_missing", "the target directory does not exist")
    source = run_dir / NARRATION
    digest = manifest["output_sha256"][NARRATION]
    target = to_dir / (stem + ".wav")
    taken = sorted(p.name for p in to_dir.iterdir() if p.name.startswith(stem + ".") and p.name != target.name)
    if taken:
        raise ExportError("export_take_exists", f"{', '.join(taken)} already holds this page")
    state = "unchanged"
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or sha256_file(target) != digest:
            raise ExportError("export_take_exists", f"{target.name} already exists with other content")
    else:
        fd, partial = tempfile.mkstemp(prefix=f".{stem}.", suffix=".partial", dir=to_dir)
        try:
            with os.fdopen(fd, "wb") as out, source.open("rb") as src:
                while block := src.read(1 << 20):
                    out.write(block)
            if sha256_file(Path(partial)) != digest:
                raise ExportError("export_copy_changed", f"{NARRATION} changed while it was copied")
            try:
                os.link(partial, target)  # fails when the name appeared meanwhile: never replaces
            except FileExistsError:
                raise ExportError("export_take_exists", f"{target.name} appeared during the export") from None
        finally:
            os.unlink(partial)
        state = "written"
    return {
        "ok": True,
        "state": state,
        "file": target.name,
        "sha256": digest,
        "run_id": manifest.get("run_id"),
        "content_sha256": manifest.get("content_sha256"),
        "slide": slide,
        "synthetic": manifest.get("synthetic") is True,
        "sample_rate": manifest["timeline"]["sample_rate"],
        "total_samples": manifest["timeline"]["total_samples"],
    }
