"""Pinned, hash-recorded fetch plan for the narrate engine bench.

The default is a dry run: it prints the download plan for the pinned sources in
narrate/bench/sources.json and touches nothing. --apply downloads the selected
Hugging Face files into a private directory outside the repository, checks each
file against its declared size and (when the Hub declares one) its LFS sha256,
and records the measured sha256 of every file in <dest>/<source>/SHA256SUMS and a
dated receipt under <dest>/receipts/ (latest copy: <dest>/fetch-receipt.json). Git sources are never cloned here; the plan prints
their pinned clone commands for the arm's build step.

Plan: docs/agent-notes/2026-10-22-narrate-bench-plan.md.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SOURCES = Path(__file__).resolve().parent / "sources.json"
HUB = "https://huggingface.co"
DEST_ENV = "NARRATE_WEIGHTS_DIR"
DEFAULT_DEST = Path.home() / ".local" / "share" / "narrate" / "weights"
REVISION = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}")
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
CHUNK = 1024 * 1024


class FetchError(ValueError):
    pass


def load_sources(path=SOURCES):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("schema_version") != 1 or not isinstance(doc.get("sources"), list):
        raise FetchError("sources file requires schema_version 1 and a sources list")
    seen = set()
    for source in doc["sources"]:
        sid = source.get("id", "")
        if not isinstance(sid, str) or not IDENT.fullmatch(sid) or sid in seen:
            raise FetchError(f"invalid or duplicate source id: {sid!r}")
        seen.add(sid)
        if not source.get("licence"):
            raise FetchError(f"{sid}: licence is required")
        if source.get("kind") == "git":
            if not REVISION.fullmatch(source.get("commit", "")) or not str(source.get("url", "")).startswith("https://"):
                raise FetchError(f"{sid}: git sources need an https url and a full commit")
        elif source.get("kind") == "hf":
            if not REPO.fullmatch(source.get("repo", "")) or not REVISION.fullmatch(source.get("revision", "")):
                raise FetchError(f"{sid}: hf sources need owner/name and a full revision")
            files = source.get("files")
            if not isinstance(files, list) or not files:
                raise FetchError(f"{sid}: hf sources need a files list")
            for entry in files:
                safe_relative(entry.get("path", ""))
                size = entry.get("bytes")
                if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
                    raise FetchError(f"{sid}: {entry.get('path')}: bytes must be a positive integer")
                digest = entry.get("sha256")
                if digest is not None and not SHA256.fullmatch(digest):
                    raise FetchError(f"{sid}: {entry.get('path')}: sha256 must be lowercase hex or null")
        else:
            raise FetchError(f"{sid}: unknown kind {source.get('kind')!r}")
    return doc


def safe_relative(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts) or "\\" in name:
        raise FetchError(f"unsafe file path: {name!r}")
    return path


def resolve_dest(dest):
    chosen = Path(dest) if dest else Path(os.environ[DEST_ENV]) if os.environ.get(DEST_ENV) else DEFAULT_DEST
    resolved = chosen.expanduser().resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise FetchError("destination is inside the repository; weights stay outside the public tree")
    return resolved


def select(doc, only=(), arms=(), include_optional=False):
    chosen = []
    known = {source["id"] for source in doc["sources"]}
    missing = sorted(set(only) - known)
    if missing:
        raise FetchError(f"unknown source ids: {', '.join(missing)}")
    for source in doc["sources"]:
        if only and source["id"] not in only:
            continue
        if arms and not any(arm.startswith(prefix) for arm in source.get("arms", []) for prefix in arms):
            continue
        if source.get("optional") and not include_optional and source["id"] not in only:
            continue
        chosen.append(source)
    return chosen


def file_url(hub, source, name):
    return f"{hub.rstrip('/')}/{source['repo']}/resolve/{source['revision']}/{urllib.parse.quote(name)}"


def check_hub(hub, allow_file_hub):
    scheme = urllib.parse.urlparse(hub).scheme
    if scheme == "https" or (scheme == "file" and allow_file_hub):
        return
    raise FetchError("hub base must be https (file: only with --allow-file-hub, for local mirrors and tests)")


def plan(doc, sources, dest, hub=HUB):
    entries, git, total, missing = [], [], 0, 0
    for source in sources:
        if source["kind"] == "git":
            target = dest / "src" / source["id"]
            git.append({"id": source["id"], "url": source["url"], "commit": source["commit"], "ref": source.get("ref"),
                        "commands": [f"git clone --filter=blob:none {source['url']} {target}",
                                     f"git -C {target} checkout --detach {source['commit']}"]})
            continue
        files = []
        for entry in source["files"]:
            target = dest / source["id"] / safe_relative(entry["path"])
            if target.is_file() and not target.is_symlink():
                state = "present_size_match" if target.stat().st_size == entry["bytes"] else "present_size_mismatch"
            else:
                state = "missing"
                missing += entry["bytes"]
            total += entry["bytes"]
            files.append({"path": entry["path"], "url": file_url(hub, source, entry["path"]), "dest": str(target),
                          "bytes": entry["bytes"], "sha256_declared": entry["sha256"], "state": state})
        entries.append({"id": source["id"], "repo": source["repo"], "revision": source["revision"],
                        "licence": source["licence"], "arms": source.get("arms", []),
                        "optional": bool(source.get("optional")), "files": files})
    return {"mode": "dry-run", "dest": str(dest), "hub": hub, "recorded": doc.get("recorded"),
            "hf": entries, "git": git,
            "totals": {"hf_sources": len(entries), "files": sum(len(e["files"]) for e in entries),
                       "bytes": total, "bytes_missing": missing, "git_sources": len(git)},
            "note": "Dry run: nothing was downloaded. Pass --apply to fetch the hf files; git sources are not cloned."}


def sha256_file(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def download(url, target, size, declared, timeout):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "video-utils-narrate-fetch/1"}),
                                    timeout=timeout) as response:
            if urllib.parse.urlparse(url).scheme == "https" and urllib.parse.urlparse(response.geturl()).scheme != "https":
                raise FetchError(f"{url}: redirected away from https")
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".partial-", delete=False) as output:
                temporary = Path(output.name)
                hasher, count = hashlib.sha256(), 0
                while block := response.read(CHUNK):
                    count += len(block)
                    if count > size:
                        raise FetchError(f"{url}: exceeds its declared {size} bytes")
                    hasher.update(block)
                    output.write(block)
        if count != size:
            raise FetchError(f"{url}: got {count} bytes, declared {size}")
        digest = hasher.hexdigest()
        if declared is not None and digest != declared:
            raise FetchError(f"{url}: sha256 {digest} does not match the declared {declared}")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        temporary = None
        return digest
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_sums(path):
    sums = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            digest, _, name = line.partition("  ")
            if SHA256.fullmatch(digest) and name:
                sums[name] = digest
    return sums


def apply(doc, sources, dest, hub=HUB, timeout=60, sources_path=SOURCES):
    records = []
    for source in sources:
        if source["kind"] != "hf":
            continue
        base = dest / source["id"]
        sums_path = base / "SHA256SUMS"
        sums = read_sums(sums_path)
        base.mkdir(parents=True, exist_ok=True)
        for entry in source["files"]:
            name, declared = entry["path"], entry["sha256"]
            target = base / safe_relative(name)
            url = file_url(hub, source, name)
            if target.is_symlink():
                raise FetchError(f"{target}: refusing a symlinked destination")
            if target.is_file() and target.stat().st_size == entry["bytes"]:
                digest = sha256_file(target)
                expected = declared or sums.get(name)
                if expected is not None and digest != expected:
                    raise FetchError(f"{target}: existing file sha256 {digest} differs from {expected}; remove it to refetch")
                status = "already_present" if expected is not None else "already_present_unverified"
            else:
                if target.exists():
                    raise FetchError(f"{target}: existing file has the wrong size; remove it to refetch")
                digest = download(url, target, entry["bytes"], declared, timeout)
                status = "downloaded"
            check = ("matched_declared" if declared else "matched_recorded" if name in sums
                     else "recorded_at_download")
            sums[name] = digest
            # Written after every file, so a failure later in the source keeps the hashes already measured.
            sums_path.write_text("".join(f"{sums[key]}  {key}\n" for key in sorted(sums)), encoding="utf-8")
            records.append({"id": source["id"], "repo": source["repo"], "revision": source["revision"], "path": name,
                            "url": url, "bytes": entry["bytes"], "sha256": digest, "declared_sha256": declared,
                            "check": check, "status": status})
    now = datetime.datetime.now(datetime.timezone.utc)
    receipt = {"schema_version": 1, "recorded_at": now.isoformat(timespec="seconds"),
               "sources_sha256": hashlib.sha256(Path(sources_path).read_bytes()).hexdigest(), "hub": hub,
               "files": records,
               "git_not_cloned": [{"id": s["id"], "url": s["url"], "commit": s["commit"]} for s in sources if s["kind"] == "git"]}
    # One dated receipt per run is kept; fetch-receipt.json is a copy of the latest.
    history = dest / "receipts" / f"{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    history.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(receipt, indent=1) + "\n"
    history.write_text(body, encoding="utf-8")
    (dest / "fetch-receipt.json").write_text(body, encoding="utf-8")
    return {"mode": "apply", "dest": str(dest), "receipt": str(history),
            "files": len(records), "downloaded": sum(r["status"] == "downloaded" for r in records)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", default=str(SOURCES), help="pinned sources file")
    parser.add_argument("--dest", help=f"private download directory (default ${DEST_ENV}, else {DEFAULT_DEST})")
    parser.add_argument("--only", action="append", default=[], help="source id to include (repeatable)")
    parser.add_argument("--arm", action="append", default=[], help="arm prefix to include, e.g. A1 or A2-mac (repeatable)")
    parser.add_argument("--include-optional", action="store_true", help="also include optional sources (Drama 3, WavLM)")
    parser.add_argument("--apply", action="store_true", help="download and record sha256 values (default: dry run)")
    parser.add_argument("--hub-base", default=HUB, help=argparse.SUPPRESS)
    parser.add_argument("--allow-file-hub", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=int, default=60, help="socket timeout in seconds per request")
    arguments = parser.parse_args(argv)
    try:
        check_hub(arguments.hub_base, arguments.allow_file_hub)
        doc = load_sources(arguments.sources)
        dest = resolve_dest(arguments.dest)
        chosen = select(doc, arguments.only, arguments.arm, arguments.include_optional)
        if arguments.apply:
            result = apply(doc, chosen, dest, arguments.hub_base, arguments.timeout, arguments.sources)
        else:
            result = plan(doc, chosen, dest, arguments.hub_base)
        print(json.dumps(result, indent=1))
        return 0
    except (FetchError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
