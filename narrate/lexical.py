"""The xoxd-lexical pass (docs/spec/NARRATE.md, "Lexical pin contract").

A job pins one release by tag, commit and the digests of its estate-lexicon.json, its prompt digest
(prompt-digest-narration.txt for the narration register, prompt-digest.txt for the others) and its Vale
register file. The release directory (the release's dist/, fetched explicitly and kept outside git) is read by
path; every pinned file's sha256 must match or the pass refuses. Nothing is fetched.

- Findings: every deterministic Pattern rule whose registers include the job's register is matched against
  the written text of each segment (before spoken normalisation), where the house-style rules apply. Findings
  are advisory and recorded, never blocking. A pattern Python cannot compile is recorded as skipped, not
  dropped silently.
- Vale: when `vale` is on PATH, the register's rules run through it and its findings are recorded. Absent,
  the record says not_run. Vale never blocks.
- RewriteCheck (XL-ACC-001 and XL-ACC-002): a rewrite of the script (an agent's, after it read
  the prompt digest) is accepted only when every number, unit, version, link, path, ticket, handle and
  identifier it speaks is the same, byte for byte and in the same order, as the original's. A recognised range or
  dollar amount the rewrite says in words (amounts.find) counts as kept when the words read back to the original's
  values: "seventeen to nineteen" keeps "17–19", "eighteen to nineteen" does not.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .ir import sha256_file

LEXICON, PROMPT_DIGEST = "estate-lexicon.json", "prompt-digest.txt"
REWRITE_RULES = ("XL-ACC-001", "XL-ACC-002")
# The recognised units, shared by the RewriteCheck's protected spans (and so the chunker, which never splits
# one) and spoken normalisation's quantity guard (narrate/normalise.py). Each unit's first alias is its
# written symbol; KB is a second symbol for kB. Aliases are explicit, never inferred: 1 ms is not 1 s, nor
# GiB GB. Symbols are case sensitive; written-out aliases use their conventional lower case.
UNITS = {
    "%": ("%", "percent", "per cent"),
    "ms": ("ms", "millisecond", "milliseconds"),
    "s": ("s", "second", "seconds"),
    "min": ("min", "minute", "minutes"),
    "h": ("h", "hour", "hours"),
    "Hz": ("Hz", "hertz"),
    "kHz": ("kHz", "kilohertz"),
    "MHz": ("MHz", "megahertz"),
    "GHz": ("GHz", "gigahertz"),
    "dB": ("dB", "decibel", "decibels"),
    "dBFS": ("dBFS", "decibels relative to full scale"),
    "dBTP": ("dBTP", "decibels true peak"),
    "LUFS": ("LUFS", "loudness units relative to full scale"),
    "LU": ("LU", "loudness unit", "loudness units"),
    "fps": ("fps", "frames per second"),
    "bpm": ("bpm", "beats per minute"),
    "px": ("px", "pixel", "pixels"),
    "x": ("x", "times"),
    "B": ("B", "byte", "bytes"),
    "kB": ("kB", "KB", "kilobyte", "kilobytes"),
    "MB": ("MB", "megabyte", "megabytes"),
    "GB": ("GB", "gigabyte", "gigabytes"),
    "TB": ("TB", "terabyte", "terabytes"),
    "KiB": ("KiB", "kibibyte", "kibibytes"),
    "MiB": ("MiB", "mebibyte", "mebibytes"),
    "GiB": ("GiB", "gibibyte", "gibibytes"),
    "TiB": ("TiB", "tebibyte", "tebibytes"),
}
_SYMBOLS = sorted([unit for unit in UNITS if unit != "%"] + ["KB"], key=len, reverse=True)
# Spans a rewrite must keep: links, paths, tickets, handles, versions, identifiers, numbers with their units.
PROTECTED = re.compile(
    r"""
    (?P<url>\b[a-z][a-z0-9+.-]*://[^\s<>"')\]]+)
  | (?P<ticket>\b[A-Z][A-Z0-9]+-\d+\b)
  | (?P<handle>(?<![\w.])@[\w-]+(?:/[\w.-]+)?)
  | (?P<path>(?<![\w.])(?:\.{0,2}/)?(?:[\w.-]+/)+[\w.-]+)
  | (?P<version>\bv?\d+(?:\.\d+){1,3}(?:[-+][\w.]+)?\b)
  | (?P<ident>\b(?:[a-z]+(?:[A-Z][a-z0-9]*)+|[A-Za-z]+_[\w]+|[A-Za-z]*\d+[A-Za-z][\w]*)\b|`[^`]+`)
  | (?P<number>(?<![\w.])[-+\N{MINUS SIGN}]?\d+(?:[.,]\d+)*
        (?:\s?(?:%|(?:UNITS)\b))?)
    """.replace("UNITS", "|".join(_SYMBOLS)),
    re.VERBOSE,
)


class LexicalError(RuntimeError):
    """The pinned release is missing or does not match its digests; or a rewrite was refused."""

    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class Release:
    """One pinned xoxd-lexical release, verified against the job's lexical pin."""

    def __init__(self, directory, pin):
        if directory is None or not Path(directory).is_dir():
            raise LexicalError(
                "lexical_missing",
                f"no xoxd-lexical release directory for {pin['release']} "
                "(set lexical in narrate.toml or NARRATE_LEXICAL_DIR)",
            )
        self.dir, self.pin = Path(directory), pin
        self.register = pin["valeRegister"]
        self.prompt_name = "prompt-digest-narration.txt" if self.register == "narration" else PROMPT_DIGEST
        files = {
            "lexicon": (self.dir / LEXICON, pin["lexiconSha256"]),
            "prompt_digest": (self.dir / self.prompt_name, pin["promptDigestSha256"]),
            "vale_register": (self.dir / "vale" / "registers" / f"{self.register}.ini", pin["valeRegisterSha256"]),
        }
        self.digests = {}
        for name, (path, want) in files.items():
            if not path.is_file():
                raise LexicalError("lexical_missing", f"{pin['release']} has no {path.relative_to(self.dir)}")
            got = sha256_file(path)
            if got != want:
                raise LexicalError(
                    "lexical_digest_mismatch", f"{path.relative_to(self.dir)} is {got[:12]}, the job pins {want[:12]}"
                )
            self.digests[name] = got
        self.lexicon = json.loads(files["lexicon"][0].read_text(encoding="utf-8"))
        version = str(self.lexicon.get("version", ""))
        if not pin["release"].endswith("@" + version):
            raise LexicalError(
                "lexical_digest_mismatch", f"the lexicon says version {version!r}, the job pins {pin['release']}"
            )
        self.vale_register_path = files["vale_register"][0]
        self.upstream_pronunciation = None
        if self.register == "narration":
            table = self.lexicon.get("pronunciation")
            if not isinstance(table, dict) or not isinstance(table.get("entries"), list) or not table["entries"]:
                raise LexicalError("lexical_missing", "the narration release has no pronunciation table")
            if not isinstance(table.get("id"), str) or not table["id"] or not isinstance(table.get("language"), str):
                raise LexicalError("lexical_invalid", "the narration pronunciation identity is invalid")
            identities = set()
            for entry in table["entries"]:
                if not isinstance(entry, dict):
                    raise LexicalError("lexical_invalid", "a narration pronunciation entry is invalid")
                identity = entry.get("id")
                if not isinstance(identity, str) or not identity or identity in identities:
                    raise LexicalError("lexical_invalid", "narration pronunciation IDs must be unique")
                identities.add(identity)
                for name in ("written", "spoken"):
                    value = entry.get(name)
                    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
                        raise LexicalError("lexical_invalid", "a narration pronunciation form is invalid")
                if any(type(entry.get(name)) is not bool for name in ("wholeWord", "caseSensitive")):
                    raise LexicalError("lexical_invalid", "narration pronunciation flags must be boolean")
            # The table is already authenticated by lexiconSha256, not a separate
            # unpinned local copy. The local Dhall overlay runs after this layer.
            self.upstream_pronunciation = table

    def prompt_digest(self):
        """The text an agent reads before it writes or rewrites a script."""
        return (self.dir / self.prompt_name).read_text(encoding="utf-8")

    def rules(self):
        return [r for r in self.lexicon.get("rules", []) if self.register in r.get("registers", [])]

    def record(self):
        return {
            "release": self.pin["release"],
            "commit": self.pin["commit"],
            "register": self.register,
            "lexicon_sha256": self.digests["lexicon"],
            "prompt_digest_file": self.prompt_name,
            "prompt_digest_sha256": self.digests["prompt_digest"],
            "vale_register_sha256": self.digests["vale_register"],
            "rewrite_check": bool(self.pin["rewriteCheck"]),
        }


def findings(release, segments):
    """Advisory Pattern-rule findings over each segment's text: [{rule, segment, match, start}], and the
    rules skipped because Python cannot compile a pattern."""
    found, skipped = [], []
    for rule in release.rules():
        kind = rule.get("kind", {})
        if kind.get("type") != "Pattern":
            continue
        for pattern in kind.get("with", {}).get("patterns", []):
            try:
                compiled = re.compile(pattern)
            except re.error as error:
                skipped.append({"rule": rule["id"], "reason": f"pattern does not compile in Python: {error}"})
                continue
            for segment in segments:
                for match in compiled.finditer(segment.text):
                    found.append(
                        {
                            "rule": rule["id"],
                            "severity": rule.get("severity"),
                            "segment": segment.id,
                            "start": match.start(),
                            "match": match.group(0)[:80],
                        }
                    )
    found.sort(key=lambda f: (f["segment"], f["start"], f["rule"]))
    return {"status": "measured", "advisory": True, "findings": found, "skipped_rules": skipped}


def vale(release, segments, timeout=120):
    """Vale's findings with the register's rules when vale is on PATH; else not_run. Never raises for vale."""
    binary = shutil.which("vale")
    if not binary:
        return {"status": "not_run", "reason": "vale is not on PATH", "advisory": True}
    styles = release.dir / "vale"
    with tempfile.TemporaryDirectory() as work:
        ini = Path(work) / ".vale.ini"
        register = release.vale_register_path.read_text(encoding="utf-8")
        ini.write_text(f"StylesPath = {styles}\nMinAlertLevel = suggestion\n\n[*.txt]\n{register}")
        text = Path(work) / "script.txt"
        text.write_text("\n\n".join(s.text for s in segments), encoding="utf-8")
        try:
            p = subprocess.run(
                [binary, f"--config={ini}", "--output=JSON", str(text)], capture_output=True, text=True, timeout=timeout
            )
            report = json.loads(p.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            return {"status": "not_run", "reason": f"vale failed: {type(error).__name__}", "advisory": True}
    alerts = [
        {
            "rule": a.get("Check"),
            "line": a.get("Line"),
            "severity": a.get("Severity"),
            "match": str(a.get("Match", ""))[:80],
        }
        for items in report.values()
        for a in items
    ]
    return {"status": "measured", "advisory": True, "findings": alerts}


def protected_spans(text):
    """[(kind, span)] in reading order: what a rewrite must keep byte for byte."""
    spans = []
    for m in PROTECTED.finditer(text):
        span = m.group(0).strip()
        if m.lastgroup in ("url", "path"):
            span = span.rstrip(".,;:!?")  # sentence punctuation after a link or path is not part of it
        spans.append((m.lastgroup, span))
    return spans


def rewrite_check(before, after):
    """[] when the rewrite keeps every protected span; else one violation per difference (XL-ACC-001 for a span
    only the rewrite has, XL-ACC-002 for one it changed, dropped or reordered). A range or amount the rewrite says
    in words is first put back as the original's written form when its words read back to the same values."""
    from .amounts import restore  # amounts reads this module's UNITS

    a, b = protected_spans(before), protected_spans(restore(before, after))
    violations = []
    missing = [s for s in a if s not in b]
    added = [s for s in b if s not in a]
    for kind, span in added:
        violations.append({"rule": "XL-ACC-001", "kind": kind, "span": span, "problem": "only in the rewrite"})
    for kind, span in missing:
        violations.append({"rule": "XL-ACC-002", "kind": kind, "span": span, "problem": "changed or dropped"})
    if not violations and [s for _, s in a] != [s for _, s in b]:
        violations.append({"rule": "XL-ACC-002", "kind": "order", "span": "", "problem": "protected spans reordered"})
    return violations


def check_rewrite(original, rewritten):
    """Raise LexicalError(rewrite_refused) unless every segment's rewrite keeps its protected spans. The two
    scripts must have the same segment ids, in order."""
    if [s.id for s in original.segments] != [s.id for s in rewritten.segments]:
        raise LexicalError("rewrite_refused", "the rewrite does not keep the original's segment ids")
    problems = []
    for a, b in zip(original.segments, rewritten.segments, strict=True):
        problems += [{"segment": a.id, **v} for v in rewrite_check(a.text, b.text)]
    if problems:
        first = problems[0]
        raise LexicalError(
            "rewrite_refused",
            f"{len(problems)} protected span(s) differ; first: segment "
            f"{first['segment']} {first['rule']} {first['kind']} {first['span']!r} {first['problem']}",
        )
    return {"status": "accepted", "rules": list(REWRITE_RULES), "segments": len(original.segments)}
