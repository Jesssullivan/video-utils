# Fresh NR10 extended analysis

Root authorized extending the verified NR10 candidate
`artifacts/runs/20261006T034521Z-a0def0c43eac` with the existing qualified
workflow: `--existing-run`, `--features extended`, `--backend librosa`, explicit
`.venv/bin/python`, `--pitch-seconds 20`, supplied `--bpm 178`, and `--no-latest`.
No models, packages or presets were acquired. The original application-bound
manifest was first preserved exactly as `restoration-manifest.json` at SHA256
`a6c371ab36e1f50b850f167a42b010ffa7b923b32aca14f4bfd70fb24036077c`.

Actor `/root/media_latency` owned controller execution session 71529. Controller
`8e1ae85d…` imported unchanged `run_demo.py` and its exact CLI arguments,
allocated every stage only the remaining shared 900-second processing budget
minus cleanup reserve, and preserved the original per-stage new-session cleanup.
The controller had its own recorded PID/PGID/SID and absolute alarm. Input hash
and import preflight wall time precede this processing budget; it is not claimed
as a hard real-time bound on local filesystem calls. Numerical threads were two.

The workflow exited zero after 699.065 processing seconds. All 15 stages passed:
existing media/export were verified and the 13 fresh analysis/report stages
completed. Rhythm took 453.076 seconds, materially longer than the historical
run; that measured runtime is retained rather than substituting the earlier
estimate. All five exact optional selectors—clicks, pitch, meter, tonal and
comparisons—were verified by the current DAG. Exact invocation:
`demo-invocations/20261006T035857Z-1dfbe3b98567/receipt.json` beneath this run.
The controller receipt under
`artifacts/experiments/nr10-extended-analysis-20261006T0400/receipt.json`
has SHA256 `7650754467efc72a5f6d5ea55d977e28ca3e0de4bbbc76e10e0f86a59802e54a`.
The sibling dated JSON records all selectors, hashes and stage timings.

Fresh source-bound outputs are `analysis.json`, `phrases.json`,
`phrase-comparisons.json`, `dag.json`, `flags.json`, `markers.json`/CSV and
`report.html`. The graph produced 171 uncertain review/navigation flags:
112 four-pulse proxies, 44 texture regions, five automatic recurrences, three
possible low-register riffs, six relative recurrence-difference hypotheses and
one bright-ending texture candidate. These are not confirmed missed notes,
rushed beats, bars or intended phrase mistakes. The metronome prior is supplied;
no expected note score was passed to this analysis invocation.

pYIN covers 20 seconds in four distributed spans: 0–5,
48.6536875–53.6536875, 97.3074375–102.3074375 and
145.961125–150.961125 seconds. This is about 13.25 percent of the take, including
the ending, not full-song transcription. Its overlapping branches yielded 469
voiced hypotheses and 2035 abstained frames; octave, voicing, edge and intended
note ambiguity remain explicit.

Original/current master/latest, completed NR8, all NR10 native and delivery
media, application receipts and worker/context identities were checked unchanged.
No media rerender, latest promotion, master adoption or listening occurred.
Root steered the next preview to `clip_baseline`'s compact arrangement-aware
workflow; this lane did not launch a duplicate canonical marked render.

Status: fresh analysis complete, audition candidate unreviewed. Arrangement-aware
preview, its visual proof and root publication are separate owner work.
