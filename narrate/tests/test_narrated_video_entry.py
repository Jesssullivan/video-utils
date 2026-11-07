"""The entry gates as a DAG runs them (narrate/video/entry.py, docs/spec/NARRATED_VIDEO.md "Entry gates", Linear
TIN-7788, ruling TIN-7125 0690fe88). A planted wrong number, bad slide and lexical Error each refuse before any voice,
then route to a round and pass once fixed. An absent tool refuses. Each command is the real one on a synthetic bundle.
The xoxd-lexical CLI here is a stub this file writes. No model, GPU, engine or network runs, and no test here signals a
process.
"""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from test_narrated_video_intake import (  # noqa: F401  (fixtures)
    ENGINE,
    TEMPLATE,
    VOICE,
    manifest,
    no_whisper,
    set_claims,
    set_manifest,
    set_script,
    ws,
)

from narrate import lexical, spoken
from narrate.config import ROOT
from narrate.video import (
    bundle,
    claims,
    cli,
    entry,
    findings,
    private_terms,
    render_stage,
    rerun,
    store,
)
from narrate.video.job import JobError

JOB = "demo-fixture"
CAMPAIGN = "campaign-fixture"
PROOF = {"build": {"ms": 17.877, "unit": "ms"}, "cache": {"rate": 42}, "files": [400]}
POINTERS = {"build-ms": "/build/ms", "cache-rate": "/cache/rate", "files": "/files/0"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_proof(b, value=None):
    data = json.dumps(PROOF if value is None else value).encode()
    (b / "proof.json").write_bytes(data)
    return sha(data)


def source_all(b, value=None):
    """Point every claim of the fixture bundle at proof.json."""
    digest = write_proof(b, value)

    def edit(rows):
        for row in rows:
            row["source"] = {"path": "proof.json", "sha256": digest, "pointer": POINTERS[row["id"]]}

    set_claims(b, edit)


class Root:
    """One job root that only the entry commands build."""

    def __init__(self, w, base, knobs=True):
        self.w, self.root, self.bundles = w, base / "narrated", w["bundle"].parent
        self.common = ["--root", str(self.root), "--store", str(w["store"]), "--lexical", str(w["lexical"])]
        self.common += ["--bundles", str(self.bundles)]
        self.store = store.JobStore(self.root, JOB)
        source_all(w["bundle"])
        if knobs:
            self.knobs()

    def knobs(self, **changes):
        value = {"kind": entry.KNOBS_KIND, "schema_version": 1, "narrate_template": TEMPLATE, "voice": VOICE}
        value |= {"engine": ENGINE, "persona": None, "tail_s": None} | changes
        (self.bundles / f"{JOB}.entry.json").write_text(json.dumps(value))

    def gate(self, phase, capsys):
        """(exit, stdout, refusal code) of one gate."""
        capsys.readouterr()
        records = ["--records", str(self.w["records"])]
        code = cli.main(["entry", phase, JOB, *self.common, *(records if phase == "intake" else [])])
        shown = capsys.readouterr()
        lines = [json.loads(line) for line in shown.err.splitlines() if line.startswith("{")]
        return code, json.loads(shown.out) if shown.out.strip() else None, lines[-1]["refused"] if lines else None

    def bind(self, capsys):
        argv = ["campaign-bind", JOB, "--campaign", CAMPAIGN, "--root", str(self.root), "--before-intake"]
        assert cli.main(argv) == 0
        capsys.readouterr()

    def findings(self, capsys):
        capsys.readouterr()
        assert cli.main(["findings", JOB, "--root", str(self.root)]) == 0
        return json.loads(capsys.readouterr().out)

    def round(self, capsys, report, tmp_path):
        path = tmp_path / f"report-{sha(json.dumps(report).encode())[:12]}.json"
        path.write_text(json.dumps(report))
        capsys.readouterr()
        assert cli.main(["round", JOB, "--findings", str(path), "--root", str(self.root)]) == 0
        return json.loads(capsys.readouterr().out)

    def stages(self, capsys, *names):
        capsys.readouterr()
        argv = ["run", JOB, "--stages", ",".join(names), "--root", str(self.root), "--store", str(self.w["store"])]
        assert cli.main([*argv, "--lexical", str(self.w["lexical"]), "--json"]) == 0
        return json.loads(capsys.readouterr().out)

    def voiced(self):
        return [node for node in self.store.current()["stages"] if node.startswith("voice")]


@pytest.fixture
def root(ws, tmp_path, ffmpeg):  # noqa: F811
    return Root(ws, tmp_path)


def stub_cli(base, *, version=None, findings_when=None, check_exit=None, stderr="", no_check=False, exit_one=None):
    """An executable xoxd-lexical stub in base/bin, on PATH for the caller. It answers as the real CLI's documented exit
    codes do: 0, 1 with a JSON findings report, 2 for a fault. It reads a Markdown file and nothing else, as the real
    Vale reads the narration register's Error rules: stdin reaches it as plain text, which holds no finding. exit_one is
    a report to print with exit 1 whatever the text."""
    bin_dir = base / "bin"
    bin_dir.mkdir(exist_ok=True)
    tool = bin_dir / "xoxd-lexical"
    report = {"tool": "xoxd-lexical", "findings": [{"id": "XL-FIX-001", "severity": "error", "line": 1}]}
    tool.write_text(
        f"""#!{sys.executable} -I
import sys
args = sys.argv[1:]
if args[:1] == ["version"]:
    print({version!r})
    sys.exit(0)
if args[:2] == ["check", "--help"]:
    sys.exit({1 if no_check else 0})
text = open(args[-1], encoding="utf-8").read() if args[-1].endswith(".md") else ""
if {exit_one!r} is not None:
    print({exit_one!r})
    sys.exit(1)
if {check_exit!r} is not None:
    sys.stderr.write({stderr!r})
    sys.exit({check_exit!r})
if {findings_when!r} is not None and {findings_when!r} in text:
    print({json.dumps(json.dumps(report))})
    sys.exit(1)
print('{{"findings": []}}')
"""
    )
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def path_with(monkeypatch, bin_dir):
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


# The evidence bar -------------------------------------------------------------------------------------------------


def test_a_wrong_number_refuses_before_spend_then_routes_to_a_fix_and_passes(root, capsys, tmp_path):
    source_all(root.w["bundle"], PROOF | {"build": {"ms": 12.5}})
    root.bind(capsys)

    code, shown, refused = root.gate("claims", capsys)
    assert (code, refused) == (1, "claim_value_mismatch")
    assert shown["findings"]["codes"] == {"claim_value_mismatch": 1}
    assert not root.store.exists() and root.voiced() == []
    assert "12.5" not in json.dumps(shown), "the measured number never reaches a report"

    report = root.findings(capsys)
    assert report["codes"] == {"claim_value_mismatch": 1} and report["blocking"] == 1
    assert report["video_sha256"] is None
    assert report["job_sha256"] == store.tree_sha256(root.w["bundle"])
    assert report["findings"][0]["stage"] == "script"

    first = root.round(capsys, report, tmp_path)
    assert (first["result"], first["round"], first["recorded"]) == ("round", 1, True)
    assert "voice" in first["reach"]

    # The same refusal on the same bundle spends no round: a fix that changed nothing stops here.
    assert root.gate("claims", capsys)[2] == "claim_value_mismatch"
    again = root.round(capsys, root.findings(capsys), tmp_path)
    assert (again["round"], again["recorded"]) == (1, False)

    source_all(root.w["bundle"])
    code, shown, _ = root.gate("claims", capsys)
    assert code == 0 and shown["findings"]["ok"] is True
    assert root.store.entry_refused() is None
    assert root.gate("intake", capsys)[0] == 0
    assert root.store.exists() and root.voiced() == []
    job = root.store.read_job()
    assert job["id"] == JOB and job["edition"] == bundle.EDITION == rerun.INTAKE_EDITION
    assert root.findings(capsys)["job_sha256"] != report["job_sha256"]


def test_a_fix_that_is_still_wrong_starts_the_next_round_on_the_same_job_json(root, capsys, tmp_path):
    root.bind(capsys)
    assert root.gate("intake", capsys)[0] == 0
    held = root.store.read_job()

    source_all(root.w["bundle"], PROOF | {"cache": {"rate": 40}})
    assert root.gate("claims", capsys)[2] == "claim_value_mismatch"
    assert root.store.read_job() == held, "a refused bundle leaves the job as it was"
    assert root.round(capsys, root.findings(capsys), tmp_path)["round"] == 1
    source_all(root.w["bundle"], PROOF | {"files": [401]})
    assert root.gate("claims", capsys)[2] == "claim_value_mismatch"
    assert root.round(capsys, root.findings(capsys), tmp_path)["round"] == 2


def test_a_planted_bad_slide_refuses_before_spend_then_routes_to_a_fix_and_passes(root, capsys, tmp_path):
    b = root.w["bundle"]
    good = (b / "assets" / "slide-a.png").read_bytes()
    bad = letterbox(tmp_path)
    (b / "assets" / "slide-a.png").write_bytes(bad)
    m = manifest(b)
    m["assets"][0] |= {"sha256": sha(bad), "size": {"w": 320, "h": 100}}
    set_manifest(b, m)
    root.bind(capsys)
    assert root.gate("claims", capsys)[0] == 0
    assert root.gate("intake", capsys)[0] == 0

    code, shown, refused = root.gate("preflight", capsys)
    assert (code, refused) == (1, "slide_letterbox")
    assert root.voiced() == []

    report = root.findings(capsys)
    assert report["codes"].get("slide_letterbox") == 1
    first = root.round(capsys, report, tmp_path)
    assert first["round"] == 1 and first["reach"][0] == "compose" and "voice" not in first["reach"]

    (b / "assets" / "slide-a.png").write_bytes(good)
    m["assets"][0] |= {"sha256": sha(good), "size": {"w": 320, "h": 180}}
    set_manifest(b, m)
    assert root.gate("claims", capsys)[0] == 0
    assert root.gate("intake", capsys)[0] == 0
    code, shown, _ = root.gate("preflight", capsys)
    assert code == 0 and shown["preflight_sha256"]
    assert "slide_letterbox" not in root.findings(capsys)["codes"]
    assert root.voiced() == []


def letterbox(base):
    path = base / "letterbox.png"
    done = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x100:d=1", "-frames:v", "1", str(path)]
    )
    assert done.returncode == 0
    return path.read_bytes()


def test_a_planted_lexical_error_gets_a_rewrite_round_then_passes(root, capsys, tmp_path, monkeypatch):
    b = root.w["bundle"]
    release = spoken.release_string(root.w["lexical"])
    path_with(monkeypatch, stub_cli(tmp_path, version=release, findings_when="delve"))
    set_script(b, "It did so across", "It did delve across")
    root.bind(capsys)
    assert root.gate("claims", capsys)[0] == 0
    assert root.gate("intake", capsys)[0] == 0
    root.stages(capsys, "script")

    code, _, refused = root.gate("lexical", capsys)
    assert (code, refused) == (1, "lexical_error")
    assert root.voiced() == []
    report = root.findings(capsys)
    assert report["codes"]["lexical_error"] == 1 and report["blocking"] == 1
    assert "delve" not in json.dumps(report)
    row = next(r for r in report["findings"] if r["code"] == "lexical_error")
    assert row["stage"] == "script" and row["detail"]["rule"] == "XL-FIX-001" and row["segment"]

    first = root.round(capsys, report, tmp_path)
    assert first["round"] == 1 and "voice" in first["reach"]

    # The rewrite reaches the job through the bundle: a new script, a new job.json and a new script stage.
    set_script(b, "It did delve across", "It did so across")
    assert root.gate("claims", capsys)[0] == 0
    assert root.gate("intake", capsys)[0] == 0
    assert root.gate("lexical", capsys)[2] == "lexical_unread", "the old script stage says nothing of the new job"
    root.stages(capsys, "script")
    code, shown, _ = root.gate("lexical", capsys)
    assert code == 0 and shown["entry"] == "lexical"
    assert root.findings(capsys)["codes"].get("lexical_error") is None
    assert root.voiced() == []


def test_a_stored_error_finding_refuses_too_and_a_warning_does_not(root, capsys, tmp_path, monkeypatch):
    release = spoken.release_string(root.w["lexical"])
    path_with(monkeypatch, stub_cli(tmp_path, version=release))
    assert root.gate("intake", capsys)[0] == 0
    rule = {"id": "XL-STORED", "registers": ["slides"], "kind": {"type": "Pattern", "with": {"patterns": ["fixture"]}}}
    monkeypatch.setattr(lexical.Release, "rules", lambda self: [rule | {"severity": "Error"}])
    root.stages(capsys, "script")
    assert root.gate("lexical", capsys)[2] == "lexical_error"
    assert root.findings(capsys)["codes"]["lexical_error"] >= 1


def test_a_persons_run_stays_advisory_on_the_same_error(root, capsys, monkeypatch):
    """R-N12: the stage records it, plan and run go on, and no tool is needed."""
    assert root.gate("intake", capsys)[0] == 0
    rule = {"id": "XL-STORED", "registers": ["slides"], "kind": {"type": "Pattern", "with": {"patterns": ["fixture"]}}}
    monkeypatch.setattr(lexical.Release, "rules", lambda self: [rule | {"severity": "Error"}])
    root.stages(capsys, "script")
    node = next(n for n in root.store.current()["stages"] if n.startswith("script/"))
    stored = json.loads((root.store.dir / root.store.current()["stages"][node]["dir"] / "lexical.json").read_text())
    assert stored["advisory"] is True and stored["rule"] == "R-N12" and stored["findings"]["findings"]
    report = root.findings(capsys)
    assert report["ok"] is True and report["blocking"] == 0 and report["codes"]["lexical_finding"] >= 1


# An absent tool ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stub", "code"),
    [
        (None, "lexical_tool_absent"),
        ({"no_check": True}, "lexical_tool_absent"),
        ({"version": "xoxd-lexical@9.9.9"}, "lexical_tool_absent"),
        ({"check_exit": 2, "stderr": "vale not found on PATH"}, "lexical_tool_absent"),
        ({"check_exit": 2, "stderr": "an unknown register"}, "lexical_tool_fault"),
        ({"check_exit": 7}, "lexical_tool_fault"),
        ({"check_exit": 1}, "lexical_tool_fault"),
        ({"exit_one": '{"findings": []}'}, "lexical_tool_fault"),
        ({"exit_one": '{"findings": [{"id": "XL-FIX-001", "severity": "warn", "line": 1}]}'}, "lexical_tool_fault"),
    ],
)
def test_a_tool_that_cannot_run_refuses_and_records_no_pass(root, capsys, tmp_path, monkeypatch, stub, code):
    assert root.gate("intake", capsys)[0] == 0
    root.stages(capsys, "script")
    if stub is not None:
        release = spoken.release_string(root.w["lexical"])
        path_with(monkeypatch, stub_cli(tmp_path, **({"version": release} | stub)))
    else:
        monkeypatch.setattr(lexical.shutil, "which", lambda name: None)
    exit_code, shown, refused = root.gate("lexical", capsys)
    assert (exit_code, refused) == (1, code) and shown is None
    assert not (root.store.dir / render_stage.LEXICAL_GATE_FILE).exists()


def test_each_register_of_a_job_gets_its_own_check(root, capsys, tmp_path, monkeypatch):
    """A job's segments may pin different registers. One tool for them all would read each under the first's."""
    path_with(monkeypatch, stub_cli(tmp_path, version=spoken.release_string(root.w["lexical"])))
    assert root.gate("intake", capsys)[0] == 0
    root.stages(capsys, "script")
    assert len(root.store.read_job()["segments"]) >= 2
    registers, seen, release = iter(["slides", "narration"]), [], lexical.Release

    class TwoRegisters(release):
        def __init__(self, directory, pin):
            super().__init__(directory, pin)
            self.register = next(registers, "narration")

    class Tool:
        def __init__(self, held):
            self.register = held.register

        def run(self, text):
            seen.append(self.register)
            return [{"rule": "XL-FIX-001", "line": 1}] if self.register == "narration" else []

    monkeypatch.setattr(lexical, "Release", TwoRegisters)
    monkeypatch.setattr(lexical, "CheckTool", Tool)
    assert root.gate("lexical", capsys)[2] == "lexical_error"
    assert seen[:2] == ["slides", "narration"]


def recipe(tmp_path, gate):
    script = tmp_path / "input.md"
    script.write_text("A synthetic line.\n")
    env = {k: v for k, v in os.environ.items() if k not in ("NARRATE_LEXICAL_DIR", "NARRATE_LEXICAL_GATE")}
    env |= {"NARRATE_LEXICAL_DIR": str(ROOT / "narrate" / "tests" / "fixtures" / "lexical")}
    env |= {"NARRATE_LEXICAL_GATE": "refuse"} if gate else {}
    argv = ["just", "--justfile", str(ROOT / "justfile"), "--working-directory", str(ROOT)]
    return subprocess.run([*argv, "narrate-lexical-check", str(script)], env=env, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not on PATH")
@pytest.mark.skipif(shutil.which("xoxd-lexical") is not None, reason="this reads the recipe with no CLI on PATH")
def test_the_recipe_refuses_an_absent_tool_in_a_dag_and_stays_advisory_for_a_person(tmp_path):
    advisory = recipe(tmp_path, gate=False)
    assert advisory.returncode == 0 and "not checked (advisory)" in advisory.stderr
    refused = recipe(tmp_path, gate=True)
    assert refused.returncode != 0
    assert '{"ok": false, "refused": "lexical_tool_absent"}' in refused.stderr


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not on PATH")
def test_the_recipe_hands_a_gate_a_markdown_file_and_keeps_stdin_for_a_person(tmp_path, monkeypatch):
    fixture_dir = ROOT / "narrate" / "tests" / "fixtures" / "lexical"
    release = spoken.release_string(fixture_dir)
    path_with(monkeypatch, stub_cli(tmp_path, version=release, findings_when="synthetic"))
    assert recipe(tmp_path, gate=False).returncode == 0
    assert recipe(tmp_path, gate=True).returncode == 1


# The value comparison ---------------------------------------------------------------------------------------------


def claim(number, unit="ms", **source):
    return {"id": "c", "value": {"spoken": "x", "number": Decimal(str(number)), "unit": unit}, "receipt": "r"} | (
        {"source": source} if source else {}
    )


def compared(claimed, measured, unit=None, require=False, **source):
    """The mention's fields after compare_values, reading a stub source."""
    row = {"segment": "s", "status": "passed", "codes": []}
    row["mentions"] = [{"text": "t", "status": "matched", "claim": "c", "receipt": "r"}]
    held = {"c": claim(claimed, **({"path": "p"} | source)) if (source or not require) else claim(claimed)}

    def read(_):
        if isinstance(measured, str):
            raise ValueError(measured)
        return Decimal(str(measured)), unit

    claims.compare_values([row], held, read, require)
    return row, row["mentions"][0]


@pytest.mark.parametrize(
    ("claimed", "measured", "source", "ok"),
    [
        (17.877, 17.877, {}, True),
        (17.877, 17.878, {}, False),
        (17.9, 17.877, {}, False),
        (17.9, 17.877, {"places": Decimal(1)}, True),
        (17.8, 17.877, {"places": Decimal(1)}, False),
        (17.88, 17.875, {"places": Decimal(2)}, True),
        (17.87, 17.875, {"places": Decimal(2)}, True),
        (17.877, 17.877, {"places": Decimal(1)}, False),  # says more places than it rounded to
        (42, 0.42, {"scale": Decimal(100)}, True),
        (42, 0.43, {"scale": Decimal(100)}, False),
        (18, 17.6, {"places": Decimal(0)}, True),
    ],
)
def test_a_claim_compares_its_number(claimed, measured, source, ok):
    row, mention = compared(claimed, measured, **source)
    assert (mention["status"] == "matched") is ok
    assert mention.get("value") == ("compared" if ok else None)
    assert row["codes"] == ([] if ok else ["claim_value_mismatch"])


def test_a_unit_the_source_names_must_be_the_claims():
    assert compared(17.877, 17.877, unit="ms")[1]["status"] == "matched"
    _, mention = compared(17.877, 17.877, unit="s")
    assert (mention["code"], mention["reason"]) == ("claim_value_unread", "unit_mismatch")


def test_a_claim_with_no_source_passes_a_person_and_refuses_a_dag():
    row = {"segment": "s", "status": "passed", "codes": [], "mentions": []}
    row["mentions"] = [{"text": "t", "status": "matched", "claim": "c", "receipt": "r"}]
    claims.compare_values([row], {"c": claim(1)}, lambda _: pytest.fail("no source to read"))
    assert row["status"] == "passed" and row["mentions"][0]["status"] == "matched"
    claims.compare_values([row], {"c": claim(1)}, lambda _: pytest.fail("no source to read"), require=True)
    assert row["mentions"][0]["code"] == "claim_value_unread" and row["mentions"][0]["reason"] == "no_source"
    assert row["status"] == "refused" and claims.typed_rows([row])[0]["detail"]["reason"] == "no_source"


@pytest.mark.parametrize(
    ("edit", "reason"),
    [
        (lambda s: s.update(sha256="0" * 64), "source_digest_mismatch"),
        (lambda s: s.update(path="absent.json"), "source_unreadable"),
        (lambda s: s.update(pointer="/build/absent"), "pointer_missing"),
        (lambda s: s.update(pointer="/files/9"), "pointer_missing"),
        (lambda s: s.update(pointer="/build"), "source_not_a_number"),
        (lambda s: s.update(pointer="/build/unit"), "source_not_a_number"),
        (lambda s: s.update(unit_pointer="/absent"), "pointer_missing"),
        (lambda s: s.update(unit_pointer="/build/ms"), "source_unit_unread"),
        (lambda s: s.update(unit_pointer="/build/unit", pointer="/cache/rate"), "unit_mismatch"),
    ],
)
def test_a_source_it_cannot_read_refuses(ws, edit, reason):  # noqa: F811
    source_all(ws["bundle"])

    def plant(rows):
        edit(rows[1]["source"])
        rows[0]["source"]["unit_pointer"] = "/build/unit"
        rows[2]["source"].pop("unit_pointer", None)

    set_claims(ws["bundle"], plant)
    result = bundle.claims_only(ws["bundle"], require_values=True)
    assert result["ok"] is False
    rows = [row["detail"]["reason"] for row in result["findings"]["findings"]]
    assert rows == [reason]


@pytest.mark.parametrize(
    ("value", "source"),
    [
        ('{"n": 1e9999999}', {}),
        ('{"n": 1e999999}', {"scale": 1e300}),
    ],
)
def test_a_number_outside_the_decimal_range_refuses_and_stops_no_gate(ws, value, source):  # noqa: F811
    b = ws["bundle"]
    source_all(b)
    (b / "huge.json").write_text(value)
    digest = sha(value.encode())
    set_claims(b, lambda rows: rows[0].update(source={"path": "huge.json", "sha256": digest, "pointer": "/n"} | source))
    result = bundle.claims_only(b, require_values=True)
    assert [row["detail"]["reason"] for row in result["findings"]["findings"]] == ["source_out_of_range"]


def test_a_pointer_with_a_digit_only_unicode_reads_digits_as_missing(ws):  # noqa: F811
    with pytest.raises(ValueError, match="pointer_missing"):
        bundle.pointed([1, 2, 3], "/\u00b2")


def test_a_source_in_a_symlink_refuses(ws, tmp_path):  # noqa: F811
    b = ws["bundle"]
    source_all(b)
    target = tmp_path / "outside.json"
    shutil.move(b / "proof.json", target)
    (b / "proof.json").symlink_to(target)
    reasons = {row["detail"]["reason"] for row in bundle.claims_only(b)["findings"]["findings"]}
    assert reasons == {"source_unreadable"}


@pytest.mark.parametrize(
    "source",
    [
        {"path": "../p.json", "sha256": "0" * 64, "pointer": "/a"},
        {"path": "/p.json", "sha256": "0" * 64, "pointer": "/a"},
        {"path": "p.json", "sha256": "x", "pointer": "/a"},
        {"path": "p.json", "sha256": "0" * 64, "pointer": "a"},
        {"path": "p.json", "sha256": "0" * 64, "pointer": "/a", "places": 1.5},
        {"path": "p.json", "sha256": "0" * 64, "pointer": "/a", "places": -1},
        {"path": "p.json", "sha256": "0" * 64, "pointer": "/a", "places": False},
        {"path": "p.json", "sha256": "0" * 64, "pointer": "/a", "places": 29},
        {"path": "p.json", "sha256": "0" * 64, "pointer": "/a", "places": 1e30},
        {"path": "p.json", "sha256": "0" * 64, "pointer": "/a", "scale": 0},
        {"path": "p.json", "sha256": "0" * 64, "pointer": "/a", "unit_pointer": "u"},
    ],
)
def test_a_source_of_another_shape_is_an_invalid_claim(ws, source):  # noqa: F811
    set_claims(ws["bundle"], lambda rows: rows[0].update(source=source))
    with pytest.raises(bundle.BundleError) as caught:
        bundle.claims_only(ws["bundle"])
    assert caught.value.code == "claim_invalid"


def test_an_unknown_source_key_refuses(ws):  # noqa: F811
    source = {"path": "p.json", "sha256": "0" * 64, "pointer": "/a", "tolerance": 1}
    set_claims(ws["bundle"], lambda rows: rows[0].update(source=source))
    with pytest.raises(bundle.BundleError) as caught:
        bundle.claims_only(ws["bundle"])
    assert caught.value.code == "bundle_invalid"


def test_a_source_on_a_persons_claims_run_compares_too(ws):  # noqa: F811
    source_all(ws["bundle"], PROOF | {"files": [401]})
    result = bundle.claims_only(ws["bundle"])
    assert result["findings"]["codes"] == {"claim_value_mismatch": 1}


def test_the_guard_reads_a_source_path_and_pointer_as_record_texts(ws):  # noqa: F811
    source_all(ws["bundle"])
    read_claims = bundle.read_claims(ws["bundle"])[0]
    texts = private_terms.record_texts({}, [], read_claims)
    assert ("claim#1", "record", "proof.json") in texts and ("claim#1", "record", "/build/ms") in texts


# Which jobs these gates read --------------------------------------------------------------------------------------


def test_a_job_with_no_knobs_file_has_no_bundle(ws, tmp_path, capsys):  # noqa: F811
    r = Root(ws, tmp_path, knobs=False)
    assert r.gate("claims", capsys)[1] == {"ok": True, "job_id": JOB, "entry": "none"}
    assert r.gate("intake", capsys)[1]["entry"] == "none"
    assert not r.store.dir.exists()


def test_a_bound_root_with_no_knobs_or_no_bundles_setting_refuses(ws, tmp_path, capsys, monkeypatch):  # noqa: F811
    r = Root(ws, tmp_path, knobs=False)
    r.bind(capsys)
    assert r.gate("claims", capsys)[2] == "entry_missing"
    assert r.gate("intake", capsys)[2] == "entry_missing"
    r.knobs()
    r.common = r.common[:-2]  # --bundles
    monkeypatch.delenv(entry.BUNDLES_ENV, raising=False)
    assert r.gate("claims", capsys)[2] == "entry_missing"


def test_a_knobs_file_that_is_not_a_file_refuses_rather_than_reads_as_none(ws, tmp_path, capsys):  # noqa: F811
    r = Root(ws, tmp_path, knobs=False)
    path = r.bundles / f"{JOB}.entry.json"
    target = tmp_path / "knobs-elsewhere.json"
    r.knobs()
    shutil.move(path, target)
    path.symlink_to(target)
    assert r.gate("claims", capsys)[2] == "entry_invalid"
    path.unlink()
    path.mkdir()
    assert r.gate("intake", capsys)[2] == "entry_invalid"


def test_a_slide_fix_through_the_bundle_keeps_every_voice_key(root, capsys, tmp_path):
    """A planted bad slide after the voice ran: the fix re-enters at intake, and no voice key moves."""
    assert root.gate("claims", capsys)[0] == 0
    assert root.gate("intake", capsys)[0] == 0
    root.stages(capsys, "script", "voice")
    held = {k: v["key"] for k, v in root.store.current()["stages"].items() if k.split("/")[0] in ("script", "voice")}
    assert any(k.startswith("voice/") for k in held)

    b = root.w["bundle"]
    fixed = letterbox(tmp_path)
    (b / "assets" / "slide-a.png").write_bytes(fixed)
    m = manifest(b)
    m["assets"][0] |= {"sha256": sha(fixed), "size": {"w": 320, "h": 100}}
    set_manifest(b, m)
    assert root.gate("claims", capsys)[0] == 0
    assert root.gate("intake", capsys)[0] == 0
    plan = root.stages(capsys, "script", "voice")
    assert plan["ran"] == []
    now = {k: v["key"] for k, v in root.store.current()["stages"].items() if k in held}
    assert now == held


def test_a_private_term_leaves_no_text_in_the_report_and_stays_a_stop(ws, tmp_path, capsys):  # noqa: F811
    r = Root(ws, tmp_path)
    term = "Quillfeather Labs"
    deny = tmp_path / "private" / "denylist.json"
    deny.parent.mkdir()
    entries = [{"id": "name-a", "class": "name", "literal": term}]
    salt = "3a9f0c71e6b28d45" * 2
    deny.write_text(json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": salt, "entries": entries}))
    m = manifest(ws["bundle"])
    m["privacy"] = {"ip_private": True, "never_name": True, "denylist_sha256": sha(deny.read_bytes())}
    set_manifest(ws["bundle"], m)
    set_script(ws["bundle"], "It did so across", f"It did so for {term} across")
    r.common += ["--denylist", str(deny)]
    assert r.gate("claims", capsys)[:1] == (1,)
    assert r.gate("claims", capsys)[2] == "private_term"
    held = r.store.entry_file.read_text()
    assert term not in held and "name-a" not in held
    report = r.findings(capsys)
    assert report["codes"] == {"private_term": 1} and term not in json.dumps(report)


def test_a_client_edition_with_a_knobs_file_refuses(root, capsys):
    assert root.gate("intake", capsys)[0] == 0
    job = root.store.read_job()
    path = root.store.job_file
    path.write_text(json.dumps(job | {"edition": "ClientNarrated"}))
    assert root.gate("claims", capsys)[2] == "entry_client_job"
    assert root.gate("intake", capsys)[2] == "entry_client_job"
    assert json.loads(path.read_text())["edition"] == "ClientNarrated", "intake never replaced it"


def test_a_binding_before_intake_is_opt_in_and_keeps_a_client_refused(ws, tmp_path, capsys):  # noqa: F811
    r = Root(ws, tmp_path)
    s = r.store
    with pytest.raises(JobError) as caught:
        rerun.bind_campaign(s, CAMPAIGN)
    assert caught.value.code == "job_missing" and not s.dir.exists()
    assert rerun.bind_campaign(s, CAMPAIGN, before_intake=True)["recorded"] is True

    # An unbound root takes no round, with or without a job.
    other = store.JobStore(r.root, "other-fixture")
    other.dir.mkdir(parents=True)
    write_refused(other)
    with pytest.raises(JobError) as caught:
        rerun.machine_round(other, render_stage.job_findings(other))
    assert caught.value.code == "round_needs_decision"


def test_a_binding_before_intake_keeps_a_client_edition_refused(root, capsys):
    assert root.gate("intake", capsys)[0] == 0
    job = root.store.read_job()
    root.store.job_file.write_text(json.dumps(job | {"edition": "ClientNarrated"}))
    with pytest.raises(JobError) as caught:
        rerun.bind_campaign(root.store, CAMPAIGN, before_intake=True)
    assert caught.value.code == "campaign_client_job"
    assert rerun.read(root.store).get("campaign") is None


def test_an_admit_refusal_at_intake_records_a_finding_and_writes_no_job(root, capsys, monkeypatch):
    plan = entry.graph.plan

    def refused(job, records, s, ctx):
        planned = plan(job, records, s, ctx)
        rows = [{"code": "consent_missing", "detail": "a synthetic refusal"}]
        return planned | {"admit": planned["admit"] | {"verdict": "Refused", "refusals": rows}}

    monkeypatch.setattr(entry.graph, "plan", refused)
    assert root.gate("intake", capsys)[2] == "consent_missing"
    assert not root.store.exists()
    assert root.findings(capsys)["codes"] == {"consent_missing": 1}


def write_refused(s):
    rows = [findings.finding("claim_value_mismatch", segment="b1", mention=0)]
    entry.record(s, "a" * 64, "claims", rows)


def test_a_round_on_a_client_edition_still_needs_its_decision_with_an_entry_report(root, capsys):
    assert root.gate("intake", capsys)[0] == 0
    job = root.store.read_job()
    assert rerun.bind_campaign(root.store, CAMPAIGN)["recorded"] is True
    root.store.job_file.write_text(json.dumps(job | {"edition": "ClientNarrated"}))
    write_refused(root.store)
    with pytest.raises(JobError) as caught:
        rerun.machine_round(root.store, render_stage.job_findings(root.store))
    assert caught.value.code == "round_needs_decision"


def test_a_report_of_another_bundle_is_stale(ws, tmp_path, capsys):  # noqa: F811
    r = Root(ws, tmp_path)
    r.bind(capsys)
    write_refused(r.store)
    report = render_stage.job_findings(r.store)
    entry.record(r.store, "b" * 64, "claims", [findings.finding("claim_value_mismatch", segment="b1", mention=0)])
    with pytest.raises(JobError) as caught:
        rerun.machine_round(r.store, report)
    assert caught.value.code == "findings_stale"


def test_the_gates_move_no_stage_key(root, capsys, tmp_path, monkeypatch):
    path_with(monkeypatch, stub_cli(tmp_path, version=spoken.release_string(root.w["lexical"])))
    assert root.gate("claims", capsys)[0] == 0
    assert root.gate("intake", capsys)[0] == 0
    root.stages(capsys, "script")
    held = {k: v["key"] for k, v in root.store.current()["stages"].items()}
    assert root.gate("preflight", capsys)[0] == 0
    assert root.gate("lexical", capsys)[0] == 0
    assert {k: v["key"] for k, v in root.store.current()["stages"].items()} == held
    assert root.gate("claims", capsys)[0] == 0
    assert root.gate("intake", capsys)[0] == 0
    assert {k: v["key"] for k, v in root.store.current()["stages"].items()} == held, "the same bundle keeps its keys"
    plan = root.stages(capsys, "script")
    assert plan["ran"] == []


def test_a_root_the_entry_gates_built_reads_its_own_records(root, capsys, monkeypatch):
    monkeypatch.setenv(cli.RECORDS_ENV, str(root.w["records"]))
    assert root.gate("intake", capsys)[0] == 0
    capsys.readouterr()
    assert cli.main(["plan", JOB, "--root", str(root.root), "--store", str(root.w["store"]), "--json"]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["admit"]["verdict"] == "Admitted", "the worker's records hold no beat's narrate job"
    assert cli.main(["subject", JOB, *root.common[:6], "--json"]) == 0


def test_a_refused_report_holds_no_text_or_path(ws, tmp_path, capsys):  # noqa: F811
    r = Root(ws, tmp_path)
    set_script(ws["bundle"], "forty two percent", "forty one percent")
    assert r.gate("claims", capsys)[2] == "number_unclaimed"
    held = r.store.entry_file.read_text()
    assert "forty" not in held and str(tmp_path) not in held and "proof.json" not in held
    assert Path(r.store.entry_file).stat().st_size < 4096


@pytest.mark.parametrize(
    "change",
    [
        {"voice": "../voice"},
        {"persona": "a/b"},
        {"tail_s": 61},
        {"tail_s": True},
        {"extra": 1},
        {"kind": "other"},
        {"schema_version": 2},
    ],
)
def test_a_knobs_file_of_another_shape_refuses(ws, tmp_path, capsys, change):  # noqa: F811
    r = Root(ws, tmp_path)
    r.knobs(**change)
    assert r.gate("claims", capsys)[2] == "entry_invalid"
