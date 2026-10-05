# Marked review video lane — October 5, 2026

Owner `media_latency`: `scripts/marked_video.py`, `tests/test_marked_video.py`,
this specification and a dated implementation receipt. Root owns full-take
execution, visual acceptance, recipes and publication. Authority: operator's
authorized parallel ten-hour goal and new evening marked-video request;
R-HOOK-CONVERGENCE-20261004, R-N11 owned worker cleanup and R-N13 durability.

Plan before implementation: validate existing source/master/export, DAG, flags
and generic markers by exact hashes. Inspect available FFmpeg subtitle/drawtext
filters and fonts. Select qualified phrase review or recurrence spans, compose
restrained amber uncertainty callouts and source timestamp labels, and render a
separate full-take MOV. Copy delivery AAC without another audio normalization.
Preserve native variable frame timestamps and verify decoded picture coverage,
audio packet payload/timing and all current input hashes. Test timestamp origin,
escaping, overlap, bounds, stale evidence rejection and a tiny real render.

Definition of done: fixed CLI `--run-dir DIR --selection
phrase-review|recurrences|all-review --output NEW_DIR`, default phrase-review.
Output is fresh under repository `artifacts/runs`; no newest scan or implicit
latest pointer. Fixed output files `marked-video.mov`, `callouts.ass`,
`selection.json` and `outcome.json`. Hypotheses say REVIEW / uncertain, never
MISTAKE or confirmed performance failure. Existing source, master, cleaned
video, report and latest pointer remain unchanged. Picture is explicitly
reencoded, audio is packet copied. Actual NLE import, listening and Logic
acceptance remain unverified. Root publishes only after full-take review.

Implemented CLI:

```
python3 scripts/marked_video.py --run-dir artifacts/runs/RUN --selection phrase-review --output artifacts/runs/RUN/marked-video/NEW
```

Both directories are rooted at this repository and restricted beneath
`artifacts/runs`; original lexical symlink components and traversal are rejected.
Output must be fresh. Compact stdout returns `marked_video`, `outcome_json`,
`selection_json`, `subtitles_ass`, status and counts. Failed late validation
retains its diagnostic preview and outcome with `failed_preview_preserving_inputs`;
it never returns a verified preview. Source/marker failures occur before output
creation. No prior master, video, report or latest pointer is rewritten.

The source, PCM master, exact delivery video, DAG, selected upstream artifacts,
flags and existing generic markers must match their receipts. Existing markers
are compared with a read-only reconstruction of the verified graph. The original
container start and the export's measured packet translation must establish
`source seconds = exported picture PTS + original container start`; unknown or
contradictory clocks abstain. Burned SOURCE ranges represent composed presentation
intervals. Original evidence spans and exact current flag IDs remain in
`selection.json`. ASS timestamps quantize to 10 ms; point markers receive a
disclosed one-second presentation dwell, not an asserted musical span.

`phrase-review` selects relative alignment/rate, motif timing and attack-pattern
reviews, possible recurrence and low-register riff candidates. `recurrences`
omits low-register riff regions. `all-review` includes navigation and texture
proxies with explicit proxy labels. Default selections are bounded to 128;
all-review and total input to 5000. Overlaps prioritize comparison reviews,
display at most two marker labels in one detail line below the uncertainty/source
range, and save every visible or suppressed flag span and duration. Adjacent
identical callouts coalesce. There is no confirmed wrong-note or missed-beat label.

The installed FFmpeg 8.1.2 exposes `ass`, `subtitles`, `drawtext` and `libx264`.
The renderer uses ASS with a bounded private snapshot of an existing Helvetica,
Arial or DejaVu Sans font; it installs nothing. H.264 picture uses CRF 18 and the
veryfast preset with two codec/filter threads. `-copyts`, passthrough frame mode,
the demuxer encoder timebase and exact reciprocal video timescale preserve the
native picture clock; the operator's original/clean picture remains separate.
Delivery AAC is packet-copied without a gain, denoise or normalization pass.

Verification independently decodes before/after picture frame timestamps/count,
last frame extent and geometry, and compares each AAC payload hash, rational
PTS/DTS/duration and padding metadata. It also hashes decoded native float PCM;
audio loudness is inherited only through exact verified packet/PCM identity.
Source and all current input hashes are checked after rendering. Physical capture
sync and listening acceptance remain false. Probes have 120-second deadlines,
render 600 seconds, each pipe 2 MiB. Direct media children inherit the controller
group so a wrapper group deadline includes them; internal failure cleanup
inspects the owned live child and signals only that child under R-N11.

Validation: thirteen tests cover selection, nonzero source origin, clipping,
centisecond carry, text escaping, overlap/suppression, point dwell, altered frame
or AAC rejection, freshness/symlink/traversal, source/marker identity failures,
bounded child output/deadlines and retained failed verification. Real generated
two-second VFR media with an original 2-second container offset retains 21 exact
decoded frames and all AAC/PCM evidence. Its toy callout was visually inspected;
these fixtures are controller/render evidence, not musician ground truth.
The real 150-second guitar delivery is read-only validated at 3621 decoded frames,
6503 AAC packets, frame extent 150.885 seconds and decoded PCM SHA256
`236c38376bca1c7e6af0ac6d11c298ecb34347d8dec5fd536cba11463c96e55d`.
Its default selection has 40 markers, 33 composed callouts and 157 exclusions;
full actual rendering and review remain root's acceptance lane.

Primary references: [FFmpeg stream copy and clock options](https://ffmpeg.org/ffmpeg.html#Streamcopy),
[video sync and encoder timebase](https://ffmpeg.org/ffmpeg.html#Advanced-options)
and [ASS filter](https://ffmpeg.org/ffmpeg-filters.html#ass).
Documentation establishes supported options; runtime before/after measurements
establish this preview's timing and audio preservation.
