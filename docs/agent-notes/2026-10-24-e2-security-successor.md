# E2 security successor

Authority: explicit operator direction to advance the existing narration lanes;
repository AGENTS.md and R-HOOK-CONVERGENCE-20261004 (R-N11/R-N12/R-N13).
This isolated contributor branch starts at E2 commit
`d46755a5fd57590e4a8437a7805a295e7dabd4c8`; the existing E2 branch and session
remain with their original owner. The integration coordinator owns landing and
preserves the E7-after-E2/E4 dependency. Tracker: TIN-7085 / TIN-7097.

The pre-routing guard previously matched Host prefixes, so an originless request
naming `localhost.attacker.example` was accepted. The patch now parses the entire
authority: exactly `localhost`, `127.0.0.1` or `[::1]`, optionally followed by a
colon and a decimal port in 1..65535. Origin-bearing requests remain refused.
Userinfo, suffix domains, controls, backslashes, port junk and other literals
fail closed. There is no CORS grant.

A matching build stamp previously bypassed directory ownership checks, both in
the build fast path and when serving. Every stamp/hash trust decision now checks
custody first: an owned 0700 root; directory ancestors owned by the user or root
without other-writable permissions (root-owned sticky temporary directories are
permitted); and owned regular-file/directory descendants without other-writable
permissions. Directory components, executable and stamp remain nonsymlink.
CMake soname aliases are narrowly accepted for library filenames only: relative
same-directory leaf targets, owned at every hop, no cycle, and a checked regular
file endpoint. Escaping, broken and directory aliases fail closed. Existing
GGML source and build metadata confirm that these aliases are produced by the
default shared-library build. This includes nearby libraries in custody checks. Newly built trees are checked again before writing their stamp.
Custody failures explicitly exit: Bash disables errexit inside the build-current
conditional, so an implicit failure return would be insufficient.

Validation uses the actual added C++ pre-routing handler with HTTP type stubs,
compiled with C++11 and warnings as errors, plus the existing sourced wrapper
and fake command fixtures. Root modes 0755/0777, writable ancestors and writable
or symlinked source/output/binary/stamp/library descendants are refused before
fake server execution or current-build acceptance. The unmodified E2 fixture
reproduced both defects during independent review. Focused placement checks:
108 passed. Shellcheck, Ruff, Bash syntax, patch parsing and diff checks pass.

Execution is synthetic source validation only. No model, production server,
weights, real recording, GPU inference or host configuration was invoked or changed.
An additional existing client-fixture sweep reached 117 passed and one failure:
the synthetic render-fit test could not find FFmpeg on PATH. That environment
limitation is distinct from the passing security gate; no dependency was installed.
The normal heavy wrapper's private manager socket was unavailable; the existing
hash-qualified session-bus helper retained the same heavy slice, queue and caps.
Independent review and publication receipts follow in the integration handoff.
