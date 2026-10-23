# Narrate bench host-process runner (2026-10-23, lane E6)

Authority: operator ruling of 2026-10-23 (TIN-5770): the first bench window runs as a host process on the GPU
host, today, under nice 19, `ionice -c3` and `systemd-run --user --scope -p MemoryMax=14G`, without root, without
touching the card's device node, with VRAM under 12 GB, in 30 minutes or less. Bench plan:
[`2026-10-22-narrate-bench-plan.md`](2026-10-22-narrate-bench-plan.md) (Revision 2 records what this runner
changes). R-HOOK-CONVERGENCE-20261004: R-N11 (the window takes no Lease itself; the lease holder starts it with its
own holder id), R-N13 (this receipt).

**State: source-checked and fake-tested; not run on the GPU host.** No model ran on any host for this lane. The
CLI invocations come from reading the pinned sources, not from a live run.

## Files

| File | Runs on | Role |
|---|---|---|
| `narrate/bench/prepare.py`, `chunks-v1.json` | dev shell | the fixed chunk list; `just narrate-bench-chunks --check` |
| `narrate/bench/host_run.py` | GPU host, Python 3.9+, stdlib | `verify`, `run` one arm, `vram`, `summarize` |
| `narrate/bench/run-bench.sh` | GPU host | the window: scope, checks, arm order, deadlines, receipt |
| `narrate/bench/host-job.json` | GPU host | arms, inputs and pinned weight sha256 values; paths from `${...}` |
| `narrate/bench/score.py`, `just narrate-bench-score` | dev shell | pull back and score |
| `tests/test_narrate_bench_host.py`, `tests/support/narrate_bench_fake_engine.py` | CI | fake-binary tests |

No voice is tracked. The job names a private voice registry file (`voices_file`, path and sha256 from the private
`bench.env`) that maps voice ids to a reference clip and its verified transcript, each hash-bound; the tests use a
synthetic fixture voice.

## Invocations read from the pinned sources

- **A2-gpu-alt, qwentts.cpp `5916bf7c`** (`tools/qwen-tts.cpp`): `qwen-tts --model <talker> --codec <tokenizer>
  --device <name> --lang English --format wav16 --seed N --ref-wav <clip> --ref-text <transcript file>
  --stream-by-line -o -`, chunk text on stdin, one line per chunk. `--ref-wav` with `--ref-text` is ICL cloning
  (the speaker embedding plus the reference's codec codes and transcript); without `--ref-text` it is x-vector
  only. Line mode keeps the model loaded and writes one 44-byte WAV header (placeholder sizes) before each line's
  PCM (`src/audio-io.h` `wav_stream_write_header`); host_run.py splits stdout on that header. The seed defaults
  to -1 (random), so every pass passes one. `tts-server` is not used: at this pin its speech route takes no
  reference; cloning there is a separate voice registration.
- **A1-gpu, audio.cpp `47c2756e`** (`docs/models/ming3_tts.md`, `app/cli/request.cpp`): `audiocpp_cli --task clon
  --family ming3_tts --model <gguf> --backend vulkan --device 0 --request-sequence requests.json --out-dir <dir>
  --out-format pcm16 --metrics`; each request carries `text`, `voice_ref`, `reference_text`, `seed` and options
  `language=en`, `raw_text=true` (our chunking, not the engine's). Output `<out-dir>/<id>.wav` per request, and
  `[TIMING] request.<id>.wall_ms` on stdout. Ming's generator stops when prompt plus output reach 512 positions
  (`src/models/ming3_tts/generator.cpp`); see Revision 2 for the fallback. Decoy 2: `--task tts` with options
  `template_name=ip`, `voice_id=UK_George`, no reference.
- **A3-gpu, audio.cpp `47c2756e`** (`docs/tts.md`, VoxCPM2): the same request sequence with `--family voxcpm2`;
  `voice_ref` plus `reference_text` is the "ultimate clone". `voxcpm2.mem_saver` is already true by default at
  this pin, so the plan's "only if over the bar" switch has nothing to turn on. `retry_badcase` stays at its
  default (true, up to 3 attempts) and is part of the measured wall time.
- Both runtimes read 16- and 24-bit PCM WAV references at any rate (`src/framework/audio/wav_reader.cpp`,
  qwentts `src/audio-io.h`), so the clips are used as stored.
- Device: every engine gets `VK_DRIVER_FILES` (and `VK_ICD_FILENAMES`) naming the RADV ICD only, so the Vulkan
  loader cannot offer the host's llvmpipe device; qwen-tts must be given an explicit `--device`, and an arm whose
  smoke does not raise VRAM in use by 256 MiB over the idle baseline stops as `no_gpu_use`.

## Guards as implemented (review fix round, 2026-10-23)

- **Entry.** `run-bench.sh HOLDER` refuses root, a missing or malformed holder, an existing `runs/<holder>`, and any
  `bench.env` line outside the allowed keys (it is parsed, never sourced). It hashes itself, `job/host_run.py` and
  `job/host-job.json` against the caller's `NARRATE_BENCH_EXPECT_RUN_BENCH`, `_HOST_RUN` and `_JOB` before and again
  inside the scope; the window receipt records expected and measured values.
- **Scope.** `systemd-run --user --scope -p MemoryMax=14G -p MemorySwapMax=0 -p CPUQuota=200%
  -p RuntimeMaxSec=1680` under `nice -n 19 ionice -c3`. Inside, the script checks that `/proc/self/cgroup` is the
  unit's scope and that `memory.max`, `memory.swap.max` and `cpu.max` read 15032385536, 0 and `200000 100000`,
  and records them; otherwise it refuses with a receipt. If the scope cannot be made, the outer stage writes a
  minimal receipt. Every exit prints `NARRATE-BENCH-DONE rc=N`.
- **Signals and leftovers.** HUP, TERM and INT stop the window (SIGPIPE ignored); host_run.py handles the same
  three, runs every engine in its own process group with `PR_SET_PDEATHSIG(SIGKILL)`, always reaps the whole group
  (SIGTERM, SIGKILL) and stops the window if a group survives. An EXIT trap kills anything left in the verified
  scope; the pids go to the receipt.
- **Stops.** Per arm: budget (480 s, capped at 1500 s from the window start), 120 s without output, a crash, no
  passing smoke, no GPU use, an unreadable VRAM sample. Per window: VRAM in use above 12,000,000,000 bytes (clamped
  in code; `vram.required` is always true), any process of the scope holding a `/dev/dri/cardN` descriptor
  (scanned every 0.2 s from `/proc/<pid>/fd`), an amdgpu reset or ring timeout in `journalctl -k -o cat` (host
  names are not read; readability is probed first), a surviving process group, or a signal.
- **Test mode.** Only `NARRATE_BENCH_TEST_MODE=1` from the caller (never `bench.env`) allows the test settings (no
  scope, another sysfs root, another device prefix, other arms or shorter limits); every receipt records it.
- **Scoring.** `score.py` refuses a destination inside any git work tree, refuses a receipt whose
  `chunks_sha256` is not the committed list, and flags a chunk WAV whose sha256 differs from its receipt.
  `/runs/` and `bench.env` are gitignored.

## Validation

- `python3 -m unittest tests.test_narrate_bench_host` in `systemd-run --user --scope -p MemoryMax=6G nice -n 19`:
  29 tests, a fake binary for both runtimes (with a forking variant) and a fake sysfs tree. Covers each stop rule
  above, SIGHUP, SIGTERM and SIGKILL of the runner and SIGHUP of the window with no engine left, the runner-hash,
  holder, bench.env, existing-output and scope refusals (a fake `systemd-run` on PATH), and the scorer's git-tree
  refusal.
- Before the fix round, run-bench.sh ran on the dev host inside a real user scope with the fake binary.
- Not done: no run under CPython 3.9 (syntax checked with `ast` at feature version 3.9 and ruff at py39); no run
  of any real model; whisper scoring not run.
