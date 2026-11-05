"""Entry point for `bazel test //narrate:pytest`: the narrate pytest suite on the dev shell's python3.

The hermetic interpreter has no pytest, so this runs `python3 -m pytest` from PATH in the checkout's narrate/
directory, as `just narrate-test` does. PATH reaches the test only with --config=host-tools; run it inside
`nix develop .#condense`. Stdlib only.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    package = Path(__file__).resolve().parents[1]  # the runfiles symlink resolves back to the checkout
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONSAFEPATH", "PYTHONPATH", "PYTHONHOME")}
    python = shutil.which("python3", path=env.get("PATH"))
    probe = [python, "-c", "import pytest"] if python else None
    if not probe or subprocess.run(probe, env=env, capture_output=True).returncode:
        print(
            "bazel_pytest: no python3 with pytest on PATH; run under `nix develop .#condense` with --config=host-tools",
            file=sys.stderr,
        )
        return 1
    command = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", *sys.argv[1:]]
    return subprocess.run(command, cwd=package, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
