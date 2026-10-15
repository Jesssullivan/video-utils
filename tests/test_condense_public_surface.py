"""condense/ is public source: it must carry no secrets, private addresses, host names or personal paths.

The patterns are the site's leak-scan rules (site/scripts/leak-scan-rules.json), applied to every tracked
text file under condense/ and to just/condense.just.
"""

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "site" / "scripts" / "leak-scan-rules.json"
APPLIED = ("secret-pem-block", "secret-ssh-key", "secret-cloud-access-key", "secret-forge-token",
           "secret-json-web-token", "secret-assignment", "internal-hostname", "private-network-address",
           "developer-filesystem-path", "nix-store-path", "private-estate-hostname", "real-take-filename")


def scanned_files():
    listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "condense",
                             "just/condense.just"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / name for name in listed.splitlines() if name.endswith((".py", ".md", ".toml", ".ini", ".just"))]


class CondensePublicSurface(unittest.TestCase):
    def test_condense_sources_match_no_leak_rule(self):
        rules = {rule["id"]: rule for rule in json.loads(RULES.read_text(encoding="utf-8"))["rules"]}
        compiled = {name: re.compile(rules[name]["pattern"], re.A | (re.I if "i" in rules[name]["flags"] else 0))
                    for name in APPLIED}
        files = scanned_files()
        self.assertGreater(len(files), 10)
        hits = [f"{path.relative_to(ROOT)}:{name}:{match.group(0)}"
                for path in files for name, pattern in compiled.items()
                for match in pattern.finditer(path.read_text(encoding="utf-8"))]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
