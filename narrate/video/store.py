"""The content-addressed stage store (docs/spec/NARRATED_VIDEO.md, "Stage keys and the store").

    artifacts/narrated/<job_id>/
      job.json        the NarratedVideo record (dhall-to-json render)
      graph.json      the last recorded plan (plan --record, init)
      current.json    {stages: {node: {key, dir, content_sha256}}, refusals: {node: {key, code, detail}}}
      history/        stage directories that failed re-hashing, moved aside
      stages/<stage>[/<segment>]/<key16>/   one finished stage: its outputs and manifest.json

A stage writes into <key16>.partial/ and is renamed into place when done; current.json then points at it. current.json
replaces symlinks, and a symlink anywhere in a stage directory makes it corrupt. Freshness re-hashes every output and
never reads an mtime. The store lives outside artifacts/runs/ and outside artifacts/narrate/, so no guitar tool and
no narrate run reader ever sees it. v1 keeps every stage directory until the operator removes the job (no gc).
"""

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ..config import ROOT, in_guitar_runs
from ..ir import sha256_file
from . import keys
from .job import ID, JobError, check_shape

DEFAULT_ROOT = ROOT / "artifacts" / "narrated"
NARRATE_RUNS = ROOT / "artifacts" / "narrate"
ROOT_ENV = "NARRATED_VIDEO_ROOT"
SCHEMA_VERSION = 1
MANIFEST = "manifest.json"
PARTIAL = ".partial"


class StoreError(JobError):
    """The store refuses a path or finds a directory it cannot trust."""


def guard_root(path):
    path = Path(path).resolve()
    if in_guitar_runs(path):
        raise StoreError("store_in_guitar_runs", "the narrated-video store lives outside artifacts/runs/")
    narrate = NARRATE_RUNS.resolve()
    if path == narrate or narrate in path.parents:
        raise StoreError("store_in_narrate_runs", "the narrated-video store lives outside artifacts/narrate/")
    return path


def utc_now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_commit():
    """The checkout's commit, recorded in stage manifests and kept out of every key. None outside a git checkout."""
    try:
        done = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = done.stdout.strip()
    return commit if done.returncode == 0 and len(commit) == 40 else None


def write_atomic(path, value):
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def node_parts(node_id):
    """'voice/seg-1' -> ('voice', 'seg-1'); 'base' -> ('base', None). Both parts are path-safe ids."""
    stage, _, segment = node_id.partition("/")
    if not ID.match(stage) or (segment and not ID.match(segment)) or "/" in segment:
        raise StoreError("node_invalid", f"{node_id!r} is not a stage[/segment] id")
    return stage, segment or None


def files_under(directory):
    """{relative posix path: Path} of every regular file under directory. A symlink anywhere raises StoreError."""
    found = {}
    for here, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs + files:
            path = Path(here) / name
            if path.is_symlink():
                raise StoreError("stage_symlink", f"{path.relative_to(directory).as_posix()} is a symlink")
        for name in files:
            path = Path(here) / name
            found[path.relative_to(directory).as_posix()] = path
    return found


def verify_stage_dir(directory, key=None):
    """Problems with one finished stage directory: [] when it re-hashes and its manifest holds."""
    directory = Path(directory)
    if directory.is_symlink():
        return ["stage_symlink: the stage directory is a symlink"]
    if not directory.is_dir():
        return ["dir_missing: the stage directory does not exist"]
    try:
        files = files_under(directory)
    except StoreError as exc:
        return [f"{exc.code}: {exc.detail}"]
    if MANIFEST not in files:
        return ["manifest_missing: no manifest.json"]
    try:
        manifest = json.loads(files.pop(MANIFEST).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"manifest_invalid: {exc}"]
    if not isinstance(manifest, dict) or manifest.get("kind") != "nv_stage":
        return ["manifest_invalid: kind is not nv_stage"]
    problems = []
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        return ["manifest_invalid: outputs is not an object"]
    for name in sorted(set(files) - set(outputs)):
        problems.append(f"unlisted_file: {name}")
    for name, want in sorted(outputs.items()):
        if name not in files:
            problems.append(f"output_missing: {name}")
        elif sha256_file(files[name]) != want:
            problems.append(f"output_digest_mismatch: {name}")
    if manifest.get("content_sha256") != keys.content_digest(manifest):
        problems.append("content_digest_mismatch: content_sha256 differs from the manifest")
    document = manifest.get("key_document")
    if not isinstance(document, dict) or keys.stage_key(document) != manifest.get("stage_key"):
        problems.append("key_mismatch: stage_key is not the digest of key_document")
    if key is not None and manifest.get("stage_key") != key:
        problems.append("key_mismatch: the manifest's stage_key is not the key current.json records")
    if directory.name != keys.key16(str(manifest.get("stage_key"))):
        problems.append("key_mismatch: the directory name is not the stage key's first 16 characters")
    return problems


def load_store_json(path):
    """A store file's JSON, or StoreError store_invalid when it is not UTF-8 JSON (a damaged or hand-edited file)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoreError("store_invalid", f"{Path(path).name}: {exc}") from None


class JobStore:
    def __init__(self, root, job_id):
        if not isinstance(job_id, str) or not ID.match(job_id):
            raise StoreError("job_invalid", "a job id is 1 to 64 of a-z, 0-9, '.', '_' and '-'")
        self.root = guard_root(root)
        self.dir = self.root / job_id
        self.job_id = job_id
        if self.dir.is_symlink():
            raise StoreError("stage_symlink", "the job directory is a symlink")

    # Paths ----------------------------------------------------------------------------------------------------
    @property
    def job_file(self):
        return self.dir / "job.json"

    @property
    def graph_file(self):
        return self.dir / "graph.json"

    @property
    def current_file(self):
        return self.dir / "current.json"

    @property
    def history(self):
        return self.dir / "history"

    def node_dir(self, node_id):
        stage, segment = node_parts(node_id)
        base = self.dir / "stages" / stage
        return base / segment if segment else base

    def final_dir(self, node_id, key):
        return self.node_dir(node_id) / keys.key16(key)

    def partial_dir(self, node_id, key):
        return self.node_dir(node_id) / (keys.key16(key) + PARTIAL)

    # Job -------------------------------------------------------------------------------------------------------
    def exists(self):
        return self.job_file.is_file()

    def write_job(self, job, replace=False):
        check_shape(job)
        if job["id"] != self.job_id:
            raise StoreError("job_invalid", "the record's id is not the job id")
        if self.exists() and not replace and self.read_job() != job:
            raise StoreError("job_exists", f"{self.job_id} already holds a different job; pass --replace")
        self.dir.mkdir(parents=True, exist_ok=True)
        write_atomic(self.job_file, job)

    def read_job(self):
        if self.job_file.is_symlink() or not self.job_file.is_file():
            raise StoreError("job_missing", f"no job {self.job_id} in the store; run init first")
        try:
            job = json.loads(self.job_file.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StoreError("job_invalid", f"job.json: {exc}") from None
        return check_shape(job)

    def write_graph(self, graph):
        self.dir.mkdir(parents=True, exist_ok=True)
        write_atomic(self.graph_file, graph)

    def read_graph(self):
        if self.graph_file.is_symlink():
            raise StoreError("stage_symlink", "graph.json is a symlink")
        if not self.graph_file.is_file():
            raise StoreError("graph_missing", f"{self.job_id} has no recorded plan; run plan --record")
        value = load_store_json(self.graph_file)
        if not isinstance(value, dict) or value.get("kind") != "nv_graph":
            raise StoreError("store_invalid", "graph.json is not an nv_graph object; run plan --record")
        return value

    # current.json ----------------------------------------------------------------------------------------------
    def current(self):
        if self.current_file.is_symlink():
            raise StoreError("stage_symlink", "current.json is a symlink")
        if not self.current_file.is_file():
            return {"schema_version": SCHEMA_VERSION, "stages": {}, "refusals": {}}
        value = load_store_json(self.current_file)
        if not isinstance(value, dict):
            raise StoreError("store_invalid", "current.json is not an object")
        value.setdefault("stages", {})
        value.setdefault("refusals", {})
        for table in ("stages", "refusals"):
            rows = value[table]
            if not isinstance(rows, dict) or not all(
                isinstance(row, dict) and isinstance(row.get("key"), str) for row in rows.values()
            ):
                raise StoreError("store_invalid", f"current.json {table} is not a table of entries with keys")
        if not all(isinstance(row.get("dir"), str) for row in value["stages"].values()):
            raise StoreError("store_invalid", "current.json has a stage entry without a dir")
        return value

    def entry(self, node_id):
        return self.current()["stages"].get(node_id)

    def manifest(self, node_id):
        """The current manifest of a node, or None."""
        entry = self.entry(node_id)
        if entry is None:
            return None
        path = self.dir / entry["dir"] / MANIFEST
        if path.is_symlink() or not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    # Writing a stage -------------------------------------------------------------------------------------------
    def begin(self, node_id, key):
        """A fresh, empty <key16>.partial/ for the stage to write into. A leftover partial is removed first."""
        partial = self.partial_dir(node_id, key)
        if partial.is_symlink():
            raise StoreError("stage_symlink", "a partial stage directory is a symlink")
        if partial.exists():
            shutil.rmtree(partial)
        partial.mkdir(parents=True)
        return partial

    def abort(self, node_id, key):
        partial = self.partial_dir(node_id, key)
        if partial.exists() and not partial.is_symlink():
            shutil.rmtree(partial)

    def commit(self, node_id, key, document, fields):
        """Hash the partial directory's files, write its manifest, rename it into place and point current.json at
        it. fields holds the manifest's stage-specific parts (knobs, inputs, measurements, labels, timeline...)."""
        if keys.stage_key(document) != key:
            raise StoreError("key_mismatch", "the key is not the digest of its key document")
        stage, segment = node_parts(node_id)
        partial = self.partial_dir(node_id, key)
        files = files_under(partial)
        files.pop(MANIFEST, None)
        final = self.final_dir(node_id, key)
        manifest = {
            "kind": "nv_stage",
            "schema_version": SCHEMA_VERSION,
            "stage": stage,
            "segment": segment,
            "job_id": self.job_id,
            "stage_key": key,
            "key_document": document,
            "impl": document["impl"],
            "tool": document["tool"],
            "ffmpeg": document["ffmpeg"],
            "edition": document["edition"],
            "knobs": document["knobs"],
            "inputs": document["inputs"],
            "outputs": {name: sha256_file(path) for name, path in sorted(files.items())},
            "measurements": {},
            "labels": {},
            "timeline": None,
            "states": {},
            "refusal": None,
        } | fields
        manifest |= {
            "run_dir": final.relative_to(ROOT).as_posix() if ROOT in final.parents else None,
            "created_utc": utc_now(),
            "commit": git_commit(),
        }
        manifest["content_sha256"] = keys.content_digest(manifest)
        (partial / MANIFEST).write_text(
            json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if final.exists():
            # The same key ran before (its current entry was archived or dropped): keep the finished directory
            # when it still verifies, else move it aside.
            if verify_stage_dir(final, key):
                self._move_to_history(final)
            else:
                shutil.rmtree(partial)
                manifest = json.loads((final / MANIFEST).read_text(encoding="utf-8"))
        if partial.exists():
            os.rename(partial, final)
        current = self.current()
        current["stages"][node_id] = {
            "key": key,
            "dir": final.relative_to(self.dir).as_posix(),
            "content_sha256": manifest["content_sha256"],
        }
        current["refusals"].pop(node_id, None)
        write_atomic(self.current_file, current)
        return manifest

    def record_refusal(self, node_id, key, code, detail):
        """A stage that refused for this key stays refused until its key changes."""
        self.dir.mkdir(parents=True, exist_ok=True)
        current = self.current()
        current["refusals"][node_id] = {"key": key, "code": code, "detail": detail}
        write_atomic(self.current_file, current)

    def clear_refusal(self, node_id):
        """Drop a node's recorded refusal so it plans stale again; the refusal, or None. Only a verdict is ever
        recorded (kitpip.KitpipRefused.verdict), so this is the operator's path after fixing what the key does not
        hold, such as the host environment. `run --force` (lane L4) calls it."""
        current = self.current()
        refusal = current["refusals"].pop(node_id, None)
        if refusal is not None:
            write_atomic(self.current_file, current)
        return refusal

    # Freshness -------------------------------------------------------------------------------------------------
    def freshness(self, node_id, key):
        """(state, reason) for a node whose key is now `key`: fresh, stale, refused or corrupt."""
        current = self.current()
        refusal = current["refusals"].get(node_id)
        if refusal is not None and refusal["key"] == key:
            return "refused", refusal["code"]
        entry = current["stages"].get(node_id)
        if entry is None:
            return "stale", "no_run"
        if entry["key"] != key:
            return "stale", "key_changed"
        problems = verify_stage_dir(self.dir / entry["dir"], key)
        if problems:
            return "corrupt", problems[0]
        return "fresh", None

    def _move_to_history(self, directory):
        self.history.mkdir(parents=True, exist_ok=True)
        flat = directory.relative_to(self.dir / "stages").as_posix().replace("/", "--")
        target = self.history / f"{flat}--{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        os.rename(directory, target)
        return target

    def archive(self, node_id):
        """Move a node's current directory to history/ and drop its entry, so the node becomes stale."""
        current = self.current()
        entry = current["stages"].pop(node_id, None)
        if entry is None:
            return None
        directory = self.dir / entry["dir"]
        target = self._move_to_history(directory) if directory.exists() or directory.is_symlink() else None
        write_atomic(self.current_file, current)
        return target

    def verify(self):
        """{node: problems} over every current entry; a job with no problems maps every node to []."""
        return {
            node: verify_stage_dir(self.dir / entry["dir"], entry["key"])
            for node, entry in sorted(self.current()["stages"].items())
        }
