"""The public tree carries no secrets, private addresses, estate host names, personal paths or real take names.

The patterns are the site's leak-scan rules (site/scripts/leak-scan-rules.json), the same twelve that
tests/test_condense_public_surface.py applies to condense/, applied here to every tracked or to-be-committed
text file. Forward scrub and allowlist rationale: docs/agent-notes/2026-10-15-public-tree-scrub.md.

Exceptions are explicit and narrow. VALUE_ALLOWLIST exempts one exact match of one rule anywhere;
PATH_ALLOWLIST exempts one rule in one file, for detectors, positive controls and fixtures;
FROZEN_EVIDENCE exempts a hash-pinned receipt only while its bytes are unchanged. Every entry must still
be needed, so a stale exception fails too.

Bare estate host words cannot be listed in a public file without leaking them. Set
VIDEO_UTILS_PRIVATE_TERMS to an untracked file of words (one per line) to scan for them word-bounded.
"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "site" / "scripts" / "leak-scan-rules.json"
APPLIED = ("secret-pem-block", "secret-ssh-key", "secret-cloud-access-key", "secret-forge-token",
           "secret-json-web-token", "secret-assignment", "internal-hostname", "private-network-address",
           "developer-filesystem-path", "nix-store-path", "private-estate-hostname", "real-take-filename")

PINNED_STORE_PATH = "/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin"
VALUE_ALLOWLIST = {
    # The loopback bind is a tested security property of the web stack and names no host.
    ("private-network-address", "127.0.0.1"),
    # The repository's own Kubernetes Service name in its deploy manifest; generic, no estate host.
    ("internal-hostname", "video-utils-web.video-utils.svc.cluster.local"),
    # The hash-pinned FFmpeg output used by code and receipts; the public binary cache serves it (narinfo
    # checked 2026-10-15). Exempt only as this whole store path, never as a prefix of another name.
    ("nix-store-path", PINNED_STORE_PATH),
}

# Frozen evidence: executable code pins these receipts by sha256 (or opens them through an absolute path they
# record), so scrubbing them would break a reproducible gate. Exempt from every rule only while the bytes are
# exactly these; any edit fails the test. Re-pinning them is an operator decision (scrub receipt).
FROZEN_EVIDENCE = {
    "docs/agent-notes/2026-10-05-captured-restoration-comparison.json":
        "16a333af8d6068aabb4215cf183fa2d18b6726d38affcbe439c29d55cf004e0f",
    "docs/agent-notes/2026-10-06-accepted-fuller-compact-assembly.py":
        "095fa1e694fb97cc9a53f1d12e04c86cac7fbd637a7d574c6295102ecd44a533",
    "docs/agent-notes/2026-10-06-actual-nr-pair-artifact-audit.py":
        "aaec5344a7929c240efc6f1277817b22c9d2ad4a604e5f7d77eb5aef856313b0",
    "docs/agent-notes/2026-10-06-actual-nr10-resource-artifact-audit.py":
        "7139058e83748d42d088036053ceb1ce181f3f057f0e8d66df991bce884196ac",
    "docs/agent-notes/2026-10-06-actual-nr8-independent-artifact-audit.json":
        "dc79c3af65bcc5f893af9cf6b61293baeff3429a9f3fa5cfc56fb242efab5d59",
    "docs/agent-notes/2026-10-06-actual-nr8-nr10-capture-authoring.json":
        "98108ca07705bfed300dfc8a5b6a40de72215f7cb838d05e87bca8aaa8206a8b",
    "docs/agent-notes/2026-10-06-capture-application-native-qualification-preregistration.json":
        "0eca36a73660f797c18d122bbad6d29cfa0b9815c291557d5329089e0c70320c",
    "docs/agent-notes/2026-10-06-capture-application-resource-qualification-preregistration.json":
        "f6bec7567bc3e676d13f39c1f3f79671e307d4f75483ff1204a67bb33891d5c0",
    "docs/agent-notes/2026-10-06-capture-application-resource-qualification-result.json":
        "3ad6a3c119c4e3196604f8818630ec74960028cb1df33e3f3e7c0e3abcb09603",
    "docs/agent-notes/2026-10-06-fuller-v1-plan.json":
        "f62cce0d5bf9e83ba045bfb9bd22a20d341ccc8ff690413fbfcd85bc447be599",
    "docs/agent-notes/2026-10-06-root-actual-nr10-resource-retry-release.json":
        "24ba4717093779c7afbb7d8ade6cba493353ed6d93a0b447f48f3336023392f9",
    "docs/agent-notes/2026-10-06-root-actual-nr8-nr10-render-release.json":
        "7d47ca235de555cb3f721c8b6f041e1517e71c5a1d2e87356affc9f47586c531",
    "docs/agent-notes/2026-10-06-root-capture-application-native-release.json":
        "56e49d0789fa84e8a0d75f03d222f4bda291995a519810c63d8f297d94e98b3c",
    "docs/agent-notes/2026-10-06-root-capture-application-resource-release.json":
        "65662826f918c156b450f219ae8a60ed47256e3257d0a21d74919a0d606b07bc",
    "docs/agent-notes/2026-10-06-root-low-register-diagnostic-release.json":
        "26bb0a5cc3a1d72e95471830f72ceeb706e5aed21c3474dc48c838e0e2a8225b",
}

DETECTOR = "a leak detector's own pattern or sentinel"
CONTROL = "a positive control or host-path-shaped fixture the code must refuse or redact"
TEAM = "synthetic Access team-domain fixtures for the auth gate"
GATEWAY = "the guitar_noul gateway host contract the client enforces"
RELATIVE_ROOT = "a relative temporary checkout directory named root, not the superuser home"
PATH_ALLOWLIST = {
    ("docs/agent-notes/sprints/20261007-s3/take_intake-e2e-prereg.json", "developer-filesystem-path"): RELATIVE_ROOT,
    ("docs/agent-notes/sprints/20261007-s3/workflow-handoffs/take_intake.json",
     "developer-filesystem-path"): RELATIVE_ROOT,
    ("docs/spec/sprints/TAKE_INTAKE_S3.md", "developer-filesystem-path"): RELATIVE_ROOT,
    ("native/au-spike/packaging/tests.py", "developer-filesystem-path"): CONTROL,
    ("native/au-spike/packaging/tests.py", "nix-store-path"): CONTROL,
    ("scripts/guitar_noul_client.py", "private-estate-hostname"): GATEWAY,
    ("scripts/web_runs_api.py", "nix-store-path"): DETECTOR,
    ("tests/test_artifact_ids.py", "developer-filesystem-path"): CONTROL,
    ("tests/test_auth_hosting_s3.py", "nix-store-path"): DETECTOR,
    ("tests/test_auth_hosting_s3.py", "private-estate-hostname"): TEAM,
    ("tests/test_auth_token_s3.py", "private-estate-hostname"): TEAM,
    ("tests/test_editor_marker_export.py", "developer-filesystem-path"): CONTROL,
    ("tests/test_guitar_noul_client.py", "internal-hostname"): GATEWAY,
    ("tests/test_guitar_noul_client.py", "private-estate-hostname"): GATEWAY,
    ("tests/test_report.py", "developer-filesystem-path"): CONTROL,
    ("tests/test_report_bundle.py", "developer-filesystem-path"): CONTROL,
    ("tests/test_review_server.py", "developer-filesystem-path"): CONTROL,
    ("tests/test_s3_tool_admission.py", "private-estate-hostname"): GATEWAY,
    ("tests/test_take_intake.py", "developer-filesystem-path"): CONTROL,
    ("tests/test_web_house_stack_s3.py", "nix-store-path"): DETECTOR,
    ("tests/test_web_runs_s3.py", "developer-filesystem-path"): CONTROL,
    ("tests/test_web_runs_s3.py", "nix-store-path"): DETECTOR,
    ("tests/test_web_stack.py", "developer-filesystem-path"): CONTROL,
    ("tests/test_web_stack.py", "nix-store-path"): DETECTOR,
    ("web/src/lib/server/auth/cf-access.test.ts", "private-estate-hostname"): TEAM,
    ("web/src/lib/server/auth/gate.test.ts", "private-estate-hostname"): TEAM,
}


def compiled_rules():
    rules = {rule["id"]: rule for rule in json.loads(RULES.read_text(encoding="utf-8"))["rules"]}
    return {name: re.compile(rules[name]["pattern"], re.A | (re.I if "i" in rules[name]["flags"] else 0))
            for name in APPLIED}


def listed_files(root):
    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root,
                            capture_output=True, check=True).stdout
    return sorted({name.decode("utf-8") for name in listed.split(b"\0") if name})


def read_text(path):
    if path.is_symlink() or not path.is_file():
        return None
    raw = path.read_bytes()
    if b"\0" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def allowed_value(name, text, match):
    """Return the VALUE_ALLOWLIST key that exempts this match, or None."""
    if name == "nix-store-path":
        end = match.start() + len(PINNED_STORE_PATH)
        whole = text.startswith(PINNED_STORE_PATH, match.start()) and not re.match(r"[\w.-]", text[end:end + 1])
        return (name, PINNED_STORE_PATH) if whole else None
    return (name, match.group(0)) if (name, match.group(0)) in VALUE_ALLOWLIST else None


def scan(root, names, rules, path_allowlist=PATH_ALLOWLIST):
    """Return (findings, used allowlist keys); a finding is 'path:line:rule:match'."""
    findings, used = [], set()
    for name in names:
        text = read_text(root / name)
        if text is None:
            continue
        if root == ROOT and name in FROZEN_EVIDENCE:
            if hashlib.sha256(text.encode("utf-8")).hexdigest() == FROZEN_EVIDENCE[name]:
                used.add(name)
                continue
        for rule, pattern in rules.items():
            for match in pattern.finditer(text):
                key = allowed_value(rule, text, match)
                if key:
                    used.add(key)
                    continue
                if (name, rule) in path_allowlist:
                    used.add((name, rule))
                    continue
                findings.append(f"{name}:{text.count(chr(10), 0, match.start()) + 1}:{rule}:{match.group(0)}")
    return findings, used


def private_terms():
    source = os.environ.get("VIDEO_UTILS_PRIVATE_TERMS", "")
    if not source:
        return []
    words = [line.strip() for line in Path(source).read_text(encoding="utf-8").splitlines()]
    return [re.compile(rf"\b{re.escape(word)}\b", re.I) for word in words if word and word[0] != "#"]


class PublicTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = compiled_rules()
        cls.names = listed_files(ROOT)
        cls.findings, cls.used = scan(ROOT, cls.names, cls.rules)

    def test_whole_tree_matches_no_leak_rule(self):
        self.assertGreater(len(self.names), 500)
        self.assertEqual(self.findings, [])

    def test_every_exception_is_still_needed(self):
        used = self.used
        for name, rule in PATH_ALLOWLIST:
            self.assertIn(rule, APPLIED)
            self.assertIn(name, self.names, "allowlisted path is not tracked")
        self.assertEqual(sorted(set(PATH_ALLOWLIST) - used), [], "stale path exception")
        self.assertEqual(sorted(VALUE_ALLOWLIST - used), [], "stale value exception")
        self.assertEqual(sorted(set(FROZEN_EVIDENCE) - used), [], "frozen evidence changed or vanished")

    def test_planted_positive_controls_fail_the_scan(self):
        # Built from fragments so this file is not itself a finding.
        j = "".join
        planted = {
            "secret-pem-block": j(("-----BEGIN ", "PRIVATE KEY-----")),
            "secret-ssh-key": j(("ssh-", "ed25519 AAAA", "B" * 40)),
            "secret-cloud-access-key": j(("AK", "IA", "Z" * 16)),
            "secret-forge-token": j(("gh", "p_", "a" * 36)),
            "secret-json-web-token": j(("ey", "J", "a" * 12, ".ey", "J", "b" * 12, ".", "c" * 12)),
            "secret-assignment": j(("pass", "word", ' = "', "x" * 16, '"')),
            "internal-hostname": j(("build-host.", "tail0000.", "ts", ".net")),
            "private-network-address": j(("192.", "168.", "7.", "9")),
            "developer-filesystem-path": j(("/Us", "ers/", "someone/take")),
            "nix-store-path": j(("/nix", "/st", "ore/", "0" * 32, "-private-env")),
            "private-estate-hostname": j(("gateway.", "xoxd", ".ai")),
            "real-take-filename": j(("Mov", "ie on ", "1-2-03 at 4.56 PM")),
        }
        self.assertEqual(sorted(planted), sorted(APPLIED))
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "planted.md").write_text("\n".join(planted.values()) + "\n", encoding="utf-8")
            (root / "binary.bin").write_bytes(b"\0" + "\n".join(planted.values()).encode())
            names = listed_files(root)
            self.assertEqual(names, ["binary.bin", "planted.md"])
            findings, _ = scan(root, names, self.rules)
            self.assertEqual(sorted({finding.split(":")[2] for finding in findings}), sorted(APPLIED))
            self.assertTrue(all(finding.startswith("planted.md:") for finding in findings))
            # A path exception for one rule does not hide the others in that file.
            findings, _ = scan(root, names, self.rules, {("planted.md", "nix-store-path"): "control"})
            self.assertEqual(len({finding.split(":")[2] for finding in findings}), len(APPLIED) - 1)
            # The pinned store path is exempt only as itself, not as a prefix of another name.
            (root / "planted.md").write_text(f"{PINNED_STORE_PATH}/bin/ffmpeg\n{PINNED_STORE_PATH}-x\n",
                                             encoding="utf-8")
            findings, _ = scan(root, names, self.rules)
            self.assertEqual([finding.split(":", 2)[:2] for finding in findings], [["planted.md", "2"]])

    def test_untracked_private_terms(self):
        patterns = private_terms()
        if not patterns:
            self.skipTest("VIDEO_UTILS_PRIVATE_TERMS is unset")
        hits = [f"{name}:{pattern.pattern}" for name in self.names
                for text in [read_text(ROOT / name)] if text is not None
                for pattern in patterns if pattern.search(text)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
