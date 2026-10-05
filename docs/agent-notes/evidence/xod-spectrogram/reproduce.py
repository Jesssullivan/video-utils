"""Reproduce the investigation using the operator's original isolated clone.

This launcher and pcen-proof-driver.ts are owned investigative glue. They do
not contain or redistribute the private xoxd TypeScript PCEN implementation.
The original executed proof and its numerical receipt remain unchanged.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
REVISION = "8264a38651c785aa0dd9c02e3569b2d979747d80"
PCEN_SHA256 = "2ac3c72a1a73f23fda0075ece831cbaeb30b2f205b9c9ef78a0515d6bb24ac3c"
PROOF_SHA256 = "1b32b59221b51086ce90d50e58ea3b65709900bdf9b6564210a5a8b2ddbbd48d"
DRIVER_SHA256 = "5595e59567abfd9c959584035ccdb18d8d487ade58ac081bb69159d7e6831a90"


def verify_clone():
    clone = ROOT / "artifacts/research/xoxd-spectrogram"
    revision = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    if revision != REVISION:
        raise ValueError("Original research clone must have the exact recorded revision")
    dirty = subprocess.run(
        ["git", "-C", str(clone), "status", "--porcelain"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    if dirty:
        raise ValueError("Original research clone must be clean")
    source = clone / "src/core/pcen.ts"
    if hashlib.sha256(source.read_bytes()).hexdigest() != PCEN_SHA256:
        raise ValueError("Original PCEN source must match the inspected SHA-256")
    for name, expected in (("proof.py", PROOF_SHA256),
                           ("pcen-proof-driver.ts", DRIVER_SHA256)):
        if hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Executed investigation worker changed: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verify_clone()
    if args.check_only:
        print("Exact original clone revision/source hash and owned worker hashes verified.")
        return
    if args.output is None:
        parser.error("--output must name a fresh direct child of artifacts/research")
    parent = ROOT / "artifacts/research"
    output = args.output.absolute()
    if output.parent.resolve() != parent.resolve() or output.exists():
        raise ValueError("Output must be a fresh direct child of artifacts/research")
    output.mkdir()
    shutil.copyfile(EVIDENCE / "proof.py", output / "proof.py")
    # The historical receipt calls this owned import driver pcen.ts.
    shutil.copyfile(EVIDENCE / "pcen-proof-driver.ts", output / "pcen.ts")
    subprocess.run([sys.executable, str(output / "proof.py")],
                   check=True, timeout=90, cwd=ROOT)


if __name__ == "__main__":
    main()
