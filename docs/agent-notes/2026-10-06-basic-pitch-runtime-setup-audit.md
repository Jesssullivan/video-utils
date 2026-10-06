# Independent optional runtime setup source audit

Owner: `/root/tonal_inference/tonal_audit`. Authority: root's explicit independent
installer source/unit review under the operator's ten-hour parallel goal;
R-HOOK-CONVERGENCE-20261004 / R-N13. This lane owns this note and
`tests/test_basic_pitch_runtime_setup_audit.py` only. The implementation owner
retains its installer/tests; root owns release and publication.

**PASS for reviewed source and isolated regressions. Fresh installation remains
unexecuted and unqualified by this audit.** No setup, wheel download, model
acquisition, package installation, inference, current-runtime mutation or
comparator-worker edit was performed here.

Reviewed identities:

| Artifact | SHA256 |
|---|---|
| `scripts/basic_pitch_runtime_setup.py` | `4da3b0f321e2918b44bbb46c6a5688b5ab5f633a59ba1f7ae020b27b5e4b7dd6` |
| `tests/test_basic_pitch_runtime_setup.py` | `7ee71e012318c7a852e820c02e7759d36895011f97358a465907525daab6e98c` |
| `tests/test_basic_pitch_runtime_setup_audit.py` | `9001c8db9158c7fc0669cfe33a22be1f23a6f029ab736ad97dd93d10d75d9a17` |
| `program/basic-pitch-runtime.json` | `c0e0a0f01023d5e701c13bcd092d23ef216dd3e96b2bc0320293c355252df23f` |

## Findings and closure

Four concrete findings were independently reproduced with temporary directories
and mocked networking, then fixed by the implementation owner:

1. A final rename could replace an existing wheel. The revised fetch refuses an
   existing destination before requesting bytes and uses same-directory atomic
   hardlink finalization, which also refuses a late destination collision.
2. A final response-URL check occurred after urllib's redirect dispatch. The
   custom redirect handler now rejects nonofficial hosts and non-HTTPS schemes
   before the next request; both cases pass independent no-contact fixtures.
   URL validation also rejects credentials and ports other than default/443.
3. Lexical parent traversal could pass checkout-prefix containment. The revised
   confinement rejects `..` before checking the absolute path and symlink
   ancestors. The fixture never creates an outside path.
4. Lock file hashing and payload parsing used separate reads. A deterministic
   post-hash mutation returned bytes outside the pinned digest. The revised
   loader reads at most 32,769 bytes once, checks the size and SHA256 of that
   exact byte string, and only then parses/copies it.

All four independent tests pass on the reviewed source:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tests -p test_basic_pitch_runtime_setup_audit.py -v
```

The owner reports its 20 tests plus these four passing together. This audit
independently reran only its four relevant regressions after fixes; it did not
repeat the existing runtime import check or model inference.

## Remaining source readback

The exact c0e lock specifies five qualified official wheels totaling 34,171,831
compressed bytes. Acquisition is explicit and restricted to official HTTPS;
each archive's declared size and hash are checked before ZIP parsing. The
inventory rejects traversal, absolute paths, backslashes, drive-colon forms,
symlinks, unusual file types, encryption, duplicate names and unsupported `.data`
relocations, with cumulative member and expanded-byte ceilings. Installed
expected members are checked for confinement, extent and digest.

Unsupported host architecture, macOS version, Python version/implementation or
free-threaded interpreter fails preflight without a fallback interpreter or
uv download. The venv launcher stays at its lexical stable path; its reported
prefix/site and `include-system-site-packages=false` are checked. Installation
uses exactly the five local wheel paths through uv with offline/no-index,
no-dependencies, no-build and no-Python-download flags. Fresh-install execution
of this exact argv is still unproven.

An existing runtime is checked, never replaced or silently repaired. A missing
runtime with `--check` causes no acquisition. Owned install/create children have
deadline, sampled RSS and log bounds plus finally cleanup and R-N11 receipts;
failure preserves a separate setup receipt. This operation never acquires,
registers or executes the Basic Pitch comparator model. The comparator worker
remains frozen at SHA256
`407ff9fe99edbc863b3822c98683026841a3e03d2f6b7705a746bf7c68025cf3`.

The earlier [owner checkpoint](2026-10-06-basic-pitch-runtime-setup-checkpoint.json)
records the historical pre-audit installer identity, 17 tests, a successful
existing-runtime check of 1,349 installed members, and matching pre/post snapshots
of 1,484 files/symlinks. It does not qualify the revised installer or a fresh
installation. The subsequent [final read-only receipt](2026-10-06-basic-pitch-runtime-setup-final-check.json),
SHA256 `664e4726a14543d4a9c3ce52de9728d9dcb75cdafad8dd9a9f22e97a52e0f1c9`,
records the reviewed revised installer passing the existing-runtime check,
again verifying 1,349 members with all 1,484 file/symlink snapshots unchanged
and 155,558,142 runtime bytes. Its identity/content were read back independently;
the execution and complete snapshot measurements belong to the owner.

Root may separately release a fresh isolated setup qualification without
modifying the current accepted runtime. No remaining source must-fix was found
in this bounded audit.
