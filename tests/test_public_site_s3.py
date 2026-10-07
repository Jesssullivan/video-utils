"""S3 public_site lane tests (docs/spec/sprints/PUBLIC_SITE_S3.md section 8).

Stdlib only. Static checks always run. The Node scanner checks need `node`; the build checks
need `node`, `pnpm` and an already installed `site/node_modules` (this module never runs
`pnpm install` and never uses the network). Both skip with a stated reason otherwise. Every
subprocess has an explicit timeout. Nothing is written outside a temp directory and the
generated `site/.svelte-kit` and `site/build` trees.

The rule application is re-implemented here in Python from `site/scripts/leak-scan-rules.json`
so the source scan runs without Node; the Node scanner and this port must agree on every
fixture verdict. Fixture strings are assembled from fragments at run time so that this module
contains no literal that trips a rule. Nothing here is derived from a real recording: the
exact-identifier check reads the identifiers from repository files at test time.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
SRC = SITE / "src"
BUILD = SITE / "build"
VENDOR = SITE / "vendor"
RULES_PATH = SITE / "scripts" / "leak-scan-rules.json"
SCANNER = SITE / "scripts" / "leak-scan.mjs"
SPEC = REPO / "docs" / "spec" / "sprints" / "PUBLIC_SITE_S3.md"
RECEIPT_DIR = REPO / "docs" / "agent-notes" / "sprints" / "20261007-s3"
TOOLS_JSON = REPO / "program" / "tools.json"

NODE_TIMEOUT_S = 60
CHECK_TIMEOUT_S = 300
BUILD_TIMEOUT_S = 300
GIT_TIMEOUT_S = 30
PNPM_GATE_UNAVAILABLE_EXIT = 75  # EX_TEMPFAIL from this host's pnpm storage gate

EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
VENDOR_SPEC = re.compile(r"^file:vendor/[a-z0-9][a-z0-9-]*$")
EXPECTED_RULE_IDS = (
    "secret-pem-block", "secret-ssh-key", "secret-cloud-access-key", "secret-forge-token",
    "secret-json-web-token", "secret-assignment", "kubeconfig-fragment", "internal-hostname",
    "private-network-address", "cache-or-executor-endpoint", "localhost-reference",
    "source-map-or-dev-artifact", "developer-filesystem-path", "internal-tracker-reference",
    "operator-banned-dash", "real-take-filename", "media-file-reference", "content-hash-64",
    "run-identifier", "artifact-path-reference", "nix-store-path", "analytics-or-beacon",
    "form-or-upload-surface", "private-estate-hostname",
)
VENDOR_CARRIER_RULE_IDS = frozenset((
    "secret-pem-block", "secret-ssh-key", "secret-cloud-access-key", "secret-forge-token",
    "secret-json-web-token", "secret-assignment", "developer-filesystem-path", "nix-store-path",
    "real-take-filename",
))
SRC_ONLY_RULE_IDS = frozenset(("operator-banned-dash", "form-or-upload-surface"))
CLAIM_CLASSES = frozenset((
    "implemented", "measured_synthetic", "inferred", "product_hypothesis", "unverified_listening",
    "not_done", "unknown",
))
MEASURED_CLASSES = frozenset(("implemented", "measured_synthetic"))
# Spec section 5.3: id -> pages on which it must render as a data-unknown element.
REQUIRED_UNKNOWNS = {
    "real_take_accuracy": ("home", "status"),
    "low_register_pitch_accuracy": ("features", "status"),
    "note_correctness_verdicts": ("home", "status"),
    "listening_acceptance": ("features", "status"),
    "stem_identity": ("features",),
    "bpm_meter_phrase_nullable": ("features",),
    "logic_au_host_acceptance": ("status",),
    "editor_import_proof": ("status",),
    "market_hypothesis": ("home", "status"),
    "hosted_availability": ("status",),
}
PAGES = {"home": "index.html", "features": "features.html", "agents": "agents.html", "status": "status.html"}
PAGE_ROUTES = {"home": "/", "features": "/features", "agents": "/agents", "status": "/status"}
EXPECTED_HTML = ("index.html", "features.html", "agents.html", "status.html", "404.html")
BANNED_PHRASES = (
    r"studio[- ]quality", r"recovered (original )?stem", r"original stem", r"best[- ]in[- ]class",
    r"the only tool", r"no other (tool|product)", r"100%", r"guarantee", r"flawless",
    r"perfect(ly)? accurate",
)
COLOUR_LITERAL = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b(?:rgba?|hsla?|oklch|oklab)\("
)
FORBIDDEN_TAGS = ("form", "textarea", "audio", "video", "iframe", "object", "embed", "img", "picture", "source")
FORBIDDEN_TOOL_KEYS = (
    "inputSchema", "additionalProperties", "agent_workflow", "evidence_kind", "implementation_status",
    "recommended_prior_tools", "instrument_context", "lowest_intentional_fundamental_hz",
    "readOnlyHint", "destructiveHint", "max_comparison_candidates_default",
)
# Spec section 10: field -> allowed values (None in a tuple means JSON null).
RECEIPT_FIELDS = {
    "deployed": (False,),
    "pages_project_name": (None,),
    "cloudflare_account": (None,),
    "public_hostname": (None,),
    "custom_domain": (None,),
    "wrangler_version": (None,),
    "served_check": ("not_performed",),
    "public_product_name": (None,),
    "private_app_hostname_checked": (False, True),
    "real_take_accuracy": ("unknown",),
    "low_register_pitch_accuracy": ("unknown",),
    "listening_acceptance": ("not_claimed",),
    "logic_au_host_acceptance": ("not_done",),
    "editor_import_proof": ("not_done",),
    "market_claim": ("hypothesis",),
    "xoxd_chrome_consumed": (True, False),
    "xoxd_theme_consumed": (True, False),
    "archives_anonymously_fetchable": (True, False, "unknown"),
    "contrast_ratio_measured": (False,),
    "keyboard_walkthrough": ("not_performed",),
    "reduced_motion_verified": (False,),
    "csp_enforced": (False,),
    "bazel_graph": ("absent",),
    "template_archive_verified": (False, True),
    "effect_in_site": ("absent", "4.0.1"),
    "media_shown": (0,),
}
RECEIPTS_WITH_FIELDS = ("public_site-build.json", "public_site-leak-scan.json", "public_site-handoff.json")

GENERATED_PREFIXES = ("node_modules/", ".svelte-kit/", "build/")
SOURCE_EXCLUDED_PREFIXES = ("node_modules/", ".svelte-kit/", "build/", "vendor/", "static/fonts/")
SOURCE_EXCLUDED_FILES = ("pnpm-lock.yaml",)
BUILD_TEXT_EXT = frozenset((".html", ".js", ".mjs", ".css", ".json", ".svg", ".txt", ".md", ".xml", ""))
BUILD_OPAQUE_EXT = frozenset((".woff", ".woff2", ".ico"))
BUILD_REFUSED_EXT = frozenset("." + e for e in (
    "map pdf mov mp4 m4v webm mkv avi wav flac aiff aif aac mp3 ogg opus m4a png jpg jpeg gif webp "
    "avif bmp tiff zip tar gz tgz br bz2 xz 7z").split())
CHUNK_RE = re.compile(r"(?:^|/)_app/immutable/chunks/")
URL_RE = re.compile(r"\bhttps?://([a-z0-9.-]+)", re.I | re.A)
MAILBOX_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I | re.A)
FORGE_HOST = ".".join(("github", "com"))
FORGE_URL_RE = re.compile(r"https://" + re.escape(FORGE_HOST) + r"/[^\s\"'`<>)\]]+", re.I | re.A)
FORGE_RULE_ID = "internal-tracker-reference"


# --------------------------------------------------------------------------------------------
# Python port of site/scripts/leak-scan.mjs
# --------------------------------------------------------------------------------------------

def load_rules(path: Path = RULES_PATH) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    rules = []
    for rule in document["rules"]:
        flags = re.A  # JavaScript \b, \d and \w are ASCII; match that here
        if "i" in rule["flags"]:
            flags |= re.I
        rules.append({**rule, "regexp": re.compile(rule["pattern"], flags)})
    return {
        "document": document,
        "rules": rules,
        "allowed_hosts": {h.lower() for h in document.get("allowedHosts", [])},
        "allowed_forge_urls": {u.rstrip("/") for u in document.get("allowedPublicForgeUrls", [])},
        "allowed_mailboxes": {m.lower() for m in document.get("allowedMailboxes", [])},
    }


def rule_applies(rule: dict, surface: str, rel: str) -> bool:
    if surface == "vendor":
        return rule.get("vendorCarrier") is True
    if surface == "source":
        return rule.get("sourceScope") != "src" or rel.startswith("src/")
    return not (rule.get("skipVendorRuntimeChunks") is True and CHUNK_RE.search(rel))


def _allowed_forge_match(text: str, index: int, allowed: set[str]) -> bool:
    for match in FORGE_URL_RE.finditer(text):
        if match.start() <= index < match.end():
            return match.group(0).rstrip("/") in allowed
    return False


def scan_text(rel: str, text: str, ruleset: dict, surface: str = "build") -> list[dict]:
    findings = []
    for rule in ruleset["rules"]:
        if not rule_applies(rule, surface, rel):
            continue
        for match in rule["regexp"].finditer(text):
            if (rule["id"] == FORGE_RULE_ID and match.group(0).lower() == FORGE_HOST
                    and _allowed_forge_match(text, match.start(), ruleset["allowed_forge_urls"])):
                continue
            findings.append({"ruleId": rule["id"], "file": rel, "line": text.count("\n", 0, match.start()) + 1})
    if surface != "vendor":
        for match in URL_RE.finditer(text):
            host = match.group(1).lower().rstrip(".")
            if host in ruleset["allowed_hosts"]:
                continue
            if host == FORGE_HOST and _allowed_forge_match(text, match.start(), ruleset["allowed_forge_urls"]):
                continue
            findings.append({"ruleId": "unreviewed-outbound-host", "file": rel,
                             "line": text.count("\n", 0, match.start()) + 1, "host": host})
        for match in MAILBOX_RE.finditer(text):
            if match.group(0).lower() in ruleset["allowed_mailboxes"]:
                continue
            findings.append({"ruleId": "unreviewed-mailbox", "file": rel,
                             "line": text.count("\n", 0, match.start()) + 1})
    return findings


def _walk(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _decode(data: bytes) -> str | None:
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan_directory(root: Path, ruleset: dict, surface: str = "build") -> dict:
    scanned, unscannable, findings = [], [], []
    for rel in _walk(root):
        if surface == "source":
            if rel.startswith(SOURCE_EXCLUDED_PREFIXES) or rel in SOURCE_EXCLUDED_FILES:
                continue
        ext = Path(rel).suffix.lower()
        if surface == "build":
            if ext in BUILD_REFUSED_EXT:
                findings.append({"ruleId": "refused-file-type", "file": rel, "line": 0})
                continue
            if ext in BUILD_OPAQUE_EXT:
                unscannable.append(rel)
                continue
            if ext not in BUILD_TEXT_EXT:
                findings.append({"ruleId": "unclassified-file-type", "file": rel, "line": 0})
                continue
        text = _decode((root / rel).read_bytes())
        if text is None:
            if surface == "build":
                findings.append({"ruleId": "undecodable-text-file", "file": rel, "line": 0})
            else:
                unscannable.append(rel)
            continue
        scanned.append(rel)
        findings.extend(scan_text(rel, text, ruleset, surface))
    applied = [r["id"] for r in ruleset["rules"] if surface != "vendor" or r.get("vendorCarrier") is True]
    return {"files_scanned": scanned, "files_unscannable": unscannable, "findings": findings,
            "rules_applied": applied}


# --------------------------------------------------------------------------------------------
# Synthetic fixtures (assembled from fragments; invented names, zero-filled digests)
# --------------------------------------------------------------------------------------------

def rule_fixtures() -> dict[str, tuple[str, str]]:
    """rule id -> (positive text, negative control text)."""
    j = "".join
    return {
        "secret-pem-block": (j(("-----BEG", "IN PRIVATE ", "KEY-----")), "-----BEGIN PGP SIGNATURE-----"),
        "secret-ssh-key": (j(("ssh-", "ed25519 ", "AAAA", "B" * 40)), "an ssh-ed25519 key type is named here"),
        "secret-cloud-access-key": (j(("AK", "IA", "A" * 16)), j(("AK", "I short"))),
        "secret-forge-token": (j(("gh", "p_", "a" * 36)), j(("gh", "p_ prefix only"))),
        "secret-json-web-token": (j(("ey", "J", "a" * 12, ".", "ey", "J", "b" * 12, ".", "c" * 12)), "eyJ only"),
        "secret-assignment": (j(("pass", "word", ' = "', "x" * 16, '"')), "a password field is described"),
        "kubeconfig-fragment": (j(("client-key", "-data")), "client key material in prose"),
        "internal-hostname": (j(("db.example", ".inter", "nal")), "an internal note"),
        "private-network-address": (j(("10", ".0.0", ".7")), "203.0.113.9"),
        "cache-or-executor-endpoint": (j(("grp", "cs:", "//cache.example")), "the executor role in prose"),
        "localhost-reference": (j(("loc", "alhost", ":5173")), "the local host of the party"),
        "source-map-or-dev-artifact": (j(("//# sourceMapp", "ingURL=app.js.m", "ap")), "source mapping in prose"),
        "developer-filesystem-path": (j(("/Us", "ers/", "example/project")), "users of the tool"),
        "internal-tracker-reference": (j(("TI", "N-", "1234")), "TINY-house"),
        "operator-banned-dash": ("a — b", "a - b"),
        "real-take-filename": (j(("Mov", "ie on ", "1-2-34 at 5.06 PM")), "Movie night on Friday"),
        "media-file-reference": (j(("clip", ".m", "p4")), "an mp4 container in prose"),
        "content-hash-64": ("0" * 64, "0" * 63),
        "run-identifier": (j(("20000101T000000Z", "-", "0" * 12)), "20000101T000000Z"),
        "artifact-path-reference": (j(("art", "ifacts", "/runs/x")), "the artifacts of history"),
        "nix-store-path": (j(("/n", "ix/st", "ore/", "0" * 8, "-pkg")), "the nix package manager"),
        "analytics-or-beacon": (j(("www.google", "tagmanager", ".example")), "tag management in prose"),
        "form-or-upload-surface": (j(("<fo", "rm act", 'ion="/x">')), "a form of words"),
        "private-estate-hostname": (j(("example-team.cloudflare", "access", ".com")), "access control at the edge"),
    }


def fixture_verdicts_python(ruleset: dict) -> dict[tuple[str, str], bool]:
    """(rule id, 'pos'|'neg') -> whether the rule fired on that fixture, via the Python port."""
    verdicts = {}
    for rule_id, (positive, negative) in rule_fixtures().items():
        for kind, text in (("pos", positive), ("neg", negative)):
            fired = {f["ruleId"] for f in scan_text(f"{kind}/{rule_id}.txt", text + "\n", ruleset, "build")}
            verdicts[(rule_id, kind)] = rule_id in fired
    return verdicts


def run_node_scanner(directory: Path, surface: str = "build", report: Path | None = None,
                     rules: Path | None = None) -> subprocess.CompletedProcess:
    command = ["node", str(SCANNER), str(directory), "--surface", surface]
    if report is not None:
        command += ["--report", str(report)]
    if rules is not None:
        command += ["--rules", str(rules)]
    return subprocess.run(command, capture_output=True, text=True, timeout=NODE_TIMEOUT_S, check=False)


def fixture_verdicts_node() -> dict[tuple[str, str], bool]:
    with tempfile.TemporaryDirectory(prefix="public-site-fixtures-") as tmp:
        root = Path(tmp) / "tree"
        for rule_id, (positive, negative) in rule_fixtures().items():
            for kind, text in (("pos", positive), ("neg", negative)):
                target = root / kind / f"{rule_id}.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text + "\n", encoding="utf-8")
        report = Path(tmp) / "report.json"
        result = run_node_scanner(root, "build", report)
        if result.returncode != 1:
            raise AssertionError(f"scanner exit {result.returncode} on fixtures: {result.stderr[-400:]}")
        fired = {(f["file"], f["ruleId"]) for f in json.loads(report.read_text())["findings"]}
    return {(rule_id, kind): (f"{kind}/{rule_id}.txt", rule_id) in fired
            for rule_id in rule_fixtures() for kind in ("pos", "neg")}


# --------------------------------------------------------------------------------------------
# Site file helpers and static metrics
# --------------------------------------------------------------------------------------------

def site_files(include_generated: bool = False) -> list[Path]:
    files = []
    for path in sorted(SITE.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(SITE).as_posix()
        if not include_generated and rel.startswith(GENERATED_PREFIXES):
            continue
        files.append(path)
    return files


def authored_src_files() -> list[Path]:
    return [p for p in sorted(SRC.rglob("*")) if p.is_file()]


def package_json() -> dict:
    return json.loads((SITE / "package.json").read_text(encoding="utf-8"))


def pin_metrics() -> dict:
    package = package_json()
    specs = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    exact = {name: spec for name, spec in specs.items() if EXACT_VERSION.match(spec) or VENDOR_SPEC.match(spec)}
    lock = (SITE / "pnpm-lock.yaml").read_text(encoding="utf-8")
    skeleton_versions = sorted(set(re.findall(r"@skeletonlabs/[a-z-]+@(\d+\.\d+\.\d+)", lock)))
    effect_versions = sorted(set(re.findall(r"(?m)^\s+'?effect@(\d+\.\d+\.\d+)", lock)))
    return {
        "specifiers_total": len(specs),
        "specifiers_exact": len(exact),
        "inexact": sorted(set(specs) - set(exact)),
        "skeleton_package_pins": {n: specs.get(n) for n in ("@skeletonlabs/skeleton", "@skeletonlabs/skeleton-svelte")},
        "skeleton_lock_versions": skeleton_versions,
        "effect_package_pin": specs.get("effect"),
        "effect_lock_versions": effect_versions,
        "effect_in_site": specs.get("effect", "absent") if not effect_versions else ",".join(effect_versions),
    }


def parse_claims() -> list[dict]:
    """Reads the claims registry as text (format contract stated in claims.ts)."""
    text = (SRC / "lib" / "content" / "claims.ts").read_text(encoding="utf-8")
    body = text[text.index("export const CLAIMS"):]
    pattern = re.compile(
        r'\{\s*id: "([a-z0-9_]+)",\s*claim_class: "([a-z_]+)",\s*unknown: (true|false),\s*'
        r'pages: \[([^\]]*)\],\s*section: "([a-z_]+)",\s*text: "([^"]*)"\s*\}'
    )
    claims = [
        {"id": m[1], "claim_class": m[2], "unknown": m[3] == "true",
         "pages": tuple(re.findall(r'"([a-z]+)"', m[4])), "section": m[5], "text": m[6]}
        for m in pattern.finditer(body)
    ]
    declared = len(re.findall(r"(?m)^\t\tid: \"", body))
    if declared != len(claims):
        raise AssertionError(f"claims.ts: {declared} entries declared, {len(claims)} parsed")
    return claims


def source_scan(ruleset: dict) -> dict:
    return scan_directory(SITE, ruleset, "source")


def vendor_scan(ruleset: dict) -> dict:
    return scan_directory(VENDOR, ruleset, "vendor")


def main_checkout() -> Path | None:
    """The main checkout when this tree is a linked worktree; None otherwise."""
    pointer = REPO / ".git"
    if not pointer.is_file():
        return None
    match = re.match(r"gitdir: (.+?)/\.git/worktrees/", pointer.read_text(encoding="utf-8"))
    return Path(match.group(1)) if match else None


def real_take_identifiers() -> dict:
    """Exact identifiers that must never occur under site/ (read at test time, never hardcoded)."""
    identifiers: dict[str, str] = {}
    arrangement = json.loads((REPO / "program" / "demo-arrangement.json").read_text(encoding="utf-8"))
    digest = arrangement.get("source_sha256")
    if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
        identifiers[digest] = "source_sha256"
    name_rule = next(r for r in load_rules()["rules"] if r["id"] == "real-take-filename")
    prefix_re = re.compile(name_rule["pattern"], re.I | re.A)
    # macOS writes a narrow no-break space before the meridiem; accept it and a plain space.
    name_re = re.compile(name_rule["pattern"] + r"(?: at [0-9.]+[ \u00a0\u202f][AP]M)?(?:\.[a-z0-9]{3,4})?", re.I | re.A)
    for doc in (REPO / "README.md", REPO / "docs" / "spec" / "PROJECT.md"):
        if doc.is_file():
            text = doc.read_text(encoding="utf-8")
            for match in name_re.finditer(text):
                full = match.group(0)
                identifiers.setdefault(full, "recording_basename")
                identifiers.setdefault(re.sub(r"[\u00a0\u202f]", " ", full), "recording_basename")
                identifiers.setdefault(re.sub(r"\.[a-z0-9]{3,4}$", "", full), "recording_stem")
                identifiers.setdefault(prefix_re.match(full).group(0), "recording_date_prefix")
    run_dirs = 0
    roots = [REPO / "artifacts" / "runs"]
    if main_checkout() is not None:
        roots.append(main_checkout() / "artifacts" / "runs")
    for root in roots:
        if root.is_dir():
            for entry in sorted(root.iterdir()):
                if entry.is_dir():
                    identifiers[entry.name] = "run_directory"
                    run_dirs += 1
    kinds: dict[str, int] = {}
    for kind in identifiers.values():
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"identifiers": identifiers, "count": len(identifiers), "by_kind": kinds, "run_directories_found": run_dirs}


def identifier_hits(identifiers: dict[str, str], include_build: bool) -> list[tuple[str, str]]:
    needles = [(value.encode("utf-8"), kind) for value, kind in identifiers.items()]
    hits = []
    for path in site_files():
        data = path.read_bytes()
        hits += [(path.relative_to(SITE).as_posix(), kind) for needle, kind in needles if needle in data]
    if include_build and BUILD.is_dir():
        for path in sorted(BUILD.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                hits += [("build/" + path.relative_to(BUILD).as_posix(), kind)
                         for needle, kind in needles if needle in data]
    return hits


def private_app_hostnames() -> list[str]:
    values = []
    for path in sorted((REPO / "deploy" / "cloudflare").glob("*.json")):
        def visit(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in ("hostname", "public_hostname", "publicAppOrigin", "domain") and isinstance(value, str):
                        values.append(value)
                    visit(value)
            elif isinstance(node, list):
                for item in node:
                    visit(item)
        visit(json.loads(path.read_text(encoding="utf-8")))
    return sorted({v for v in values if "." in v})


def static_metrics() -> dict:
    ruleset = load_rules()
    source = source_scan(ruleset)
    vendor = vendor_scan(ruleset)
    identifiers = real_take_identifiers()
    colour_hits = [p.relative_to(SITE).as_posix() for p in authored_src_files()
                   if COLOUR_LITERAL.search(p.read_text(encoding="utf-8"))]
    python_verdicts = fixture_verdicts_python(ruleset)
    return {
        "pins": pin_metrics(),
        "rules_total": len(ruleset["rules"]),
        "python_fixture_rules_ok": sum(1 for r in EXPECTED_RULE_IDS
                                       if python_verdicts[(r, "pos")] and not python_verdicts[(r, "neg")]),
        "source_scan": {"files_scanned": len(source["files_scanned"]), "findings": len(source["findings"]),
                        "unscannable": source["files_unscannable"], "rules_applied": len(source["rules_applied"])},
        "vendor_scan": {"files_scanned": len(vendor["files_scanned"]), "findings": len(vendor["findings"]),
                        "unscannable": vendor["files_unscannable"], "rules_applied": len(vendor["rules_applied"])},
        "identifiers_checked": identifiers["count"],
        "identifiers_by_kind": identifiers["by_kind"],
        "identifier_hits_source": len(identifier_hits(identifiers["identifiers"], include_build=False)),
        "private_app_hostname_checked": bool(private_app_hostnames()),
        "authored_colour_literal_files": colour_hits,
        "claims_total": len(parse_claims()),
    }


# --------------------------------------------------------------------------------------------
# Built HTML model and build metrics
# --------------------------------------------------------------------------------------------

VOID_TAGS = frozenset(("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
                       "source", "track", "wbr"))


class Element:
    def __init__(self, tag: str, attrs: dict, parent: "Element | None"):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[Element | str] = []

    def iter(self):
        for child in self.children:
            if isinstance(child, Element):
                yield child
                yield from child.iter()

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def find_all(self, tag: str) -> list["Element"]:
        return [e for e in self.iter() if e.tag == tag]


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("#document", {}, None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        element = Element(tag, {k: (v if v is not None else "") for k, v in attrs}, self.current)
        self.current.children.append(element)
        if tag not in VOID_TAGS:
            self.current = element

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Element(tag, {k: (v if v is not None else "") for k, v in attrs}, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse_html(path: Path) -> Element:
    builder = _Builder()
    builder.feed(path.read_text(encoding="utf-8"))
    builder.close()
    return builder.root


def visible_text(document: Element) -> str:
    def collect(node: Element) -> str:
        if node.tag in ("script", "style"):
            return ""
        return "".join(c if isinstance(c, str) else collect(c) for c in node.children)
    return re.sub(r"\s+", " ", collect(document))


def accessible_name(element: Element) -> str:
    for key in ("aria-label", "title"):
        if element.attrs.get(key, "").strip():
            return element.attrs[key].strip()
    if element.attrs.get("aria-labelledby", "").strip():
        return element.attrs["aria-labelledby"].strip()
    return element.text().strip()


def accessibility_checks(document: Element, route: str) -> dict[str, bool]:
    """The eight structure checks of spec section 5.5 for one page."""
    html = document.find_all("html")
    body = document.find_all("body")[0]
    ids = {e.attrs["id"] for e in document.iter() if "id" in e.attrs}
    navs = document.find_all("nav")
    headings = [int(e.tag[1]) for e in body.iter() if re.fullmatch(r"h[1-6]", e.tag)]
    focusable = [e for e in body.iter()
                 if (e.tag == "a" and "href" in e.attrs) or e.tag in ("button", "input", "select", "textarea")
                 or "tabindex" in e.attrs]
    first = focusable[0] if focusable else None
    controls = [e for e in body.iter() if e.tag in ("a", "button")]
    current = [e for e in body.iter() if e.tag == "a" and e.attrs.get("aria-current") == "page"]
    interactive = ("a", "button", "input", "select", "textarea", "summary")
    return {
        "html_lang_en": len(html) == 1 and html[0].attrs.get("lang") == "en",
        "one_main": len(document.find_all("main")) == 1,
        "one_h1": headings.count(1) == 1 and bool(headings) and headings[0] == 1,
        "nav_named_and_current": bool(navs) and all(
            n.attrs.get("aria-label", "").strip() or n.attrs.get("aria-labelledby", "").strip() for n in navs
        ) and bool(current) and all(e.attrs.get("href") == route for e in current),
        "footer_present": len(document.find_all("footer")) >= 1,
        "heading_levels_do_not_skip": all(b - a <= 1 for a, b in zip(headings, headings[1:])),
        "skip_link_first_and_target_exists": first is not None and first.tag == "a"
        and first.attrs.get("href", "").startswith("#") and first.attrs["href"][1:] in ids,
        "controls_named_no_positive_tabindex": all(accessible_name(e) for e in controls) and not any(
            e.attrs.get("tabindex", "0").lstrip("-").isdigit() and int(e.attrs.get("tabindex", "0")) > 0
            for e in body.iter()
        ) and not any("onclick" in e.attrs for e in body.iter() if e.tag not in interactive),
    }


def build_metrics(build: Path = BUILD) -> dict:
    """M7 to M18 on a build directory. Callers decide whether the build is fresh."""
    ruleset = load_rules()
    tools = json.loads(TOOLS_JSON.read_text(encoding="utf-8"))["tools"]
    documents = {page: parse_html(build / name) for page, name in PAGES.items() if (build / name).is_file()}
    metrics: dict = {"pages_present": [n for n in EXPECTED_HTML if (build / n).is_file()],
                     "html_files": sorted(p.relative_to(build).as_posix() for p in build.rglob("*.html"))}

    scan = scan_directory(build, ruleset, "build")
    metrics["build_scan"] = {"files_scanned": len(scan["files_scanned"]), "rules_applied": len(scan["rules_applied"]),
                             "findings": len(scan["findings"]), "finding_rules": sorted({f["ruleId"] for f in scan["findings"]}),
                             "unscannable": scan["files_unscannable"]}

    agents_html = (build / "agents.html").read_text(encoding="utf-8") if (build / "agents.html").is_file() else ""
    agents_data = (build / "agents" / "__data.json")
    agents_surface = agents_html + (agents_data.read_text(encoding="utf-8") if agents_data.is_file() else "")
    rendered = set()
    if "agents" in documents:
        rendered = {e.attrs["data-tool"] for e in documents["agents"].iter() if "data-tool" in e.attrs}
    names = [t["name"] for t in tools]
    properties = set()
    for tool in tools:
        properties |= set(tool.get("inputSchema", {}).get("properties", {}))
    snake_properties = sorted(p for p in properties if "_" in p and p not in names)
    published_text = " ".join(f"{t['title']} {t['intent']}" for t in tools)
    limitations = sorted({l for t in tools for l in t.get("limitations", []) if l not in published_text})
    forbidden_hits = [k for k in FORBIDDEN_TOOL_KEYS if k in agents_surface]
    forbidden_hits += [p for p in snake_properties if re.search(r"\b" + re.escape(p) + r"\b", agents_surface)]
    forbidden_hits += [l[:40] for l in limitations if l in agents_surface]
    forbidden_hits += [s for s in (".agents/", "SKILL.md") if any(
        s in p.read_text(encoding="utf-8", errors="ignore") for p in build.rglob("*") if p.is_file()
        and p.suffix in (".html", ".js", ".json"))]
    withheld = 0
    if "agents" in documents:
        withheld = sum(1 for e in documents["agents"].iter() if "data-intent-withheld" in e.attrs)
    metrics["agents"] = {"tools_in_registry": len(names), "tools_rendered": len(rendered & set(names)),
                         "unexpected_tools": sorted(rendered - set(names)),
                         "forbidden_candidates_checked": len(FORBIDDEN_TOOL_KEYS) + len(snake_properties) + len(limitations) + 2,
                         "forbidden_hits": forbidden_hits, "intents_withheld": withheld,
                         "status_counts": {s: sum(1 for t in tools if t["implementation_status"] == s)
                                           for s in sorted({t["implementation_status"] for t in tools})}}

    placements, claim_elements, claim_classes_ok = {}, 0, 0
    for unknown_id, pages in REQUIRED_UNKNOWNS.items():
        for page in pages:
            present = page in documents and any(
                e.attrs.get("data-unknown") == unknown_id and e.text().strip() for e in documents[page].iter())
            placements[f"{unknown_id}@{page}"] = present
    for document in documents.values():
        for element in document.iter():
            if "data-claim-class" in element.attrs:
                claim_elements += 1
                claim_classes_ok += element.attrs["data-claim-class"] in CLAIM_CLASSES
    metrics["unknown_placements"] = placements
    metrics["claim_elements"] = claim_elements
    metrics["claim_elements_in_closed_set"] = claim_classes_ok

    feature_sections = {}
    if "features" in documents:
        for element in documents["features"].iter():
            if "data-feature-section" in element.attrs:
                classes = [c.attrs["data-claim-class"] for c in element.iter() if "data-claim-class" in c.attrs]
                unknowns = [c for c in element.iter() if "data-unknown" in c.attrs]
                feature_sections[element.attrs["data-feature-section"]] = {
                    "note_visible": "Measured vs unknown" in visible_text(element),
                    "measured_or_implemented": sum(1 for c in classes if c in MEASURED_CLASSES),
                    "unknown": len(unknowns)}
    metrics["feature_sections"] = feature_sections

    banned, surfaces, a11y = {}, {}, {}
    html_paths = [build / n for n in EXPECTED_HTML if (build / n).is_file()]
    for pattern in BANNED_PHRASES:
        regexp = re.compile(pattern, re.I)
        banned[pattern] = sum(len(regexp.findall(visible_text(parse_html(p)))) for p in html_paths)
    inputs, third_party, outbound = [], [], []
    tag_counts = {tag: 0 for tag in FORBIDDEN_TAGS}
    file_inputs = 0
    for path in html_paths:
        document = parse_html(path)
        for element in document.iter():
            if element.tag in tag_counts:
                tag_counts[element.tag] += 1
            if element.tag == "input":
                inputs.append({"page": path.name, "type": element.attrs.get("type", "")})
                file_inputs += element.attrs.get("type", "").lower() == "file"
            for key in ("src", "href", "action", "poster", "data", "srcset"):
                value = element.attrs.get(key, "")
                if re.match(r"(?:[a-z][a-z0-9+.-]*:)?//", value, re.I):
                    third_party.append({"page": path.name, "tag": element.tag, "attr": key})
            if element.tag == "a" and "href" in element.attrs and not element.attrs["href"].startswith(("/", "#")):
                outbound.append({"page": path.name, "href_kind": "non-root-relative"})
            if element.tag == "a" and element.attrs.get("href", "").startswith("//"):
                outbound.append({"page": path.name, "href_kind": "protocol-relative"})
    surfaces = {**tag_counts, "file_inputs": file_inputs, "third_party_origin_attributes": len(third_party),
                "authored_outbound_links": len(outbound), "inputs": inputs,
                "action_or_method_attributes": sum(
                    1 for p in html_paths for e in parse_html(p).iter() if "action" in e.attrs or "method" in e.attrs)}
    for page, document in documents.items():
        a11y[page] = accessibility_checks(document, PAGE_ROUTES[page])
    metrics["banned_phrase_hits"] = banned
    metrics["forbidden_surfaces"] = surfaces
    metrics["accessibility"] = a11y
    metrics["accessibility_passed"] = sum(sum(checks.values()) for checks in a11y.values())
    metrics["accessibility_total"] = sum(len(checks) for checks in a11y.values())
    metrics["source_maps"] = sorted(p.relative_to(build).as_posix() for p in build.rglob("*.map"))
    metrics["compressed_twins"] = sorted(p.relative_to(build).as_posix() for p in build.rglob("*")
                                         if p.suffix in (".gz", ".br"))
    identifiers = real_take_identifiers()
    metrics["identifier_hits_build"] = len([h for h in identifier_hits(identifiers["identifiers"], True)
                                            if h[0].startswith("build/")])
    return metrics


def run_pnpm(script: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(["pnpm", "run", script], cwd=SITE, capture_output=True, text=True,
                          timeout=timeout, check=False)


# --------------------------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------------------------

class SpecAndReceiptTests(unittest.TestCase):
    def test_spec_exists_and_names_the_lane(self):
        text = SPEC.read_text(encoding="utf-8")
        self.assertIn("public_site", text)
        self.assertIn("## 10. Explicit unknown fields", text)

    def test_contract_freeze_receipt_matches_frozen_spec_shape(self):
        receipt = json.loads((RECEIPT_DIR / "public_site-contract-freeze.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["lane"], "public_site")
        self.assertIs(receipt["deployed"], False)
        self.assertEqual(receipt["frozen"]["leak_rules"], len(EXPECTED_RULE_IDS))

    def test_present_receipts_carry_every_unknown_field_with_an_allowed_value(self):
        present = [RECEIPT_DIR / name for name in RECEIPTS_WITH_FIELDS if (RECEIPT_DIR / name).is_file()]
        for path in present:
            receipt = json.loads(path.read_text(encoding="utf-8"))
            for field, allowed in RECEIPT_FIELDS.items():
                with self.subTest(receipt=path.name, field=field):
                    self.assertIn(field, receipt)
                    self.assertTrue(any(receipt[field] is a or (type(receipt[field]) is type(a) and receipt[field] == a)
                                        for a in allowed), receipt[field])
            with self.subTest(receipt=path.name, field="agents_intents_withheld"):
                self.assertIsInstance(receipt.get("agents_intents_withheld"), int)
                self.assertNotIsInstance(receipt.get("agents_intents_withheld"), bool)

    def test_receipts_are_json_and_never_claim_a_deploy(self):
        for path in sorted(RECEIPT_DIR.glob("public_site-*.json")):
            with self.subTest(receipt=path.name):
                receipt = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(receipt.get("lane"), "public_site")
                self.assertIsNot(receipt.get("deployed"), True)

    def test_deploy_plan_requires_a_separate_operator_go(self):
        text = (SITE / "DEPLOY.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"separate operator go")
        self.assertRegex(text, r"(?i)plan only")
        self.assertRegex(text, r"(?i)nothing in this directory has been deployed")
        self.assertRegex(text, r"(?i)no credential belongs in this repository")
        for decision in ("Pages project name", "Cloudflare account", "Production branch", "Custom domain",
                         "Wrangler version"):
            self.assertIn(decision, text)

    def test_no_wrangler_dependency_or_config(self):
        package = package_json()
        names = set(package.get("dependencies", {})) | set(package.get("devDependencies", {}))
        self.assertNotIn("wrangler", names)
        self.assertFalse(list(SITE.glob("wrangler.*")))
        self.assertNotIn("wrangler", (SITE / "pnpm-lock.yaml").read_text(encoding="utf-8"))


class PinTests(unittest.TestCase):
    def test_m1_every_specifier_is_exact_or_a_vendor_path(self):
        metrics = pin_metrics()
        self.assertGreater(metrics["specifiers_total"], 0)
        self.assertEqual(metrics["inexact"], [])
        self.assertEqual(metrics["specifiers_exact"], metrics["specifiers_total"])

    def test_m2_skeleton_is_5_0_1_everywhere(self):
        metrics = pin_metrics()
        self.assertEqual(metrics["skeleton_package_pins"],
                         {"@skeletonlabs/skeleton": "5.0.1", "@skeletonlabs/skeleton-svelte": "5.0.1"})
        self.assertEqual(metrics["skeleton_lock_versions"], ["5.0.1"])

    def test_m3_effect_is_absent_or_exactly_4_0_1(self):
        metrics = pin_metrics()
        self.assertIn(metrics["effect_package_pin"], (None, "4.0.1"))
        self.assertTrue(set(metrics["effect_lock_versions"]) <= {"4.0.1"}, metrics["effect_lock_versions"])
        if metrics["effect_package_pin"] is None:
            self.assertEqual(metrics["effect_lock_versions"], [])

    def test_package_manager_engine_and_scripts(self):
        package = package_json()
        self.assertEqual(package["packageManager"], "pnpm@11.25.0")
        self.assertEqual(package["engines"]["node"], ">=22.13 <23")
        self.assertIs(package["private"], True)
        scripts = package["scripts"]
        self.assertEqual(scripts["check"], "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json")
        self.assertEqual(scripts["build"], "vite build")
        self.assertEqual(scripts["leak-scan"], "node scripts/leak-scan.mjs build")
        lifecycle = {"preinstall", "install", "postinstall", "prepare", "prepublish", "prepublishOnly", "prepack",
                     "postpack"}
        self.assertEqual(lifecycle & set(scripts), set())

    def test_lockfile_is_committed_and_matches_the_manifest(self):
        lock = SITE / "pnpm-lock.yaml"
        self.assertTrue(lock.is_file())
        text = lock.read_text(encoding="utf-8")
        package = package_json()
        for name, spec in {**package["dependencies"], **package["devDependencies"]}.items():
            with self.subTest(dependency=name):
                self.assertRegex(text, r"(?m)^      '?" + re.escape(name) + r"'?:\n        specifier: " + re.escape(spec) + r"$")
        if shutil.which("git") is None or not (REPO / ".git").exists():
            self.skipTest("git is not available; lockfile presence checked, tracking not checked")
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", "site/pnpm-lock.yaml"],
                                 capture_output=True, text=True, timeout=GIT_TIMEOUT_S, check=False)
        self.assertEqual(tracked.returncode, 0, "site/pnpm-lock.yaml is not tracked by git")

    def test_generated_trees_are_not_tracked(self):
        if shutil.which("git") is None or not (REPO / ".git").exists():
            self.skipTest("git is not available")
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "site"], capture_output=True, text=True,
                                 timeout=GIT_TIMEOUT_S, check=True).stdout.splitlines()
        self.assertEqual([t for t in tracked if t[len("site/"):].startswith(GENERATED_PREFIXES)], [])

    def test_m20_vendored_carriers_are_unmodified_and_integrity_matched(self):
        provenance = json.loads((VENDOR / "PROVENANCE.json").read_text(encoding="utf-8"))
        self.assertEqual(len(provenance["carriers"]), 2)
        for carrier in provenance["carriers"]:
            with self.subTest(carrier=carrier["package"]):
                self.assertIs(carrier["integrity_match"], True)
                self.assertEqual(carrier["registry_integrity"], carrier["computed_integrity"])
                self.assertIs(carrier["modified"], False)
                root = SITE / carrier["directory"]
                on_disk = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in root.rglob("*") if p.is_file()}
                self.assertEqual(on_disk, {f["path"]: f["sha256"] for f in carrier["files"]})
                self.assertEqual(carrier["file_count"], len(on_disk))
                self.assertIn("LICENSE", on_disk)
                self.assertIn("NOTICE", on_disk)
                manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
                self.assertEqual((manifest["name"], manifest["version"]), (carrier["package"], carrier["version"]))
        for font in sorted((VENDOR / "xoxd-theme" / "fonts").iterdir()):
            with self.subTest(font=font.name):
                self.assertEqual((SITE / "static" / "fonts" / font.name).read_bytes(), font.read_bytes())
        self.assertTrue((SITE / "static" / "fonts" / "OFL.txt").is_file())


class PrerenderConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = (SITE / "svelte.config.js").read_text(encoding="utf-8")
        self.route_files = [p for p in (SRC / "routes").rglob("*") if p.is_file()]

    def test_m6_prerender_configuration(self):
        checks = {
            "adapter_static": "from '@sveltejs/adapter-static'" in self.config and "adapter-node" not in self.config,
            "layout_prerender_true": re.search(r"(?m)^export const prerender = true;$",
                                               (SRC / "routes" / "+layout.ts").read_text(encoding="utf-8")) is not None,
            "no_opt_out": not any(re.search(r"\b(prerender|ssr)\s*=\s*(false|'auto'|\"auto\")", p.read_text(encoding="utf-8"))
                                  for p in authored_src_files()),
            "no_endpoints": not any(p.name.startswith("+server.") for p in self.route_files),
            "no_form_actions": not any(re.search(r"export\s+(const|let|var|function)\s+actions\b", p.read_text(encoding="utf-8"))
                                       for p in self.route_files),
        }
        self.assertEqual(sum(checks.values()), 5, checks)

    def test_adapter_and_prerender_options(self):
        for pattern in (r"pages: 'build'", r"assets: 'build'", r"fallback: '404\.html'", r"precompress: false",
                        r"strict: true", r"base: ''", r"handleHttpError: 'fail'", r"handleMissingId: 'fail'",
                        r"handleUnseenRoutes: 'fail'", r"runes: true"):
            with self.subTest(option=pattern):
                self.assertRegex(self.config, pattern)
        self.assertNotIn("process.env", self.config)
        self.assertNotIn("trailingSlash", self.config)

    def test_no_source_maps_service_worker_or_redirects(self):
        self.assertRegex((SITE / "vite.config.ts").read_text(encoding="utf-8"), r"sourcemap: false")
        self.assertFalse((SRC / "service-worker.ts").exists() or (SRC / "service-worker.js").exists())
        self.assertFalse((SITE / "static" / "_redirects").exists())

    def test_gitignore_covers_generated_trees(self):
        lines = (SITE / ".gitignore").read_text(encoding="utf-8").splitlines()
        for entry in ("node_modules/", ".svelte-kit/", "build/"):
            self.assertIn(entry, lines)

    def test_headers_file(self):
        text = (SITE / "static" / "_headers").read_text(encoding="utf-8")
        for header in ("X-Content-Type-Options: nosniff", "Referrer-Policy: no-referrer", "X-Frame-Options: DENY",
                       "Permissions-Policy:"):
            self.assertIn(header, text)
        self.assertNotIn("Content-Security-Policy", text)
        policy = next(line for line in text.splitlines() if "Permissions-Policy:" in line)
        directives = [d.strip() for d in policy.split(":", 1)[1].split(",")]
        self.assertTrue(directives and all(d.endswith("=()") for d in directives), directives)


class ContentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = parse_claims()
        cls.src_text = {p.relative_to(SITE).as_posix(): p.read_text(encoding="utf-8") for p in authored_src_files()}

    def test_route_files_exist(self):
        for rel in ("+layout.svelte", "+layout.ts", "+page.svelte", "features/+page.svelte", "agents/+page.svelte",
                    "agents/+page.server.ts", "status/+page.svelte"):
            with self.subTest(route=rel):
                self.assertTrue((SRC / "routes" / rel).is_file())
        pages = sorted(p.parent.relative_to(SRC / "routes").as_posix() for p in (SRC / "routes").rglob("+page.svelte"))
        self.assertEqual(pages, [".", "agents", "features", "status"])

    def test_claims_use_only_the_closed_class_set(self):
        self.assertGreaterEqual(len(self.claims), len(REQUIRED_UNKNOWNS))
        self.assertEqual(len({c["id"] for c in self.claims}), len(self.claims))
        for claim in self.claims:
            with self.subTest(claim=claim["id"]):
                self.assertIn(claim["claim_class"], CLAIM_CLASSES)
                self.assertTrue(claim["pages"] and set(claim["pages"]) <= set(PAGES))
                self.assertTrue(claim["text"].strip())
        declared = re.search(r"export const CLAIM_CLASSES = \[(.*?)\] as const", self.src_text["src/lib/content/claims.ts"], re.S)
        self.assertEqual(set(re.findall(r'"([a-z_]+)"', declared.group(1))), set(CLAIM_CLASSES))

    def test_every_required_unknown_is_defined_on_its_pages(self):
        by_id = {c["id"]: c for c in self.claims}
        for unknown_id, pages in REQUIRED_UNKNOWNS.items():
            with self.subTest(unknown=unknown_id):
                self.assertIn(unknown_id, by_id)
                self.assertIs(by_id[unknown_id]["unknown"], True)
                self.assertTrue(set(pages) <= set(by_id[unknown_id]["pages"]))
                self.assertNotIn(by_id[unknown_id]["claim_class"], MEASURED_CLASSES)

    def test_each_feature_section_has_measured_and_unknown_claims(self):
        for section in ("restoration", "review", "agent_tools"):
            claims = [c for c in self.claims if "features" in c["pages"] and c["section"] == section]
            with self.subTest(section=section):
                self.assertTrue(any(c["claim_class"] in MEASURED_CLASSES for c in claims))
                self.assertTrue(any(c["unknown"] for c in claims))
        self.assertIn("Measured vs unknown", self.src_text["src/routes/features/+page.svelte"])

    def test_authored_copy_numerals_are_only_the_instrument_context(self):
        registry = self.src_text["src/lib/content/claims.ts"]
        strings = re.findall(r'(?:text|title|tagline|footer_note|footer_line): ?\n?\s*"([^"]*)"', registry)
        self.assertGreater(len(strings), len(self.claims))
        for text in strings:
            with self.subTest(text=text[:40]):
                self.assertEqual(set(re.findall(r"\d+", text)) - {"32"}, set())
                if "32" in text:
                    self.assertRegex(text, r"(near|roughly|approximately) 32 Hz")
        for rel, text in self.src_text.items():
            if rel.endswith(".svelte"):
                prose = re.sub(r"<script.*?</script>|<[^>]+>|\{[^}]*\}", " ", text, flags=re.S)
                with self.subTest(file=rel):
                    self.assertEqual(re.findall(r"\d+", prose), [])

    def test_no_tuning_artist_or_recording_context_is_published(self):
        context = json.loads((REPO / "program" / "capture-context.json").read_text(encoding="utf-8"))
        words: set[str] = set()

        def visit(node):
            if isinstance(node, str):
                words.update(re.findall(r"[A-Z][a-zł]+(?: [A-Z][a-zł]+)+", node))
            elif isinstance(node, dict):
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for item in node:
                    visit(item)
        visit(context)
        joined = "\n".join(self.src_text.values())
        for phrase in sorted(words):
            with self.subTest(context_phrase_length=len(phrase)):
                self.assertNotIn(phrase, joined)
        self.assertNotRegex(joined, r"\bC F Bb Eb\b|\b[A-G]b?[0-9]\b(?:\s+[A-G]b?[0-9]\b){2,}")
        self.assertNotRegex(joined, r"(?i)\b(october|10-5-26|2026-10-05)\b")

    def test_no_verdict_or_overclaim_wording_in_source(self):
        joined = "\n".join(self.src_text.values())
        for pattern in BANNED_PHRASES:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, joined, re.I))
        self.assertNotRegex(joined, r"(?i)\b(detects?|finds?|flags?|identif(y|ies)) (missed|wrong) notes?\b")
        self.assertNotRegex(joined, r"(?i)recovered original (stem|stems)\b")

    def test_no_forbidden_surface_in_source(self):
        ruleset = load_rules()
        form_rule = next(r for r in ruleset["rules"] if r["id"] == "form-or-upload-surface")
        for rel, text in self.src_text.items():
            with self.subTest(file=rel):
                self.assertIsNone(form_rule["regexp"].search(text))
                self.assertNotRegex(text, r"<(audio|video|iframe|object|embed|img|picture|input|select)\b")
                self.assertNotRegex(text, r"(?i)\b(action|method|enctype)=")
                self.assertNotRegex(text, r"document\.cookie|navigator\.sendBeacon|\bfetch\(|XMLHttpRequest|WebSocket")
                self.assertNotRegex(text, r"\bon(click|keydown|keyup|submit)=")
                self.assertNotRegex(text, r"\btabindex=")

    def test_authored_links_are_root_relative_or_fragments(self):
        hrefs = []
        for rel, text in self.src_text.items():
            hrefs += re.findall(r'href="([^"{]*)"', text)
            hrefs += re.findall(r"href: '([^']*)'", text)
        hrefs = [h for h in hrefs if "%sveltekit" not in h]
        self.assertGreaterEqual(len(hrefs), 8)
        self.assertEqual([h for h in hrefs if not h.startswith(("/", "#")) or h.startswith("//")], [])
        self.assertNotRegex("\n".join(self.src_text.values()), r"https?://")

    def test_m19_no_authored_colour_literal(self):
        hits = [rel for rel, text in self.src_text.items() if COLOUR_LITERAL.search(text)]
        self.assertEqual(hits, [])
        self.assertTrue(COLOUR_LITERAL.search("#" + "1a2b3c") and COLOUR_LITERAL.search("okl" + "ch(0 0 0)"))
        self.assertIsNone(COLOUR_LITERAL.search('href="#content" color-mix(in oklch, var(--x) 5%, transparent)'))

    def test_agents_loader_emits_only_public_fields(self):
        loader = self.src_text["src/routes/agents/+page.server.ts"]
        self.assertIn(
            "return { name, title: trips(title) ? name : title, intent: withheld ? null : intent, "
            "skill_name: skillMatch[1] };", loader)
        for forbidden in ("inputSchema", "limitations", "dependencies", "agent_workflow", "evidence_kind",
                          "description", "instrument_context"):
            with self.subTest(field=forbidden):
                self.assertNotRegex(loader, r"tool\." + forbidden + r"\b")
        self.assertIn("'program', 'tools.json'", loader)
        self.assertRegex(loader, r"throw new Error\('agents page: the tool registry lists no tools'\)")
        self.assertEqual([p for p in site_files() if p.name == "tools.json"], [])

    def test_app_shell_language_and_no_external_resources(self):
        shell = self.src_text["src/app.html"]
        self.assertIn('<html lang="en"', shell)
        self.assertNotRegex(shell, r"https?://|<script")
        css = self.src_text["src/app.css"]
        self.assertNotRegex(css, r"@import\s+(url\()?['\"]https?:")
        self.assertNotRegex(css, r"@keyframes|animation:|transition:")


class LeakRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ruleset = load_rules()
        cls.document = cls.ruleset["document"]

    def test_rule_file_shape(self):
        rules = self.document["rules"]
        self.assertEqual([r["id"] for r in rules], list(EXPECTED_RULE_IDS))
        self.assertEqual(len({r["id"] for r in rules}), 24)
        for rule in rules:
            with self.subTest(rule=rule["id"]):
                self.assertTrue(rule["pattern"] and rule["description"])
                self.assertRegex(rule["flags"], r"^(u|iu)$")
                re.compile(rule["pattern"], re.A)
        self.assertEqual({r["id"] for r in rules if r.get("vendorCarrier")}, set(VENDOR_CARRIER_RULE_IDS))
        self.assertEqual({r["id"] for r in rules if r.get("sourceScope") == "src"}, set(SRC_ONLY_RULE_IDS))
        self.assertEqual({r["id"] for r in rules if r.get("skipVendorRuntimeChunks")},
                         {"internal-tracker-reference", "operator-banned-dash"})

    def test_upstream_private_name_rule_is_not_ported(self):
        ids = {r["id"] for r in self.document["rules"]}
        self.assertNotIn("plan-private-name", ids)
        self.assertNotIn("unsourced-promise", ids)

    def test_allowlists_are_minimal_and_explained(self):
        self.assertEqual(self.document["allowedMailboxes"], [])
        hosts = self.document["allowedHosts"]
        self.assertEqual(hosts, sorted(set(hosts)))
        comment = "\n".join(self.document["allowedHostsComment"])
        for host in hosts:
            with self.subTest(host=host):
                self.assertIn(host, comment)
                self.assertIsNone(next(r for r in self.ruleset["rules"]
                                       if r["id"] == "private-estate-hostname")["regexp"].search(host))
        self.assertNotIn(FORGE_HOST, hosts)
        self.assertLessEqual(len(self.document.get("allowedPublicForgeUrls", [])), 2)

    def test_rule_file_does_not_match_itself(self):
        text = RULES_PATH.read_text(encoding="utf-8")
        findings = scan_text("scripts/leak-scan-rules.json", text, self.ruleset, "build")
        self.assertEqual(findings, [])

    def test_m10_python_port_fixture_verdicts(self):
        verdicts = fixture_verdicts_python(self.ruleset)
        self.assertEqual(len(verdicts), 48)
        for rule_id in EXPECTED_RULE_IDS:
            with self.subTest(rule=rule_id):
                self.assertTrue(verdicts[(rule_id, "pos")], "positive fixture did not fire")
                self.assertFalse(verdicts[(rule_id, "neg")], "negative control fired")

    def test_negative_fixtures_are_entirely_clean(self):
        for rule_id, (_, negative) in rule_fixtures().items():
            with self.subTest(rule=rule_id):
                self.assertEqual(scan_text(f"neg/{rule_id}.txt", negative, self.ruleset, "build"), [])

    def test_surface_scoping(self):
        dash = "a — b"
        tracker = "".join(("TI", "N-", "77"))
        self.assertEqual(scan_text("_app/immutable/chunks/x.js", dash + tracker, self.ruleset, "build"), [])
        self.assertEqual(len(scan_text("_app/immutable/nodes/x.js", dash + " " + tracker, self.ruleset, "build")), 2)
        self.assertEqual(scan_text("scripts/x.mjs", dash, self.ruleset, "source"), [])
        self.assertEqual(len(scan_text("src/x.svelte", dash, self.ruleset, "source")), 1)
        self.assertEqual(scan_text("pkg/BUILD", tracker + " https://unknown.example/", self.ruleset, "vendor"), [])
        self.assertEqual(len(scan_text("pkg/x", "".join(("/n", "ix/st", "ore/abc")), self.ruleset, "vendor")), 1)

    def test_host_and_mailbox_allowlists(self):
        self.assertEqual([f["ruleId"] for f in scan_text("a.html", "see https://unknown.example/x", self.ruleset)],
                         ["unreviewed-outbound-host"])
        self.assertEqual(scan_text("a.svg", 'xmlns="http://www.w3.org/2000/svg"', self.ruleset), [])
        self.assertEqual([f["ruleId"] for f in scan_text("a.html", "write to someone@unknown.example", self.ruleset)],
                         ["unreviewed-mailbox"])

    def test_forge_urls_pass_only_when_exact(self):
        allowed = self.document.get("allowedPublicForgeUrls", [])
        for url in allowed:
            with self.subTest(kind="exact"):
                self.assertEqual(scan_text("fonts/OFL.txt", f"({url})", self.ruleset), [])
            with self.subTest(kind="deeper path"):
                fired = {f["ruleId"] for f in scan_text("fonts/OFL.txt", f"({url}/issues/1)", self.ruleset)}
                self.assertEqual(fired, {"internal-tracker-reference", "unreviewed-outbound-host"})
        other = "https://" + FORGE_HOST + "/example/private-repository"
        self.assertEqual({f["ruleId"] for f in scan_text("a.html", other, self.ruleset)},
                         {"internal-tracker-reference", "unreviewed-outbound-host"})
        self.assertEqual({f["ruleId"] for f in scan_text("a.html", "hosted on " + FORGE_HOST, self.ruleset)},
                         {"internal-tracker-reference"})

    def test_framework_deviation_patterns_still_catch_authored_content(self):
        fired = lambda text: {f["ruleId"] for f in scan_text("a.html", text, self.ruleset)}
        self.assertIn("form-or-upload-surface", fired("".join(("<input ty", 'pe="fi', 'le">'))))
        self.assertIn("form-or-upload-surface", fired("".join(("<text", "area>"))))
        self.assertNotIn("form-or-upload-surface", fired("".join((".input[ty", "pe=fi", "le]::x{}"))))
        self.assertIn("analytics-or-beacon", fired("".join(("ad.double", "click", ".net"))))
        self.assertNotIn("analytics-or-beacon", fired("".join(("onDouble", "Click"))))

    def test_m12_source_scan_is_clean(self):
        result = source_scan(self.ruleset)
        self.assertGreater(len(result["files_scanned"]), 15)
        self.assertEqual(len(result["rules_applied"]), 24)
        self.assertEqual([(f["ruleId"], f["file"], f["line"]) for f in result["findings"]], [])
        self.assertEqual(result["files_unscannable"], [])
        self.assertIn("scripts/leak-scan-rules.json", result["files_scanned"])
        self.assertIn("DEPLOY.md", result["files_scanned"])

    def test_vendor_carriers_pass_the_nine_carrier_rules(self):
        result = vendor_scan(self.ruleset)
        self.assertEqual(len(result["rules_applied"]), 9)
        self.assertEqual([(f["ruleId"], f["file"]) for f in result["findings"]], [])
        self.assertTrue(all(name.endswith(".woff2") for name in result["files_unscannable"]))

    def test_m13_no_exact_real_take_identifier_under_site(self):
        identifiers = real_take_identifiers()
        self.assertGreaterEqual(identifiers["by_kind"].get("source_sha256", 0), 1)
        self.assertGreaterEqual(identifiers["by_kind"].get("recording_basename", 0), 1)
        self.assertEqual(identifier_hits(identifiers["identifiers"], include_build=True), [])

    def test_private_app_hostname_is_absent_when_known(self):
        hostnames = private_app_hostnames()
        if not hostnames:
            self.skipTest("private app hostname is null in deploy/cloudflare (private_app_hostname_checked: false)")
        for path in site_files():
            data = path.read_bytes()
            for hostname in hostnames:
                self.assertNotIn(hostname.encode(), data)

    def test_no_site_file_references_private_trees_or_the_real_take(self):
        needles = [b"".join((b"art", b"ifacts", b"/")), b"".join((b"art", b"ifacts", b"\\")),
                   b"".join((b".loc", b"al/sprint")), b"".join((b"Mov", b"ie on "))]
        checked = 0
        for path in site_files():
            data = path.read_bytes()
            checked += 1
            for needle in needles:
                with self.subTest(file=path.relative_to(SITE).as_posix()):
                    self.assertFalse(needle in data, "a private tree or recording name is referenced")
        self.assertGreater(checked, 40)
        media = [p.relative_to(SITE).as_posix() for p in site_files()
                 if p.suffix.lower() in BUILD_REFUSED_EXT - {".gz"}]
        self.assertEqual(media, [])


@unittest.skipUnless(shutil.which("node"), "node is not on PATH; the Node scanner cannot run")
class LeakScannerNodeTests(unittest.TestCase):
    def test_m10_node_fixture_verdicts_agree_with_the_python_port(self):
        node = fixture_verdicts_node()
        python = fixture_verdicts_python(load_rules())
        self.assertEqual(len(node), 48)
        for rule_id in EXPECTED_RULE_IDS:
            with self.subTest(rule=rule_id):
                self.assertTrue(node[(rule_id, "pos")])
                self.assertFalse(node[(rule_id, "neg")])
        self.assertEqual(sum(1 for key in node if node[key] == python[key]), 48)

    def test_node_and_python_agree_on_real_surfaces(self):
        ruleset = load_rules()
        for directory, surface in ((SITE, "source"), (VENDOR, "vendor")):
            with self.subTest(surface=surface), tempfile.TemporaryDirectory() as tmp:
                report = Path(tmp) / "report.json"
                result = run_node_scanner(directory, surface, report)
                data = json.loads(report.read_text(encoding="utf-8"))
                expected = scan_directory(directory, ruleset, surface)
                self.assertEqual(result.returncode, 0, result.stdout[-600:])
                self.assertEqual(data["files_scanned"], expected["files_scanned"])
                self.assertEqual(data["files_unscannable"], expected["files_unscannable"])
                self.assertEqual(data["rules_applied"], expected["rules_applied"])
                self.assertEqual(data["findings_count"], len(expected["findings"]))
                self.assertNotIn(str(REPO), report.read_text(encoding="utf-8"))

    def test_build_surface_refuses_maps_media_and_unknown_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tree"
            root.mkdir()
            (root / "index.html").write_text("<p>clean</p>\n", encoding="utf-8")
            (root / "font.woff2").write_bytes(b"\x00\x01")
            clean = run_node_scanner(root)
            self.assertEqual(clean.returncode, 0, clean.stdout)
            self.assertRegex(clean.stdout, r"files=1 unscannable=1 findings=0")
            (root / "app.js.map").write_text("{}", encoding="utf-8")
            (root / "clip" ".m4v").write_bytes(b"\x00")
            (root / "blob.bin").write_bytes(b"\x00")
            report = Path(tmp) / "report.json"
            dirty = run_node_scanner(root, "build", report)
            self.assertEqual(dirty.returncode, 1)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["findings_by_rule"], {"refused-file-type": 2, "unclassified-file-type": 1})
            python = scan_directory(root, load_rules(), "build")
            self.assertEqual(sorted((f["ruleId"], f["file"]) for f in python["findings"]),
                             sorted((f["ruleId"], f["file"]) for f in data["findings"]))
            self.assertRegex(dirty.stdout, r"(?m)^refused-file-type app\.js\.map:0$")

    def test_usage_errors_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = subprocess.run(["node", str(SCANNER)], capture_output=True, text=True,
                                     timeout=NODE_TIMEOUT_S, check=False)
            bad_surface = run_node_scanner(Path(tmp), "everything")
            not_a_directory = run_node_scanner(Path(tmp) / "absent")
        self.assertEqual((missing.returncode, bad_surface.returncode, not_a_directory.returncode), (2, 2, 2))


def _build_skip_reason() -> str | None:
    if shutil.which("node") is None:
        return "node is not on PATH"
    if shutil.which("pnpm") is None:
        return "pnpm is not on PATH"
    if not (SITE / "node_modules").is_dir():
        return "site/node_modules is absent; run `pnpm install --frozen-lockfile` in site/ first (never run by tests)"
    return None


@unittest.skipIf(_build_skip_reason() is not None, _build_skip_reason() or "")
class BuildTests(unittest.TestCase):
    """Runs check then build once, and only inspects the build it just produced."""

    @classmethod
    def setUpClass(cls):
        if BUILD.exists():
            shutil.rmtree(BUILD)  # a stale build is never trusted
        cls.check = run_pnpm("check", CHECK_TIMEOUT_S)
        if cls.check.returncode == PNPM_GATE_UNAVAILABLE_EXIT:
            raise unittest.SkipTest("pnpm storage gate unavailable on this host (exit 75)")
        cls.build = run_pnpm("build", BUILD_TIMEOUT_S) if cls.check.returncode == 0 else None
        cls.metrics = build_metrics(BUILD) if cls.build is not None and cls.build.returncode == 0 else None

    def setUp(self):
        self.assertEqual(self.check.returncode, 0, (self.check.stdout + self.check.stderr)[-1500:])
        self.assertIsNotNone(self.build)
        self.assertEqual(self.build.returncode, 0, (self.build.stdout + self.build.stderr)[-1500:])
        self.assertIsNotNone(self.metrics)

    def test_m4_m5_check_and_build_exit_zero_with_no_diagnostics(self):
        summary = re.search(r"COMPLETED (\d+) FILES (\d+) ERRORS (\d+) WARNINGS", self.check.stdout)
        self.assertIsNotNone(summary, self.check.stdout[-600:])
        self.assertEqual((summary.group(2), summary.group(3)), ("0", "0"))
        self.assertNotRegex(self.build.stdout + self.build.stderr, r"(?i)\ba11y_[a-z_]+\b")

    def test_m7_expected_pages_and_nothing_else(self):
        self.assertEqual(self.metrics["pages_present"], list(EXPECTED_HTML))
        self.assertEqual(self.metrics["html_files"], sorted(EXPECTED_HTML))
        self.assertEqual(self.metrics["source_maps"], [])
        self.assertEqual(self.metrics["compressed_twins"], [])
        self.assertTrue((BUILD / "_headers").is_file())
        self.assertFalse((BUILD / "_redirects").exists())
        self.assertFalse((BUILD / "service-worker.js").exists())

    def test_m8_every_registry_tool_is_rendered(self):
        agents = self.metrics["agents"]
        self.assertGreater(agents["tools_in_registry"], 0)
        self.assertEqual(agents["tools_rendered"], agents["tools_in_registry"])
        self.assertEqual(agents["unexpected_tools"], [])
        document = parse_html(BUILD / "agents.html")
        tools = json.loads(TOOLS_JSON.read_text(encoding="utf-8"))["tools"]
        summary = next(e for e in document.iter() if "data-tool-count" in e.attrs)
        self.assertEqual(int(summary.attrs["data-tool-count"]), len(tools))
        self.assertEqual(int(summary.attrs["data-skill-count"]), len({t["skill"] for t in tools}))
        self.assertEqual(int(summary.attrs["data-intents-withheld"]), agents["intents_withheld"])
        rendered_status = {e.attrs["data-status"]: int(e.attrs["data-status-count"])
                           for e in document.iter() if "data-status" in e.attrs}
        self.assertEqual(rendered_status, agents["status_counts"])
        by_name = {t["name"]: t for t in tools}
        for card in (e for e in document.iter() if "data-tool" in e.attrs):
            tool = by_name[card.attrs["data-tool"]]
            intents = [e.text().strip() for e in card.iter() if "data-tool-intent" in e.attrs]
            withheld = [e for e in card.iter() if "data-intent-withheld" in e.attrs]
            with self.subTest(tool=tool["name"]):
                self.assertEqual(len(intents) + len(withheld), 1)
                if intents:
                    self.assertEqual(intents[0], tool["intent"])
                self.assertEqual([e.text().strip() for e in card.iter() if "data-skill-name" in e.attrs],
                                 [Path(tool["skill"]).parent.name])

    def test_m9_no_forbidden_tool_field_is_published(self):
        agents = self.metrics["agents"]
        self.assertGreater(agents["forbidden_candidates_checked"], 50)
        self.assertEqual(agents["forbidden_hits"], [])

    def test_m11_build_scan_is_clean_in_both_scanners(self):
        scan = self.metrics["build_scan"]
        self.assertEqual(scan["rules_applied"], 24)
        self.assertGreater(scan["files_scanned"], 10)
        self.assertEqual((scan["findings"], scan["finding_rules"]), (0, []))
        self.assertTrue(all(Path(name).suffix in BUILD_OPAQUE_EXT for name in scan["unscannable"]))
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            node = run_node_scanner(BUILD, "build", report)
            data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(node.returncode, 0, node.stdout[-800:])
        self.assertEqual((data["files_scanned_count"], data["files_unscannable_count"], data["findings_count"]),
                         (scan["files_scanned"], len(scan["unscannable"]), 0))

    def test_m13_no_exact_real_take_identifier_in_the_build(self):
        self.assertEqual(self.metrics["identifier_hits_build"], 0)

    def test_m14_required_unknowns_are_rendered_on_their_pages(self):
        placements = self.metrics["unknown_placements"]
        self.assertEqual(len(placements), 15)
        self.assertEqual([key for key, present in placements.items() if not present], [])

    def test_m15_every_claim_element_uses_the_closed_class_set(self):
        self.assertGreater(self.metrics["claim_elements"], 20)
        self.assertEqual(self.metrics["claim_elements_in_closed_set"], self.metrics["claim_elements"])

    def test_feature_sections_carry_a_measured_vs_unknown_note(self):
        sections = self.metrics["feature_sections"]
        self.assertEqual(sorted(sections), ["agent_tools", "restoration", "review"])
        for name, section in sections.items():
            with self.subTest(section=name):
                self.assertTrue(section["note_visible"])
                self.assertGreaterEqual(section["measured_or_implemented"], 1)
                self.assertGreaterEqual(section["unknown"], 1)

    def test_home_states_the_three_axioms_and_status_states_storage(self):
        home = parse_html(BUILD / "index.html")
        self.assertEqual(len([e for e in home.iter() if "data-axiom" in e.attrs]), 3)
        status = visible_text(parse_html(BUILD / "status.html"))
        for phrase in ("Logic", "Final Cut", "Resolve", "local storage", "no analytics"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, status)

    def test_m16_no_banned_affirmative_phrase(self):
        self.assertEqual(len(self.metrics["banned_phrase_hits"]), 10)
        self.assertEqual({p: n for p, n in self.metrics["banned_phrase_hits"].items() if n}, {})

    def test_m17_no_forbidden_surface(self):
        surfaces = self.metrics["forbidden_surfaces"]
        for key in (*FORBIDDEN_TAGS, "file_inputs", "third_party_origin_attributes", "authored_outbound_links",
                    "action_or_method_attributes"):
            with self.subTest(surface=key):
                self.assertEqual(surfaces[key], 0)
        self.assertEqual(surfaces["inputs"], [])
        for name in EXPECTED_HTML:
            scripts = parse_html(BUILD / name).find_all("script")
            with self.subTest(page=name):
                self.assertTrue(all("src" not in s.attrs for s in scripts))
                self.assertLessEqual(len(scripts), 2)

    def test_m18_accessibility_structure(self):
        self.assertEqual(self.metrics["accessibility_total"], 32)
        failed = {f"{page}:{check}" for page, checks in self.metrics["accessibility"].items()
                  for check, passed in checks.items() if not passed}
        self.assertEqual(failed, set())
        self.assertEqual(self.metrics["accessibility_passed"], 32)

    def test_fallback_page_keeps_language_and_no_take_data(self):
        text = (BUILD / "404.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="en"', text)
        self.assertNotIn("data-tool=", text)


if __name__ == "__main__":
    unittest.main()
