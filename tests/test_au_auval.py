"""S2 au_auval: read-only AU discovery/auval step receipts, parser and guards.

Frozen protocol: docs/spec/sprints/AU_AUVAL_S2.md. Real host commands are
never executed here; the step receives an injected fake runner and `which`.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "native/au-spike/host"
FIXTURES = ROOT / "native/au-spike/tests/fixtures/auval"


def _load_step():
    spec = importlib.util.spec_from_file_location("au_auval_step", HOST / "auval_step.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


step = _load_step()
BUNDLE = "org.video-utils.gain.prototype.audio-unit"
NOW = datetime(2026, 10, 6, 14, 0, 0, tzinfo=timezone.utc)
PLUGINKIT = ["/usr/bin/pluginkit", "-m", "-A", "-D", "-v", "-i", BUNDLE]
AUVAL_LIST = ["/usr/bin/auval", "-a"]
AUVAL_VALIDATE = ["/usr/bin/auval", "-v", "aufx", "vuGn", "Jess"]
SW_VERS = "ProductName:\t\tmacOS\nProductVersion:\t\t26.0\nBuildVersion:\t\t25A000\n"
LISTING_NONE = "aufx bpas appl  -  Apple: AUBandpass\n"
LISTING_ONE = LISTING_NONE + "aufx vuGn Jess  -  video-utils: Guitar Gain Prototype\n"


def result(stdout="", exit_code=0, timed_out=False, stderr=""):
    return step.CommandResult(None if timed_out else exit_code, stdout, stderr, timed_out, 0.01)


class FakeHost:
    """Scripted host. `responses` maps a key to a CommandResult."""

    def __init__(self, pluginkit="(no matches)\n", listing=LISTING_NONE, **overrides):
        self.calls = []
        self.responses = {"sw_vers": result(SW_VERS), "uname": result("arm64\n"),
                          "pluginkit": result(pluginkit), "auval_list": result(listing),
                          "typecheck": result(), "auval_validate": result((FIXTURES / "pass.txt").read_text()),
                          "compile": result(),
                          "render": result(json.dumps({"status": "passed", "observed_instantiation_mode": "out_of_process",
                                                       "fixtures": {"total": 60, "passed": 60}}))}
        self.responses.update(overrides)

    @staticmethod
    def key(argv):
        if argv[0] == "/usr/bin/sw_vers":
            return "sw_vers"
        if argv[0] == "/usr/bin/uname":
            return "uname"
        if argv[0] == "/usr/bin/pluginkit":
            return "pluginkit"
        if argv == AUVAL_LIST:
            return "auval_list"
        if argv[:2] == ["/usr/bin/auval", "-v"]:
            return "auval_validate"
        if argv[:3] == ["/usr/bin/xcrun", "swiftc", "-typecheck"]:
            return "typecheck"
        if argv[:3] == ["/usr/bin/xcrun", "swiftc", "-O"]:
            return "compile"
        if argv[0].endswith("registered-render"):
            return "render"
        raise AssertionError(f"unexpected command {argv}")

    def __call__(self, argv, timeout):
        self.calls.append((list(argv), timeout))
        return self.responses[self.key(argv)]

    def argvs(self):
        return [argv for argv, _ in self.calls]


def which_all(name):
    return step.TOOL_PATHS.get(name)


class StepCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.out = self.base / "out"

    def run_step(self, host, which=which_all, packaging=None, system_name="Darwin"):
        receipt, code, paths = step.run_step(self.out, packaging or (self.base / "missing.json"),
                                             runner=host, which=which, system_name=system_name, now=NOW)
        self.assertTrue(all(Path(path).resolve().is_relative_to(self.out.resolve()) for path in paths))
        written = json.loads((self.out / "receipt.json").read_text())
        self.assertEqual(written, json.loads(json.dumps(receipt, allow_nan=False)))
        return receipt, code

    def fake_appex(self, content=b"fake extension executable"):
        appex = self.base / "Installed/VideoUtilsGain.appex"
        binary = appex / "Contents/MacOS/VideoUtilsGain"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(content)
        return appex, hashlib.sha256(content).hexdigest()

    def packaging_receipt(self, sha256):
        path = self.base / "packaging-receipt.json"
        path.write_text(json.dumps({"binaries": {"extension": {"sha256": sha256}}}))
        return path

    def registered_host(self, appex, **overrides):
        line = f"+    {BUNDLE}(0.1.0)\tUUID-0000\t2026-10-06 13:00:00 +0000\t{appex}\n"
        return FakeHost(pluginkit=line, listing=LISTING_ONE, **overrides)


class ReceiptSchema(StepCase):
    REQUIRED = {"schema", "created_at", "host", "tool_paths", "authority", "source_sha256", "target",
                "stage_0_local_checks", "stage_1_installation", "installation", "stage_2_discovery",
                "discovery", "swift_typecheck", "stage_3_registered_render", "observed_instantiation_mode",
                "stage_4_parameters_state", "stage_5_auval", "logic_host_acceptance", "realtime_deadline",
                "bypass", "state_recall", "listening", "audio_device_opened", "mutations", "commands", "status"}

    def test_required_fields_and_enums(self):
        receipt, code = self.run_step(FakeHost())
        self.assertEqual(code, 0)
        self.assertLessEqual(self.REQUIRED, set(receipt))
        self.assertEqual(receipt["schema"], "vu.au_auval_step.v1")
        self.assertEqual(receipt["authority"],
                         "R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13; S2 20261006-s2 TIN-5612")
        self.assertEqual(receipt["host"], {"os_version": "26.0 (25A000)", "architecture": "arm64"})
        self.assertEqual(set(receipt["tool_paths"]), {"sw_vers", "uname", "pluginkit", "auval", "xcrun"})
        self.assertTrue(all(path.startswith("/usr/bin/") for path in receipt["tool_paths"].values()))
        self.assertEqual(set(receipt["source_sha256"]), {"native/au-spike/host/auval_step.py",
                                                         "native/au-spike/host/RegisteredRender.swift",
                                                         "native/au-spike/packaging/targets.json"})
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", value) for value in receipt["source_sha256"].values()))
        self.assertEqual(receipt["target"], {"bundle_id": BUNDLE, "component":
                                             {"type": "aufx", "subtype": "vuGn", "manufacturer": "Jess"}})
        self.assertIn(receipt["stage_0_local_checks"], ("see au-spike-check receipt", "unknown"))
        self.assertIn(receipt["stage_2_discovery"], step.DISCOVERY_VALUES)
        self.assertIn(receipt["status"], step.STATUS_VALUES)
        self.assertIn(receipt["stage_5_auval"]["status"], step.STAGE5_VALUES)
        self.assertIn(receipt["swift_typecheck"]["status"], step.TYPECHECK_VALUES)
        self.assertEqual(set(receipt["swift_typecheck"]), {"status", "reason", "seconds"})
        explicit = {"stage_1_installation": "out_of_scope", "installation": "out_of_scope",
                    "stage_4_parameters_state": "not_performed", "logic_host_acceptance": "not_performed",
                    "realtime_deadline": "unknown", "bypass": "not_performed", "state_recall": "not_performed",
                    "listening": "not_performed", "observed_instantiation_mode": "unknown",
                    "packaging_artifact_freshness": "stale_unknown", "audio_device_opened": False}
        for field, value in explicit.items():
            with self.subTest(field=field):
                self.assertEqual(receipt[field], value)
        self.assertEqual(receipt["mutations"], {"files_copied": [], "registry_writes": [],
                                                "writes_outside_out_dir": []})
        for command in receipt["commands"]:
            self.assertEqual(set(command), {"argv", "timeout_s", "exit_code", "timed_out", "seconds"})
            self.assertGreater(command["timeout_s"], 0)
        for query in ("pluginkit", "auval_list"):
            summary = receipt["discovery"][query]
            self.assertTrue({"exit_code", "timed_out", "matching_lines", "stdout_sha256", "stdout_line_count"}
                            <= set(summary))
        # allow_nan=False round trip of the written file.
        text = (self.out / "receipt.json").read_text()
        self.assertEqual(json.loads(text), json.loads(json.dumps(json.loads(text), allow_nan=False)))
        stamped = self.out / "auval-step-20261006T140000Z.json"
        self.assertEqual(stamped.read_text(), text)

    def test_unsupported_platform_exit_2(self):
        host = FakeHost()
        receipt, code = self.run_step(host, system_name="Linux")
        self.assertEqual((code, receipt["status"]), (2, "unsupported"))
        self.assertEqual(host.calls, [])


class BlockedPath(StepCase):
    def test_not_installed_runs_only_readonly_queries(self):
        host = FakeHost()
        receipt, code = self.run_step(host)
        self.assertEqual(code, 0)
        self.assertEqual(receipt["stage_2_discovery"], "blocked_not_installed")
        self.assertEqual(receipt["status"], "blocked_not_installed")
        self.assertEqual(host.argvs(), [
            ["/usr/bin/sw_vers"], ["/usr/bin/uname", "-m"], PLUGINKIT, AUVAL_LIST,
            ["/usr/bin/xcrun", "swiftc", "-typecheck", "-swift-version", "6", "-module-cache-path",
             str(self.out.resolve() / "swift-module-cache"), "native/au-spike/host/RegisteredRender.swift"]])
        self.assertEqual([timeout for _, timeout in host.calls], [10, 10, 30, 60, 180])
        self.assertNotIn(AUVAL_VALIDATE, host.argvs())
        self.assertEqual(receipt["stage_3_registered_render"],
                         {"status": "not_performed", "blocked_by": "stage_2_discovery"})
        self.assertEqual(receipt["stage_5_auval"]["status"], "not_performed")
        self.assertEqual(receipt["stage_5_auval"]["blocked_by"], "stage_2_discovery")
        self.assertEqual(receipt["next_required_decision"],
                         "operator-approved stage-1 installation (AU_HOST_ACCEPTANCE_LANE.md); "
                         "not requested by this lane")
        self.assertEqual(receipt["mutations"], {"files_copied": [], "registry_writes": [],
                                                "writes_outside_out_dir": []})
        self.assertEqual(receipt["swift_typecheck"]["status"], "passed")
        written = sorted(str(path.relative_to(self.out)) for path in self.out.rglob("*") if path.is_file())
        self.assertEqual(written, ["auval-step-20261006T140000Z.json", "raw/20261006T140000Z-auval-list.txt",
                                   "raw/20261006T140000Z-pluginkit.txt", "receipt.json"])

    def test_ambiguous_partial(self):
        for pluginkit, listing in ((f"+ {BUNDLE}(0.1.0)\t/x/VideoUtilsGain.appex\n", LISTING_NONE),
                                   ("(no matches)\n", LISTING_ONE)):
            with self.subTest(pluginkit=pluginkit, listing=listing):
                host = FakeHost(pluginkit=pluginkit, listing=listing)
                receipt, _ = self.run_step(host)
                self.assertEqual(receipt["stage_2_discovery"], "ambiguous_partial")
                self.assertEqual(receipt["status"], "discovery_ambiguous")
                self.assertNotIn(AUVAL_VALIDATE, host.argvs())
                self.assertEqual(receipt["stage_3_registered_render"]["status"], "not_performed")

    def test_ambiguous_duplicates(self):
        two = f"+ {BUNDLE}(0.1.0)\t/a/VideoUtilsGain.appex\n  {BUNDLE}(0.1.0)\t/b/VideoUtilsGain.appex\n"
        for pluginkit, listing in ((two, LISTING_ONE), ("(no matches)\n", LISTING_ONE + LISTING_ONE)):
            with self.subTest(pluginkit=pluginkit, listing=listing):
                host = FakeHost(pluginkit=pluginkit, listing=listing)
                receipt, _ = self.run_step(host)
                self.assertEqual(receipt["stage_2_discovery"], "ambiguous_duplicates")
                self.assertEqual(receipt["status"], "discovery_ambiguous")
                self.assertFalse(any(argv[:2] == ["/usr/bin/auval", "-v"] for argv in host.argvs()))
                self.assertFalse(any(argv[0].endswith("registered-render") for argv in host.argvs()))

    def test_pluginkit_timeout_is_error_not_retry(self):
        host = FakeHost(pluginkit=None)
        host.responses["pluginkit"] = result(timed_out=True, stderr="")
        receipt, code = self.run_step(host)
        self.assertEqual(code, 0)
        self.assertEqual(receipt["stage_2_discovery"], "error")
        self.assertEqual(receipt["status"], "discovery_error")
        self.assertEqual(host.argvs().count(PLUGINKIT), 1)
        self.assertNotIn(AUVAL_VALIDATE, host.argvs())
        self.assertEqual(receipt["discovery"]["error"]["command"], "pluginkit")
        self.assertTrue(receipt["discovery"]["error"]["timed_out"])

    def test_nonzero_listing_exit_is_error(self):
        host = FakeHost(auval_list=result(LISTING_ONE, exit_code=1, stderr="boom"))
        receipt, _ = self.run_step(host)
        self.assertEqual(receipt["stage_2_discovery"], "error")
        self.assertEqual(receipt["discovery"]["error"]["exit_code"], 1)


class RegisteredPath(StepCase):
    def test_passed_runs_auval_once_with_timeout(self):
        appex, digest = self.fake_appex()
        host = self.registered_host(appex)
        receipt, code = self.run_step(host, packaging=self.packaging_receipt(digest))
        self.assertEqual(code, 0)
        self.assertEqual(receipt["stage_2_discovery"], "passed")
        validations = [(argv, timeout) for argv, timeout in host.calls if argv[:2] == ["/usr/bin/auval", "-v"]]
        self.assertEqual(validations, [(AUVAL_VALIDATE, 120)])
        stage5 = receipt["stage_5_auval"]
        self.assertEqual(stage5["status"], "passed")
        self.assertEqual(stage5["artifact_binding"], "matched")
        self.assertEqual(stage5["artifact_sha256"], digest)
        self.assertEqual(stage5["parsed"]["overall"], "passed")
        self.assertEqual(stage5["parsed"]["pass_count"], 6)
        self.assertEqual(receipt["stage_3_registered_render"]["status"], "passed")
        self.assertEqual(receipt["observed_instantiation_mode"], "out_of_process")
        self.assertEqual(receipt["status"], "validated")
        render_calls = [timeout for argv, timeout in host.calls if argv[0].endswith("registered-render")]
        self.assertEqual(render_calls, [180])
        self.assertEqual(receipt["mutations"]["files_copied"], [])
        self.assertEqual(receipt["mutations"]["writes_outside_out_dir"], [])

    def test_auval_timeout_recorded(self):
        appex, digest = self.fake_appex()
        host = self.registered_host(appex, auval_validate=result("partial\n", timed_out=True))
        receipt, _ = self.run_step(host, packaging=self.packaging_receipt(digest))
        self.assertEqual(receipt["stage_5_auval"]["status"], "timeout")
        self.assertTrue(receipt["stage_5_auval"]["timed_out"])
        self.assertEqual(sum(argv == AUVAL_VALIDATE for argv in host.argvs()), 1)
        self.assertEqual(receipt["status"], "validation_failed")

    def test_artifact_mismatch_caps_status(self):
        appex, _ = self.fake_appex()
        host = self.registered_host(appex)
        receipt, _ = self.run_step(host, packaging=self.packaging_receipt("0" * 64))
        stage5 = receipt["stage_5_auval"]
        self.assertEqual(stage5["artifact_binding"], "mismatch")
        self.assertEqual(stage5["status"], "failed_artifact_mismatch")
        self.assertEqual(stage5["parsed"]["overall"], "passed")  # transcript kept, status capped
        self.assertTrue((self.out / stage5["raw_transcript_path"]).is_file())
        self.assertEqual(receipt["status"], "validation_failed")

    def test_binding_unknowns(self):
        appex, _ = self.fake_appex()
        receipt, _ = self.run_step(self.registered_host(appex))
        self.assertEqual(receipt["stage_5_auval"]["artifact_binding"], "unknown_no_packaging_receipt")
        self.assertEqual(receipt["status"], "validation_failed")
        host = FakeHost(pluginkit=f"+ {BUNDLE}(0.1.0)\tUUID\n", listing=LISTING_ONE)
        receipt, _ = self.run_step(host)
        self.assertEqual(receipt["stage_5_auval"]["artifact_binding"], "unknown_path_not_reported")


class Parser(unittest.TestCase):
    def parse(self, name):
        text = (FIXTURES / f"{name}.txt").read_text()
        parsed = step.parse_auval_transcript(text)
        self.assertEqual(parsed.pop("transcript_sha256"), hashlib.sha256(text.encode()).hexdigest())
        return parsed

    @staticmethod
    def sections(spec):
        return [{"title": title, "result": outcome, "warnings": warnings, "line_span": span}
                for title, outcome, warnings, span in spec]

    VALIDATING = "VALIDATING AUDIO UNIT: 'aufx' - 'vuGn' - 'Jess'"

    def test_fixture_pass(self):
        self.assertEqual(self.parse("pass"), {
            "overall": "passed", "section_count": 6, "pass_count": 6, "fail_count": 0,
            "no_verdict_count": 0, "fatal_message": None,
            "sections": self.sections([(self.VALIDATING, "pass", 0, [6, 12]),
                                       ("TESTING OPEN TIMES:", "pass", 0, [14, 20]),
                                       ("VERIFYING DEFAULT SCOPE FORMATS:", "pass", 0, [22, 27]),
                                       ("VERIFYING REQUIRED PROPERTIES:", "pass", 0, [29, 35]),
                                       ("VERIFYING PARAMETERS:", "pass", 0, [37, 42]),
                                       ("RENDER TESTS:", "pass", 0, [44, 48])])})

    def test_fixture_fail_param(self):
        self.assertEqual(self.parse("fail_param"), {
            "overall": "failed", "section_count": 6, "pass_count": 5, "fail_count": 1,
            "no_verdict_count": 0, "fatal_message": None,
            "sections": self.sections([(self.VALIDATING, "pass", 0, [6, 12]),
                                       ("TESTING OPEN TIMES:", "pass", 0, [14, 20]),
                                       ("VERIFYING DEFAULT SCOPE FORMATS:", "pass", 0, [22, 27]),
                                       ("VERIFYING REQUIRED PROPERTIES:", "pass", 0, [29, 35]),
                                       ("VERIFYING PARAMETERS:", "fail", 0, [37, 44]),
                                       ("RENDER TESTS:", "pass", 0, [46, 50])])})

    def test_fixture_fatal_not_found(self):
        self.assertEqual(self.parse("fatal_not_found"), {
            "overall": "fatal", "section_count": 1, "pass_count": 0, "fail_count": 1,
            "no_verdict_count": 0, "fatal_message": "FATAL ERROR: didn't find the component",
            "sections": self.sections([(self.VALIDATING, "fail", 0, [6, 8])])})

    def test_fixture_warn_no_verdict(self):
        self.assertEqual(self.parse("warn_no_verdict"), {
            "overall": "unknown", "section_count": 1, "pass_count": 0, "fail_count": 0,
            "no_verdict_count": 1, "fatal_message": None,
            "sections": self.sections([(self.VALIDATING, "no_verdict", 2, [6, 11])])})

    def test_fixture_listing(self):
        self.assertEqual(step.parse_auval_listing((FIXTURES / "listing.txt").read_text()), {
            "target_lines": ["aufx vuGn Jess  -  video-utils: Guitar Gain Prototype"],
            "target_count": 1, "total_rows": 7})

    def test_listing_matches_only_exact_triple(self):
        for near in ("aufx vuGn Jesz  -  x", "aumf vuGn Jess  -  x", "# aufx vuGn Jess  -  x",
                     "aufx vuGn JessX -  x", "aufx vugn Jess  -  x", "xaufx vuGn Jess  -  x"):
            with self.subTest(near=near):
                self.assertEqual(step.parse_auval_listing(near + "\n")["target_count"], 0)
        self.assertEqual(step.parse_auval_listing("  aufx vuGn Jess  -  ok\n")["target_count"], 1)

    def test_pluginkit_match_is_exact(self):
        text = (f"+    {BUNDLE}(0.1.0)\tU\t2026\t/A/VideoUtilsGain.appex\n"
                f"     {BUNDLE}.other(0.1.0)\tU\t2026\t/B/Other.appex\n"
                f"     x{BUNDLE}(0.1.0)\n(no matches)\n")
        parsed = step.parse_pluginkit(text, BUNDLE)
        self.assertEqual(parsed["match_count"], 1)
        self.assertEqual(parsed["paths"], ["/A/VideoUtilsGain.appex"])

    def test_unknown_is_never_upgraded(self):
        parsed = step.parse_auval_transcript("random output\nno verdict here\n")
        self.assertEqual((parsed["overall"], parsed["pass_count"]), ("unknown", 0))


class Guard(StepCase):
    FORBIDDEN = [r"\bditto\b", r"\bcp\s", r"/Applications", r"Library/", r"pluginkit\",\s*\"-a\"",
                 r"\"-e\"", r"\"-r\"", r"lsregister", r"killall", r"\bsudo\b", r"\brm\s", r"open -n",
                 r"--deep", r"\bcodesign\b"]

    def test_no_install_or_mutation_tokens(self):
        hits = []
        for name in ("auval_step.py", "RegisteredRender.swift"):
            text = (HOST / name).read_text()
            hits += [(name, pattern) for pattern in self.FORBIDDEN if re.search(pattern, text)]
        self.assertEqual(hits, [])
        argv = step.pluginkit_argv(BUNDLE)
        self.assertEqual(argv, PLUGINKIT)
        self.assertFalse({"-a", "-e", "-r"} & set(argv))

    def test_swiftc_missing_skips_with_reason(self):
        host = FakeHost()
        receipt, _ = self.run_step(host, which=lambda name: None if name == "xcrun" else which_all(name))
        typecheck = receipt["swift_typecheck"]
        self.assertEqual(typecheck["status"], "skipped")
        self.assertTrue(typecheck["reason"])
        self.assertFalse(any(argv[0] == "/usr/bin/xcrun" for argv in host.argvs()))
        unresolved = FakeHost(typecheck=result(exit_code=72, stderr="xcrun: error: unable to find utility \"swiftc\""))
        receipt, _ = self.run_step(unresolved)
        self.assertEqual(receipt["swift_typecheck"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
