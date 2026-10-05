# Nineteen-tool source and calibrated demo checkpoint

Authority: operator implementation, parallel-work and ten-hour goal requests;
R-HOOK-CONVERGENCE-20261004, R-N11/R-N12/R-N13. Root owns integration.

The prompt archive and TEN_HOUR_PLAN reassert the user scope durably. The active
goal was created at20:49:34UTC October5 and has a planned ten-hour horizon ending
06:49:34UTC October6. This checkpoint does not close that goal.

## Actual local demo

Run `artifacts/runs/20261005T211103Z-c6d0bac2fcd2` uses the unchanged Documents
recording SHA256 a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6.
The original 44.1kHz mono decode has6,657,385samples. Conservatively restored
master measures−18.01LUFS/−1.50dBTP. The final decodedAAC video measures
−18.07LUFS/−1.56dBTP after a bounded−0.06dB feed adjustment. Initial−1.49dBTP
export is preserved in `export-revisions/initial-unreviewed`. Picture packet
payload/timestamps match all3631source packets. Physical capture A/V sync is
unverified; the measured1102sample FFT-denoiser delay is calibrated and
compensated, with rate, channels, length and tail preserved.

Automatic discovery produces48candidate regions,14recurrence pairs and186
review/navigation flags. Sparse-DTW comparison adds11hypotheses across14pairs;
these are not confirmed mistakes. Detection-only click analysis finds219
candidates; identity is unverified and audio is unmodified. Pitch analysis
samples20seconds across the take including its ending (13.25%coverage):420
voiced branch hypotheses and2084abstentions, not unique notes. Meter remains
unknown; tonal tonic/mode remain null. No model weights are downloaded.

## Local source verification

Final integrated suite:219/219PASS in160.966seconds, without skips, using the
locked analysis interpreter and explicit FFmpeg/FFprobe. Separate MCP target
checks:37/37PASS; all19typed tools, exact19skill prompt bodies and19skill
validations independently verified. Behavior covers32Hz preservation, low
notes/missing fundamentals, legato, ambiguity, strict JSON, bounded workers,
provenance changes, immutable results, AAC peak repair, and annotations.

Root `just au-spike-check` passes isolated ABI/Swift lifecycle/render checks.
Root `just au-automation-check` passes release and ASan/UBSan behavior checks
plus direct native runtime-reference audits. The observed10,000-block local
run has p95.958microseconds/max23microseconds and0nominal deadline overruns;
this scheduling sample is not a real-time or host guarantee.1000render calls
record0C++new calls. No AU package, registration, auval, Logic load, audio
device, editor import or listening acceptance is claimed.

Private GitHub source publication and current hosted CI are recorded separately
below after live readback. Original media and derivatives remain ignored.

Hosted repair run37373960394 at9883069 ended overall failure; its single offline
job was cancelled with no steps/logs. GitHub annotation reports no hosted runner
was acquired after repeated attempts; this is not a source-test
failure or a hosted pass. Root's local219-test result is separate evidence.

Process receipt: root | pid79901,parent79889,own live gitleaks dir invocation
verified by ps | directory scan includes regenerable private artifacts; replace
with bounded staged-source scan | R-N11/R-N12/R-N13 | running | SIGTERM sent only
to inspected owned process. Staged-source scan found no leaks (611,529bytes).
