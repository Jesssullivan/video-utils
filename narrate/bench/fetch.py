"""Pinned, hash-recorded fetch plan for the narrate engine bench.

The default is a dry run: it prints the download plan for the pinned sources in
narrate/bench/sources.json and touches nothing. --apply downloads the selected
Hugging Face files into a private directory outside every checkout of the
repository, checks each file against its declared size and its declared hash
(the Hub's LFS sha256, or for a small non-LFS file the Hub's git blob sha1),
and records the measured sha256 of every file in <dest>/hf/<source>/SHA256SUMS
and a dated receipt under <dest>/receipts/ (latest copy:
<dest>/fetch-receipt.json). A file already present is re-hashed against the
same declared value; a file without a declared hash is refused. Git sources are
never cloned here; the plan prints their pinned clone commands (into
<dest>/src/<source>) for the arm's build step.

Plan: docs/agent-notes/2026-10-22-narrate-bench-plan.md.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
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
SHA1 = re.compile(r"[0-9a-f]{40}")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}")
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
CHUNK = 1024 * 1024


class FetchError(ValueError):
    pass


def load_sources(path=SOURCES):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("schema_version") != 1 or not isinstance(doc.get("sources"), list):
        raise FetchError("sources file requires schema_version 1 and a sources list")
    optional_arms = doc.get("optional_arms", [])
    if not isinstance(optional_arms, list) or not all(isinstance(arm, str) for arm in optional_arms):
        raise FetchError("optional_arms must be a list of arm names")
    seen = set()
    for source in doc["sources"]:
        if not isinstance(source, dict):
            raise FetchError(f"every source must be an object, got {type(source).__name__}")
        sid = source.get("id", "")
        if not isinstance(sid, str) or not IDENT.fullmatch(sid) or sid in seen:
            raise FetchError(f"invalid or duplicate source id: {sid!r}")
        seen.add(sid)
        if not isinstance(source.get("licence"), str) or not source["licence"]:
            raise FetchError(f"{sid}: licence is required")
        arms = source.get("arms", [])
        if not isinstance(arms, list) or not all(isinstance(arm, str) for arm in arms):
            raise FetchError(f"{sid}: arms must be a list of strings")
        if not isinstance(source.get("optional", False), bool):
            raise FetchError(f"{sid}: optional must be true or false")
        if source.get("kind") == "git":
            commit, url = source.get("commit"), source.get("url")
            if not isinstance(commit, str) or not REVISION.fullmatch(commit) or not isinstance(url, str) \
                    or not url.startswith("https://"):
                raise FetchError(f"{sid}: git sources need an https url and a full commit")
        elif source.get("kind") == "hf":
            repo, revision = source.get("repo"), source.get("revision")
            if not isinstance(repo, str) or not REPO.fullmatch(repo) or not isinstance(revision, str) \
                    or not REVISION.fullmatch(revision):
                raise FetchError(f"{sid}: hf sources need owner/name and a full revision")
            files = source.get("files")
            if not isinstance(files, list) or not files:
                raise FetchError(f"{sid}: hf sources need a files list")
            names = set()
            for entry in files:
                if not isinstance(entry, dict):
                    raise FetchError(f"{sid}: every file entry must be an object")
                name = entry.get("path")
                if not isinstance(name, str):
                    raise FetchError(f"{sid}: file path must be a string")
                safe_relative(name)
                if name in names or name == "SHA256SUMS":
                    raise FetchError(f"{sid}: {name}: duplicate or reserved file path")
                names.add(name)
                size = entry.get("bytes")
                if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
                    raise FetchError(f"{sid}: {name}: bytes must be a positive integer")
                if "sha256" not in entry:
                    raise FetchError(f"{sid}: {name}: sha256 key is required (null for a non-LFS file)")
                digest, blob = entry["sha256"], entry.get("git_blob_sha1")
                if digest is not None and (not isinstance(digest, str) or not SHA256.fullmatch(digest)):
                    raise FetchError(f"{sid}: {name}: sha256 must be lowercase hex or null")
                if blob is not None and (not isinstance(blob, str) or not SHA1.fullmatch(blob)):
                    raise FetchError(f"{sid}: {name}: git_blob_sha1 must be 40 lowercase hex characters")
                if digest is None and blob is None:
                    raise FetchError(f"{sid}: {name}: needs a declared sha256 or git_blob_sha1; unhashed files are refused")
        else:
            raise FetchError(f"{sid}: unknown kind {source.get('kind')!r}")
    return doc


def safe_relative(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts) or "\\" in name:
        raise FetchError(f"unsafe file path: {name!r}")
    return path


def checkouts(root=ROOT):
    """Every checkout of this repository: the one running the script, the main work tree and each linked worktree."""
    found = {root}
    try:
        listed = subprocess.run(["git", "-C", str(root), "worktree", "list", "--porcelain"], capture_output=True,
                                text=True, timeout=10, check=False)
        common = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return found
    if listed.returncode == 0:
        for line in listed.stdout.splitlines():
            if line.startswith("worktree "):
                found.add(Path(line[len("worktree "):]).resolve())
    if common.returncode == 0 and common.stdout.strip():
        found.add(Path(common.stdout.strip()).resolve().parent)
    return found


def resolve_dest(dest, root=ROOT):
    chosen = Path(dest) if dest else Path(os.environ[DEST_ENV]) if os.environ.get(DEST_ENV) else DEFAULT_DEST
    resolved = chosen.expanduser().resolve()
    for checkout in checkouts(root):
        if resolved == checkout or checkout in resolved.parents:
            raise FetchError("destination is inside a checkout of the repository; weights stay outside the public tree")
    return resolved


def select(doc, only=(), arms=(), include_optional=False):
    """Pick sources. Optional sources join with --include-optional, by --only id, or when an --arm prefix
    names an optional arm (for example D3-rented) that the source serves."""
    chosen = []
    known = {source["id"] for source in doc["sources"]}
    missing = sorted(set(only) - known)
    if missing:
        raise FetchError(f"unknown source ids: {', '.join(missing)}")
    optional_arms = set(doc.get("optional_arms", []))
    for source in doc["sources"]:
        if only and source["id"] not in only:
            continue
        matched = [arm for arm in source.get("arms", []) if any(arm.startswith(prefix) for prefix in arms)]
        if arms and not matched:
            continue
        if source.get("optional") and not include_optional and source["id"] not in only \
                and not any(arm in optional_arms for arm in matched):
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


def hf_base(dest, source):
    return dest / "hf" / source["id"]


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
            target = hf_base(dest, source) / safe_relative(entry["path"])
            if target.is_file() and not target.is_symlink():
                state = "present_size_match" if target.stat().st_size == entry["bytes"] else "present_size_mismatch"
            else:
                state = "missing"
                missing += entry["bytes"]
            total += entry["bytes"]
            files.append({"path": entry["path"], "url": file_url(hub, source, entry["path"]), "dest": str(target),
                          "bytes": entry["bytes"], "sha256_declared": entry["sha256"],
                          "git_blob_sha1_declared": entry.get("git_blob_sha1"), "state": state})
        entries.append({"id": source["id"], "repo": source["repo"], "revision": source["revision"],
                        "licence": source["licence"], "arms": source.get("arms", []),
                        "optional": bool(source.get("optional")), "files": files})
    picked = {source["id"] for source in sources}
    excluded = sorted(s["id"] for s in doc["sources"] if s.get("optional") and s["id"] not in picked)
    return {"mode": "dry-run", "dest": str(dest), "hub": hub, "recorded": doc.get("recorded"),
            "hf": entries, "git": git, "optional_excluded": excluded,
            "totals": {"hf_sources": len(entries), "files": sum(len(e["files"]) for e in entries),
                       "bytes": total, "bytes_missing": missing, "git_sources": len(git)},
            "note": "Dry run: nothing was downloaded. Pass --apply to fetch the hf files; git sources are not cloned."}


def blob_hasher(size):
    """The git blob id the Hub reports for a non-LFS file: sha1 over a 'blob <size>\\0' header plus the content."""
    return hashlib.sha1(b"blob %d\0" % size)


def hash_file(path, size):
    # A chunked loop rather than hashlib.file_digest, which needs Python 3.11 (the Mac host's system Python is older).
    sha256, blob = hashlib.sha256(), blob_hasher(size)
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            sha256.update(block)
            blob.update(block)
    return sha256.hexdigest(), blob.hexdigest()


def verify(label, entry, sha256, blob):
    """Check measured hashes against the declared ones; return which declared value matched."""
    declared, declared_blob = entry["sha256"], entry.get("git_blob_sha1")
    if declared is not None:
        if sha256 != declared:
            raise FetchError(f"{label}: sha256 {sha256} does not match the declared {declared}")
        return "matched_declared_sha256"
    if declared_blob is not None:
        if blob != declared_blob:
            raise FetchError(f"{label}: git blob sha1 {blob} does not match the declared {declared_blob}")
        return "matched_declared_git_blob_sha1"
    raise FetchError(f"{label}: no declared sha256 or git_blob_sha1; refusing an unverified file")


def download(url, target, entry, timeout):
    size = entry["bytes"]
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "video-utils-narrate-fetch/1"}),
                                    timeout=timeout) as response:
            if urllib.parse.urlparse(url).scheme == "https" and urllib.parse.urlparse(response.geturl()).scheme != "https":
                raise FetchError(f"{url}: redirected away from https")
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".partial-", delete=False) as output:
                temporary = Path(output.name)
                sha256, blob, count = hashlib.sha256(), blob_hasher(size), 0
                while block := response.read(CHUNK):
                    count += len(block)
                    if count > size:
                        raise FetchError(f"{url}: exceeds its declared {size} bytes")
                    sha256.update(block)
                    blob.update(block)
                    output.write(block)
        if count != size:
            raise FetchError(f"{url}: got {count} bytes, declared {size}")
        digest = sha256.hexdigest()
        check = verify(url, entry, digest, blob.hexdigest())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        temporary = None
        return digest, check
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
        base = hf_base(dest, source)
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
                digest, blob = hash_file(target, entry["bytes"])
                check = verify(str(target), entry, digest, blob)
                if name in sums and sums[name] != digest:
                    raise FetchError(f"{target}: sha256 {digest} differs from the recorded {sums[name]}; remove it to refetch")
                status = "already_present"
            else:
                if target.exists():
                    raise FetchError(f"{target}: existing file has the wrong size; remove it to refetch")
                digest, check = download(url, target, entry, timeout)
                status = "downloaded"
            sums[name] = digest
            # Written after every file, so a failure later in the source keeps the hashes already measured.
            sums_path.write_text("".join(f"{sums[key]}  {key}\n" for key in sorted(sums)), encoding="utf-8")
            records.append({"id": source["id"], "repo": source["repo"], "revision": source["revision"], "path": name,
                            "url": url, "bytes": entry["bytes"], "sha256": digest, "declared_sha256": declared,
                            "declared_git_blob_sha1": entry.get("git_blob_sha1"), "check": check, "status": status})
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
    parser.add_argument("--include-optional", action="store_true", help="also include optional sources (Drama 3, fish-speech, WavLM); "
                        "an --arm naming an optional arm such as D3-rented includes that arm's sources without it")
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
