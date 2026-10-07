"""Bazel entry point for one stdlib unittest module.

`bazel test //tests:<module>` runs this file with the module name as the first
argument. It reproduces `PYTHONPATH=tests python3 -m unittest <module> -v` from
the repository root:

- the module is imported from the declared tests/ runfiles directory;
- the working directory is the real checkout when the runfiles are symlinks
  (the test modules already resolve their own path back to it), otherwise the
  runfiles root, where the same tracked files are present as declared data;
- a Bazel --test_filter is forwarded as a unittest -k pattern;
- PYTHONSAFEPATH, which the rules_python launcher exports for this process, is
  removed from the environment so that worker scripts the tests start as
  subprocesses (`python scripts/<worker>.py`) get their own directory on
  sys.path, exactly as under the reference command. Without this, every such
  subprocess fails with ModuleNotFoundError on its sibling imports.

Stdlib only. Starts no process and applies no timeout of its own: Bazel bounds
the test through the target's timeout.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


def runfiles_workspace() -> Path:
    """Returns the runfiles directory of this workspace (tools/bazel/../..)."""
    return Path(__file__).absolute().parents[2]


def checkout_root(module: str) -> Path:
    declared = runfiles_workspace() / "tests" / f"{module}.py"
    if not declared.is_file():
        raise SystemExit(f"unittest_main: {declared} is not in the runfiles")
    return declared.resolve().parents[1]


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].startswith("test_"):
        raise SystemExit("usage: unittest_main.py <test_module> [unittest arguments]")
    module = argv[1]
    tests_directory = str(runfiles_workspace() / "tests")
    if tests_directory not in sys.path:
        sys.path.insert(0, tests_directory)
    os.chdir(checkout_root(module))
    os.environ.pop("PYTHONSAFEPATH", None)
    arguments = [f"python -m unittest {module}", "-v", *argv[2:]]
    selected = os.environ.get("TESTBRIDGE_TEST_ONLY")
    if selected:
        arguments += ["-k", selected]
    program = unittest.main(module=module, argv=arguments, exit=False)
    return 0 if program.result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
