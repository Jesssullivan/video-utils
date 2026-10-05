# Source-time markers in Final Cut Pro and DaVinci Resolve

Primary-source research checked October 5, 2026. This is a compatibility design,
not evidence of an editor import. The existing generic JSON/CSV remains the
canonical interchange. See [the bounded spike](../spec/EDITOR_MARKER_SPIKE.md)
for implementation contracts and fixtures.

## Decisions supported by the documentation

| Question | Finding and adapter decision | Evidence boundary |
| --- | --- | --- |
| Can a Final Cut marker represent a phrase span? | Final Cut markers represent points; FCPXML represents each with one video-frame duration. Emit a START/END pair for a span and retain its exact interval in notes and the sidecar. | An arbitrary long XML marker duration is not proof of a visible range. [Apple annotation semantics](https://developer.apple.com/documentation/professional-video-applications/associating-ratings-keywords-markers-and-metadata-with-media) |
| Where does its timestamp belong? | Marker `start` follows the containing clip's local time, including its `start` origin. Apple's example places a marker at local 8 s in a clip starting at 5 s: 3 s into that clip. | Parent timeline placement additionally depends on clip `offset`; retiming needs a separate mapping. [Apple worked example](https://developer.apple.com/documentation/professional-video-applications/describing-final-cut-pro-items-in-fcpxml) |
| How should FCPXML time be encoded? | Use reduced rational seconds, with the chosen editor frame duration kept separate from source sample/PTS resolution. `offset`, `start`, and `duration` have distinct roles. | Apple warns that timing inconsistent with a containing timeline's frame grid can cause inserted gaps and warnings. [Apple timing attributes](https://developer.apple.com/documentation/professional-video-applications/timing-attributes) |
| Which XML version and container? | Version-bound fixtures can use the directly published DTD 1.10. A minimal `.fcpxmld` bundle contains `Info.fcpxml`; media need not be copied into this repository. | DTD 1.10 is a chosen fixture profile, not a claim about the latest schema or an installed application's support. [Apple DTD](https://developer.apple.com/documentation/professional-video-applications/document-type-definition), [Apple bundle reference](https://developer.apple.com/documentation/professional-video-applications/fcpxml-bundle-reference) |
| Does valid XML prove import works? | Validate against the exact selected DTD, then perform separate application validation. | Apple explicitly distinguishes structural validity from semantic import errors. [Apple DTD](https://developer.apple.com/documentation/professional-video-applications/document-type-definition) |
| Can XML convey review status? | DTD 1.10 provides `value`, `note`, `start`, optional `duration`, and optional `completed`; supplying `completed` makes a to-do item. | `completed=1` means the to-do is completed, not that a musical mistake is confirmed or a master accepted. Use ordinary markers until review semantics are explicitly mapped. [Apple DTD](https://developer.apple.com/documentation/professional-video-applications/document-type-definition) |
| Which Resolve marker target? | Source-clip markers match original-take annotations; select a specific `MediaPoolItem` for the future scripting adapter. Source, timeline-item, and timeline-ruler markers are distinct. | The manufacturer manual establishing these distinctions is historical. Current scripting behavior still needs the installed SDK and host proof. [Resolve 11 manual, Using Markers](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_11_Reference_Manual.pdf) |
| Does Resolve support visible ranges? | Manufacturer training demonstrates one-frame markers and extended frame ranges. Names and notes should carry separate concise and detailed information. | Training does not establish inclusive endpoints, accepted numeric types, current Python signatures, or collision behavior. [Resolve 17 training, Marking a Range of Frames](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-17-Beginners-Guide.pdf), [Resolve 16 training, marker fields](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-16-Beginners-Guide.pdf) |
| Is generic CSV a native Resolve import? | Keep it generic. Timeline-marker EDL export and ADR cue-list CSV import address different workflows. | Neither documents native import of our source-time review CSV. [Resolve 18 training](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-18-Beginners-Guide.pdf), [Resolve 17 Fairlight training, ADR cue lists](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-17-Fairlight-Audio-Post.pdf) |
| Where is the authoritative Resolve scripting contract? | Inspect the installed Help → Documentation → Developer → Scripting documentation for the actual version/build/edition. | Blackmagic staff's July 2024 edition-specific guidance is historical. The conventional macOS SDK directory was absent in this lane's read-only check; current marker signatures are unverified. [Blackmagic staff guidance](https://forum.blackmagicdesign.com/viewtopic.php?f=21&t=205175) |

The Blackmagic support index listed the Resolve 21.1 reference manual dated
September 8, 2026 during this research. That establishes a published manual, not
the locally installed version. The large current reference PDFs exceeded the
browser retrieval limit; they were not downloaded. Do not substitute community
SDK reproductions for a verified current manufacturer contract.
[Blackmagic support index](https://www.blackmagicdesign.com/support)

Apple's live marker guide offers a Final Cut Pro 12.4 version selector. Its
developer reference introduction still describes FCPXML 1.9, while its published
DTD page contains 1.10. These pages are useful for explicit version profiles;
their headings alone do not determine a current application's import support.
[Apple marker guide](https://support.apple.com/guide/final-cut-pro/intro-to-markers-ver397279dd/mac),
[Apple developer reference](https://developer.apple.com/documentation/professional-video-applications/fcpxml-reference)

## What the actual take establishes

The inspected source manifest has SHA-256
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
Its audio is mono AAC at 44,100 Hz. Audio and format duration are approximately
150.954059 s; video header duration is 150.905 s. The video metadata reports
average rate `108930/4549`, nominal rate `24/1`, and time base `1/600`.
All recorded stream/format start values are zero.

A read-only FFprobe decoded-frame scan, with JSON held in memory, measured:

| Observation | Result |
| --- | --- |
| Decoded frames with best-effort presentation timestamps | 3,621 |
| First/last presentation ticks | 0 / 90,506 at `1/600` s |
| Successive PTS steps | 24 ticks × 43; 25 ticks × 3,528; 26 ticks × 49 |
| Last reported frame duration | 25 ticks |
| Last PTS plus reported duration | `90531/600` s = 150.885 s |
| Audio extent minus that decoded video coverage | Approximately 69.059 ms |

This establishes variable decoded cadence: frame starts do not follow a uniform
24 fps grid. Header `nb_frames=3631` also differs from the observed decoded-frame
count. No cause of the discrepancy is inferred. The scan is FFmpeg's decoded
view, not an editor's interpretation of edit lists, tail handling or source
timecode. The final audio interval cannot silently acquire a video frame.

Using average rate as a timecode rate would assign inferred frame 3,600 to
approximately 150.339 s; a 24 fps grid assigns it to 150 s. Neither calculation
is a substitute for actual source PTS or a calibrated editor mapping.

## Timecode and musical uncertainty

Drop-frame changes displayed frame numbers, not media timing or samples. Apple's
29.97 example skips labels from `00:00:59:29` to `00:01:00:02`, with the exception
at minutes divisible by ten. Keep the exact rate, display mode, and displayed
origin separate. This take's approximately 23.95 average cadence does not justify
a drop-frame setting or an NTSC rate substitution.
[Apple TN2310](https://developer.apple.com/library/archive/technotes/tn2310/_index.html)

A phrase boundary, recurrence difference, possible rush or unclear riff is a
review hypothesis. Labels must preserve confidence, feature coverage and any
calibration uncertainty. Nine-string C1 fundamentals, distorted harmonics,
syncopation, sweeps and tapping make apparent attack boundaries ambiguous; a
marker is neither an identified note nor a confirmed performance error. Unknown
meter/tonic remains unknown. Frame snapping must not hide more precise audio
times or manufacture musical certainty.

## Research receipt

Authority: existing operator goal and R-HOOK-CONVERGENCE-20261004, R-N12/R-N13.
Owned lane: these two documentation files. Apple Markdown documentation was read
from official in-memory HTTP responses where browser rendering omitted its body;
the Resolve child lane used manufacturer sources and reported SDK access gaps.
Source inspection used the existing FFmpeg 8.1.2 store binary and emitted JSON
to stdout only. No media derivatives, editor installations, host configuration,
API writes, plugin repairs, imports, SDK/model downloads or source uploads were
performed. Source-only adapter design is complete; application acceptance is
pending separately.
