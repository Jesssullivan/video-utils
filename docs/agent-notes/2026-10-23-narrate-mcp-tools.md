# W7a narrate MCP tools and the SIM scorer (2026-10-23)

Authority: operator plan of 2026-10-22/23 for narration v0 (parent TIN-7084, this
lane TIN-7090, tools half); R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13. Hooks
were advisory. No sibling repository was edited, no session was signalled, and no
host or plugin configuration changed.

## What lands on `feat/narrate-mcp-tools`

| Path | What |
| --- | --- |
| `program/tool-drafts/narrate.json`, `program/tools.json` | Four typed tools appended as 58-61: `narrate_render`, `narrate_voices`, `narrate_engines`, `narrate_evaluate`. Closed input schemas, intent, knobs, dependencies, evidence kind, limitations, agent workflow |
| `.agents/skills/narrate-{render,voices,engines,evaluate}/SKILL.md` | One skill per tool, pinned by sha256 in the admission test |
| `scripts/tool_api.py` | Path and argument checks before any worker; `python -m narrate COMMAND` in its own process group with a deadline; typed refusals carried through as receipts |
| `tests/test_s5_tool_admission.py` | Freezes tools 1-57 by digest, checks the draft equals the admitted descriptors, the refusals, and one end-to-end pass (inline text through the fake engine, voices, engines, evaluate) through `tool_api` and the stdio MCP server |
| `narrate/render.py`, `narrate/__main__.py` | `render --json` and range-checked job overrides recorded in `job.overrides`; `confidential` and `--no-hosted` only tighten |
| `narrate/registry.py` | `engines --reach`: a 2 s TCP connect, no request or token; the endpoint is never returned |
| `narrate/sim.py`, `narrate/sim_worker.py`, `narrate/evaluate.py` | SIM: ECAPA-TDNN cosine per delivered chunk against the speaking voice's reference clip, wSIM (10 s windows, 5 s hop), `--reference-voice` for a decoy |
| `program/models.json` | `speechbrain-spkrec-ecapa-voxceleb-embedding`, bound by sha256 and byte count at a pinned revision |
| `flake.nix` | `speechbrain` added to the existing `ml` shell from the locked nixpkgs; `flake.lock` is unchanged |
| `just/narrate.just` | `narrate-sim-model` fetches the registered checkpoint, hash-checked |
| test counts elsewhere | 57 to 61 tools, 55 to 59 prompts and 3 to 4 models in the older admission, web and contract tests and the regenerated web capabilities fixture |

## SIM model choice

- **Model:** speechbrain `spkrec-ecapa-voxceleb`, revision
  `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`. Only `embedding_model.ckpt` is
  registered. Its sha256 is `0575cb64…26a2` and it is 83,316,686 bytes. The
  `hyperparams.yaml` digest is recorded alongside.
- **Licence:** the model card front matter says `license: "apache-2.0"`; I read it
  at the pinned revision. The VoxCeleb training-data terms are separate.
- **Runtime:** torch and speechbrain in `nix develop .#ml`, on the CPU, with at most
  8 threads. The worker loads the state dict with `weights_only=True` and strict
  keys, and builds the front end the hyperparams declare (Fbank 80, sentence mean
  normalisation). This is the same path speechbrain's `verify_batch` takes, which
  does not apply `mean_var_norm_emb`.
- **Why not ONNX:** the bench had already pinned and licence-checked this
  checkpoint, and torch was already in the `ml` shell. An ONNX path would need a
  second model pin, onnxruntime in a shell and a reimplemented filterbank front end.
- **No numpy-only scorer:** it was not attempted.

## Gates (this continuation, 2026-10-23)

Everything ran inside `systemd-run --user --scope -p MemoryMax=6G nice -n 19 ionice -c3`, in the
condense shell, one step at a time, after a check of `/proc/pressure/memory`.

| Gate | Result |
| --- | --- |
| `just narrate-lint` | passed |
| `just narrate-test` | 174 passed, 1 skipped (the real-model SIM case, which needs `NARRATE_SIM_TEST_MODEL` and `NARRATE_SIM_TEST_PYTHON`) |
| `tests/` admission, contract, MCP, web-runs, bazel-graph and public-tree modules (14 modules, 293 tests) | 1 failure before the fix: `test_s4a` still expected 55 prompts (fixed to 59). 1 failure that is environmental: `test_tool_contracts` `marked_video` reports "No bounded supported installed font found" in this shell; the narrate change does not touch it |
| `nix eval .#devShells.x86_64-linux.ml.drvPath` | evaluates with speechbrain |
| Web vitest and Playwright counts | not run locally (no `node_modules`); CI runs them |

## Measurements from the lane's earlier run (before the stop)

These ran between 16:54Z and 17:19Z, on the CPU host, with 8 torch threads. That
window overlaps the 17:14Z host incident (TIN-7085 comment e878a04f). They ran
before the rule that bans torch inference on that host. Neither the continuation
nor the tests ran torch inference there; the real-model test stays opt-in.

**Synthetic formant voices.** This is the material of the opt-in test: a
glottal pulse train through three formant resonators, with no recording.

| Pair | Cosine |
| --- | --- |
| Same voice (f0 110 Hz against 118 Hz, same tract) | 0.912 |
| Decoy: higher pitch and shorter tract | 0.574 |
| Decoy: breathy, longer tract | 0.477 |

**Fake-engine render evaluated end to end.** The render used an espeak-ng engine
inside the fake backend and three chunks of 3.4 to 4.3 s each.

| Scored against | Per-chunk SIM | wSIM | Reading |
| --- | --- | --- | --- |
| The voice's fixture reference (a 375 Hz sine) | 0.053 to 0.102 | 0.091 | the mismatch case |
| An espeak-ng reference, given as `--reference-voice` | 0.747 to 0.757 | 0.825 | the matched case |

What the numbers do and do not show:
- These are measurements of the plumbing and of the model's separation on
  synthetic speech.
- They do not calibrate `minSim`. That gate stays uncalibrated (`gates.calibrated`
  false) until the bench sets it against real decoys.
- A SIM number is not listening acceptance.

## Open

- **SIM per take in render** is not wired in v0, so every run is flagged
  `sim_not_measured`. Only `narrate_evaluate` scores SIM.
- **Real-voice SIM** on the bench renders belongs to the bench window. It runs on
  the Mac build host or in the GPU-host window, not on the CPU host.
- **UTMOS** has no registry entry.
