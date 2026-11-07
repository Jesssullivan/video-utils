"""Bed selection for a campaign job (docs/spec/NARRATED_VIDEO.md, "Bed selection", Linear TIN-7788, ruling TIN-7125
e552e569).

An agent judges whether a job wants a backing bed. When it does, a rule picks 2 or 3 loops from a catalog port, a
monthly guard counts the credits before any download, and the loops enter the private store by digest with a licence
record. The result is one selection file that intake reads. Selection comes before admit, because a job names its bed
when it is written, so it is no row of the render graph and moves no task digest.

Two ports hold everything outside this process, and both are passed in:

- judge.judge(brief) returns the decision: {wanted, reason, query, layers, bpm_min, bpm_max}. FileJudge reads one an
  agent wrote. A job the judge wants no bed for spends nothing and passes bedless;
- catalog.search(query, bpm_min, bpm_max) returns candidate rows {asset_id, type, bpm, key, preview}, and
  catalog.download(asset_id, directory) saves a purchased sound and returns its path. catalog.source, terms_ref and
  terms_read_on fill the licence record. CatalogError is its failure. No adapter ships here, so the command refuses
  bed_catalog_unconfigured on a wanted bed.

A catalog holds no share method. Splice's terms let a sound leave the account only inside a finished work, so this
stage never publishes a stack or a link (docs/research/2026-11-07-splice-terms-campaign-beds.md).

The pick is the rule of the existing record: loops only, never preview audio, the same key as the first usable row,
each layer's tempo factor inside the record's bound, in catalog order. Too few gives a bedless job with no spend.

BedCredits is the guard. One ledger under the store root counts credits per UTC calendar month, with no default
budget. A spend row is written before the download, and a failed download stays counted, because the port cannot say
whether the vendor charged. A sound the ledger already holds costs nothing, because the vendor makes a repeat download
free. The ledger sees only this stage's spend, so it holds a project budget and not the account's balance. It is the
one file here that names a vendor asset id, so a certified licence can be found later. No output or log does.

An agent-acquired record is a campaign's: acquiredBy is {agent: campaign id}, its id binds its digests (bound_id) and
acquisition_problems refuses it on a client edition or on a job root that campaign does not hold. NV-3 stands for every
other job. Nothing here closes a licence PDF or Content ID gate, so deliver_check still decides those.
"""

import contextlib
import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from ..ir import canonical, sha256_file
from .common import StageRefused, ffprobe
from .job import CLIENT_EDITIONS, ID, SHA256, JobError, read_json
from .store import guard_root, load_store_json, utc_now, write_atomic

KIND = "nv_bed_selection"
LEDGER_KIND = "nv_bed_credits"
SCHEMA_VERSION = 1
LEDGER = "bed-credits.json"
LOCK = ".bed-credits.lock"
RULING = "TIN-7125 comment e552e569"
CREDITS_PER_SOUND = 1  # https://support.splice.com/en/articles/14442749: a new sample costs 1, a repeat download 0
LAYERS = (2, 3)  # check.BED_LAYERS
TEMPO_RANGE = (0.5, 2.0)  # check.BED_TEMPO_RANGE
UPPER_LAYER_GAIN_DB = -6.0  # the first loop leads and the rest sit under it; mix sets the bed's level from the voice
MAX_LOOP_BYTES = 256 * 1024 * 1024
MAX_REASON = 200
AUDIO_SUFFIXES = (".wav", ".aif", ".aiff", ".flac", ".mp3")
AGENT_SOURCES = ("Splice",)  # the ruling spends Splice credits, and attributionRequired below is Splice's answer only
LAYER_FIELDS = {"sha256", "bytes", "rateHz", "channels", "source", "bpm", "key", "tempoFactor", "gainDb"}
MONTH = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
LEDGER_ROW = {"month", "asset_id", "credits", "campaign", "job", "recorded_utc", "sha256"}
DECISION_FIELDS = {"wanted", "reason", "query", "layers", "bpm_min", "bpm_max"}
GATE_FIELDS = ("certifiedPdfSha256", "contentIdCheck")  # recorded after selection, so the id does not bind them


class CatalogError(Exception):
    """The catalog port failed. Its text never reaches a refusal, because a vendor's reply may name an asset."""


# The record -----------------------------------------------------------------------------------------------------
def agent_campaign(bed):
    """The campaign id an agent-acquired record names, or None for any other acquiredBy."""
    acquired = bed["acquisition"]["acquiredBy"]
    if not isinstance(acquired, dict) or set(acquired) != {"agent"}:
        return None
    campaign = acquired["agent"]
    return campaign if isinstance(campaign, str) and ID.fullmatch(campaign) else None


def bound_id(bed):
    """bed-<digest> of the record's layers, terms and acquisition. The licence PDF and Content ID results are left out,
    because they arrive after selection and must not move the job that names this bed."""
    body = copy.deepcopy({k: v for k, v in bed.items() if k != "id"})
    for field in GATE_FIELDS:
        body["licence"].pop(field, None)
    return f"bed-{hashlib.sha256(canonical(body).encode()).hexdigest()[:32]}"


def acquisition_problems(bed, edition, campaign, root=None):
    """[(code, detail)] of a record's acquisition on this job. campaign is the campaign holding the job root, or None.
    An operator's record has none. An agent's holds only on a non-client job root bound to the campaign it names, and
    with root, the store root of the job, only when that root's ledger counted every loop. Intake has no root yet, so
    its caller passes none and plan, init and the music stage read the ledger."""
    if bed["acquisition"]["acquiredBy"] == "Operator":
        return []
    named = agent_campaign(bed)
    if named is None:
        return [("bed_acquisition_agent", "acquiredBy is neither Operator nor a campaign's agent")]
    if edition in CLIENT_EDITIONS:
        return [("bed_acquisition_agent", "a client edition takes only a bed the operator acquired (NV-3)")]
    if campaign != named:
        return [("bed_acquisition_agent", "an agent-acquired bed needs the job root bound to the campaign it names")]
    problems = []
    if bed["id"] != bound_id(bed):
        problems.append(("bed_digest_mismatch", "the bed record is not the one its id binds"))
    if not bed["licence"]["termsRef"] or not bed["licence"]["termsReadOn"]:
        problems.append(("bed_licence_missing", "an agent-acquired bed names the terms it read and the date"))
    if any(layer.get("source") not in AGENT_SOURCES for layer in bed["layers"]):
        problems.append(("bed_acquisition_agent", "the ruling lets an agent spend Splice credits and no other source"))
    if root is not None and not {layer["sha256"] for layer in bed["layers"]} <= BedCredits(root).digests():
        problems.append(("bed_unledgered", "a loop of this agent-acquired bed is not in this root's credit ledger"))
    return problems


def bound_campaign(store):
    """The campaign holding this job root, or None."""
    from . import rerun  # rerun reads the graph, and the graph reads this module

    return (rerun.read(store).get("campaign") or {}).get("id")


# The guard ------------------------------------------------------------------------------------------------------
def check_budget(budget):
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
        raise JobError("bed_credit_budget_missing", "a wanted bed needs a monthly credit budget of at least 1")


class BedCredits:
    """The monthly credit ledger under a store root. Every read and write holds its lock."""

    def __init__(self, root, now=utc_now):
        self.root = guard_root(root)
        self.path = self.root / LEDGER
        self.now = now

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.root / LOCK, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def read(self):
        if self.path.is_symlink():
            raise JobError("stage_symlink", f"{LEDGER} is a symlink")
        if not self.path.exists():
            return {"kind": LEDGER_KIND, "schema_version": SCHEMA_VERSION, "rows": []}
        value = load_store_json(self.path)
        rows = value.get("rows") if isinstance(value, dict) else None
        if (
            not isinstance(rows, list)
            or value.get("kind") != LEDGER_KIND
            or value.get("schema_version") != SCHEMA_VERSION
            or not all(valid_row(row) for row in rows)
        ):
            raise JobError("store_invalid", f"{LEDGER} is not a {LEDGER_KIND} record")
        return value

    def spend(self, asset_ids, budget, campaign, job):
        """Count these sounds against this month, or refuse bed_credit_budget and write nothing. {month, credits,
        spent_month, budget}. A sound the ledger holds, from any month, costs nothing."""
        check_budget(budget)
        stamp = self.now()
        month = stamp[:7]
        with self.locked():
            ledger = self.read()
            held = {row["asset_id"] for row in ledger["rows"]}
            new = [asset for asset in asset_ids if asset not in held]
            spent = month_total(ledger["rows"], month)
            credits = len(new) * CREDITS_PER_SOUND
            if spent + credits > budget:
                raise JobError(
                    "bed_credit_budget", f"{credits} new credits on {spent} spent is past the {budget} of {month}"
                )
            if new:
                ledger["rows"] += [
                    {"month": month, "asset_id": asset, "credits": CREDITS_PER_SOUND, "campaign": campaign, "job": job,
                     "recorded_utc": stamp, "sha256": None}
                    for asset in new
                ]  # fmt: skip
                write_atomic(self.path, ledger)
        return {"month": month, "credits": credits, "spent_month": spent + credits, "budget": budget}

    def digests(self):
        """The digest of every counted sound that arrived."""
        with self.locked():
            return {row["sha256"] for row in self.read()["rows"] if row["sha256"] is not None}

    def bind(self, asset_id, sha256):
        """Name the digest a counted sound arrived as, so a licence claim can find it from a layer."""
        with self.locked():
            ledger = self.read()
            rows = [row for row in ledger["rows"] if row["asset_id"] == asset_id and row["sha256"] != sha256]
            for row in rows:
                row["sha256"] = sha256
            if rows:
                write_atomic(self.path, ledger)


def valid_row(row):
    return (
        isinstance(row, dict)
        and set(row) == LEDGER_ROW
        and isinstance(row["month"], str)
        and MONTH.fullmatch(row["month"]) is not None  # a month no stamp can match would never count against a budget
        and isinstance(row["asset_id"], str)
        and bool(row["asset_id"])
        and isinstance(row["credits"], int)
        and not isinstance(row["credits"], bool)
        and row["credits"] >= 0
    )


def month_total(rows, month):
    return sum(row["credits"] for row in rows if row["month"] == month)


# The stage ------------------------------------------------------------------------------------------------------
class FileJudge:
    """The decision an agent wrote to a file. The brief is the agent's own context, so it is not read here."""

    def __init__(self, path):
        self.path = path

    def judge(self, brief):
        return read_json(self.path, "bed decision")


def check_decision(value):
    invalid = JobError("bed_decision_invalid", "the decision is not {wanted, reason} with a query on a wanted bed")
    if not isinstance(value, dict) or set(value) - DECISION_FIELDS or not isinstance(value.get("wanted"), bool):
        raise invalid
    reason = value.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON:
        raise invalid
    query = value.get("query")
    layers = value.get("layers", LAYERS[0])
    bpm = [value.get("bpm_min"), value.get("bpm_max")]
    if value["wanted"] and (
        not isinstance(query, str)
        or not query.strip()
        or len(query) > MAX_REASON  # the query is the one text that reaches the vendor
        or layers not in LAYERS
        or isinstance(layers, bool)
        or not all(b is None or (isinstance(b, int) and not isinstance(b, bool) and b > 0) for b in bpm)
    ):
        raise invalid
    return value | {"layers": layers}


def usable(row):
    """A loop of known tempo and key that a purchase, not a preview, supplies. A preview may not leave the vendor's
    service, and a stack is no Creative Work on its own (Splice Terms 2.3.1.4 (f), 2.5). A row must say it is no
    preview: an absent or unclear mark is not usable, because the terms refuse the other reading."""
    return (
        isinstance(row, dict)
        and isinstance(row.get("asset_id"), str)
        and bool(row["asset_id"])
        and row.get("type") == "loop"
        and row.get("preview") is False
        and isinstance(row.get("bpm"), (int, float))
        and not isinstance(row.get("bpm"), bool)
        and row["bpm"] > 0
        and isinstance(row.get("key"), str)
        and bool(row["key"].strip())
    )


def pick(rows, layers):
    """The first usable row, then the next usable rows in its key whose tempo factor to it is inside the record's
    bound, up to layers. None when fewer than two fit. Catalog order decides, so a replayed search picks the same."""
    picked, seen = [], set()
    for row in rows if isinstance(rows, list) else []:
        if not usable(row) or row["asset_id"] in seen:
            continue
        if picked:
            factor = picked[0]["bpm"] / row["bpm"]
            if row["key"].casefold() != picked[0]["key"].casefold() or not TEMPO_RANGE[0] <= factor <= TEMPO_RANGE[1]:
                continue
        picked.append(row)
        seen.add(row["asset_id"])
        if len(picked) == layers:
            break
    return picked if len(picked) >= LAYERS[0] else None


def port_call(method, *args):
    try:
        return method(*args)
    except CatalogError:
        raise JobError("bed_catalog_failed", "the catalog port failed; a counted spend stays counted") from None


def put_in_store(path, digest, store_dir):
    """Copy a file into the private store as <digest><suffix>, once."""
    suffix = path.suffix.lower() if path.suffix.lower() in AUDIO_SUFFIXES else ".bin"
    target = Path(store_dir) / f"{digest}{suffix}"
    if target.is_symlink() or (target.exists() and sha256_file(target) != digest):
        raise JobError("store_conflict", f"the store holds a different file named {target.name}")
    if not target.exists():
        fd, name = tempfile.mkstemp(prefix=".bed-", suffix=".part", dir=store_dir)
        os.close(fd)
        try:
            shutil.copyfile(path, name)  # mkstemp's 0600 stays: a raw loop leaves only inside a finished work
            os.replace(name, target)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(name)
            raise
    return target


def fetch(catalog, row, work, store_dir):
    """One purchased loop in the private store: (sha256, bytes, rate, channels). The returned path is the port's."""
    path = Path(port_call(catalog.download, row["asset_id"], work))
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_LOOP_BYTES:
        raise JobError("bed_loop_unreadable", "the catalog's file is not a regular audio file of a usable size")
    try:
        streams = [s for s in ffprobe(path).get("streams", []) if s.get("codec_type") == "audio"]
    except StageRefused:
        raise JobError("bed_loop_unreadable", "the catalog's file is not audio FFprobe can read") from None
    if len(streams) != 1 or not int(streams[0].get("sample_rate") or 0) or not streams[0].get("channels"):
        raise JobError("bed_loop_unreadable", "the catalog's file holds no one audio stream of known rate and channels")
    digest = sha256_file(path)
    put_in_store(path, digest, store_dir)
    return digest, path.stat().st_size, int(streams[0]["sample_rate"]), int(streams[0]["channels"])


def selection_record(campaign, decision, outcome, bed, credits, reason, stamp):
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "linear": "TIN-7788",
        "ruling": RULING,
        "campaign": campaign,
        "outcome": outcome,
        "bedless_reason": reason,
        "decision": {"wanted": decision["wanted"], "reason": decision["reason"], "query": decision.get("query")},
        "bed": bed,
        "credits": credits,
        "recorded_utc": stamp,
    }


def select_bed(brief, judge, catalog, *, campaign, budget, root, store_dir, job=None, now=utc_now):
    """A selection record: outcome bedless, or selected with its bed record. A refusal spends nothing unless it names a
    counted spend, and a later selection with a bedless decision still gives a job that passes, so no refusal here
    stops a video."""
    if not isinstance(campaign, str) or ID.fullmatch(campaign) is None:
        raise JobError("campaign_id_invalid", "a campaign id is 1 to 64 of a-z, 0-9, '.', '_' and '-'")
    decision = check_decision(judge.judge(brief))
    stamp = now()
    if not decision["wanted"]:
        return selection_record(campaign, decision, "bedless", None, None, "not_wanted", stamp)
    if catalog is None:
        raise JobError("bed_catalog_unconfigured", "this worker has no catalog port, so a wanted bed cannot be met")
    check_budget(budget)
    if not store_dir or not Path(store_dir).is_dir():
        raise JobError("store_missing", "a selected loop goes into the private store: pass --store or NARRATE_STORE")
    if catalog.source not in AGENT_SOURCES or not catalog.terms_ref or not catalog.terms_read_on:
        raise JobError("bed_licence_missing", "the catalog names no ruled source, terms and read date for the record")
    rows = port_call(catalog.search, decision["query"], decision.get("bpm_min"), decision.get("bpm_max"))
    picked = pick(rows, decision["layers"])
    if picked is None:
        return selection_record(campaign, decision, "bedless", None, None, "no_candidates", stamp)
    ledger = BedCredits(root, now)
    spent = ledger.spend([row["asset_id"] for row in picked], budget, campaign, job)
    layers = []
    with tempfile.TemporaryDirectory(prefix="bed-select-") as work:
        for i, row in enumerate(picked):
            digest, size, rate, channels = fetch(catalog, row, Path(work), store_dir)
            ledger.bind(row["asset_id"], digest)
            layers.append(
                {
                    "sha256": digest,
                    "bytes": size,
                    "rateHz": rate,
                    "channels": channels,
                    "source": catalog.source,
                    "bpm": row["bpm"],
                    "key": row["key"],
                    "tempoFactor": round(picked[0]["bpm"] / row["bpm"], 6),
                    "gainDb": 0.0 if i == 0 else UPPER_LAYER_GAIN_DB,
                }
            )
    if len({layer["sha256"] for layer in layers}) != len(layers):
        raise JobError("bed_layers_invalid", "two catalog rows gave one file, and a bed arranges distinct loops")
    bed = {
        "id": "",
        "layers": layers,
        "licence": {
            "termsRef": catalog.terms_ref,
            "termsReadOn": catalog.terms_read_on,
            "attributionRequired": False,
            "attributionText": None,
            "certifiedPdfSha256": None,
            "contentIdCheck": "NotRun",
        },
        "acquisition": {
            "acquiredBy": {"agent": campaign},
            "date": stamp[:10],
            "creditsSpent": spent["credits"],
            "rulingRef": RULING,
        },
    }
    bed["id"] = bound_id(bed)
    return selection_record(campaign, decision, "selected", bed, spent, None, stamp)


def write_selection(path, selection):
    """Write the selection file once: out_exists on a file already there, so a recorded choice is never overwritten."""
    try:
        with open(path, "x", encoding="utf-8") as out:
            out.write(json.dumps(selection, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    except FileExistsError:
        raise JobError("out_exists", "--out already holds a selection") from None


def summary(selection):
    """What a command prints: outcome, ids, digests and counts. The decision's words stay in the private file."""
    bed = selection["bed"]
    return {
        "ok": True,
        "outcome": selection["outcome"],
        "bedless_reason": selection["bedless_reason"],
        "campaign": selection["campaign"],
        "bed": None if bed is None else bed["id"],
        "layers": [] if bed is None else [layer["sha256"] for layer in bed["layers"]],
        "credits": selection["credits"],
    }


def read_selection(path, campaign):
    """(selection, its file's sha256), checked for the campaign intake was given. An agent's record must be the one its
    id binds, name this campaign, hold every layer field and arrive with its licence gates open: select_bed writes them
    open, and the id leaves them out, so a file that says clear has been edited and nothing else would show it."""
    value = read_json(path, "bed selection")
    invalid = JobError("bed_selection_invalid", "the file is not a bed selection this stage wrote")
    if not isinstance(value, dict) or value.get("kind") != KIND or value.get("schema_version") != SCHEMA_VERSION:
        raise invalid
    if value.get("campaign") != campaign:
        raise JobError("bed_selection_campaign", "the selection names another campaign")
    bed = value.get("bed")
    if value.get("outcome") == "bedless" and bed is None:
        return value, sha256_file(path)
    if value.get("outcome") != "selected" or not isinstance(bed, dict):
        raise invalid
    try:
        digests = [layer["sha256"] for layer in bed["layers"]]
        sizes = [layer["bytes"] for layer in bed["layers"]]
        bound = bed["id"] == bound_id(bed) and agent_campaign(bed) == campaign
        open_gates = bed["licence"]["certifiedPdfSha256"] is None and bed["licence"]["contentIdCheck"] == "NotRun"
        shaped = all(set(layer) == LAYER_FIELDS for layer in bed["layers"])
    except (AttributeError, KeyError, TypeError):
        raise invalid from None
    # The id is computed from the record, so it shows no edit by itself. check_loops reads each digest's store file.
    well_formed = all(isinstance(d, str) and SHA256.fullmatch(d) for d in digests) and all(
        isinstance(n, int) and not isinstance(n, bool) for n in sizes
    )
    if not bound or not well_formed or not open_gates or not shaped:
        raise invalid
    return value, sha256_file(path)


def check_loops(bed, store_dir):
    """Every layer in the store, by digest and byte count: bed_loop_missing or bed_digest_mismatch."""
    for i, layer in enumerate(bed["layers"]):
        found = [p for p in sorted(Path(store_dir).glob(f"{layer['sha256']}.*")) if p.is_file() and not p.is_symlink()]
        if not found:
            raise JobError("bed_loop_missing", f"bed layer {i} is not in the store")
        if found[0].stat().st_size != layer["bytes"] or sha256_file(found[0]) != layer["sha256"]:
            raise JobError("bed_digest_mismatch", f"bed layer {i} in the store is not the record's")
