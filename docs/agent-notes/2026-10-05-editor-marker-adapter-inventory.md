# Editor marker adapter inventory and design receipt

Actor: `resolve_marker_sources`. Recorded October 5, 2026, approximately
23:58 UTC. Authority: operator-authorized parallel week design;
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. Parent integration: root.

Owned outputs: [adapter lane specification](../spec/EDITOR_MARKER_ADAPTER_LANE.md)
and this receipt only. Base checkout observed at
`eb378bd33e6c1ab408245e58f93430a495efbf6b`; shared main already contained other
agents' dirty work, preserved by this lane. No commits or publication performed.

## Read-only app and SDK inventory

Inspected directory entries in `/Applications`, `/Applications/Nix Apps`,
`/Users/jess/Applications`, its `Home Manager Apps` link, and
`Chrome Apps.localized`. No Final Cut Pro or Resolve app was listed. Exact
checks also found these paths absent:

```text
/Applications/Final Cut Pro.app
/Applications/Final Cut Pro Trial.app
/Applications/DaVinci Resolve.app
/Applications/DaVinci Resolve/DaVinci Resolve.app
/Library/Application Support/Blackmagic Design
/Users/jess/Library/Application Support/Blackmagic Design
/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting
/Library/Application Support/Blackmagic Design/Developer/Scripting
/Users/jess/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting
```

A scoped read-only Spotlight query for `com.apple.FinalCut` and
`com.blackmagic-design.DaVinciResolve` returned no matches. This is evidence
limited to checked paths and available Spotlight metadata; relocated,
unindexed or differently identified installations were not excluded. No app
version, build, edition or bundled current marker SDK was available to read.
No app was launched, connected, installed, registered or configured.

## Actual source-bound inputs inspected

Run: `artifacts/runs/20261005T232741Z-2b5dc43fd009`.
Original source SHA-256:
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.

| Input | SHA-256 | Read-only observation |
| --- | --- | --- |
| `markers.json` | `b2d2cf4aa6ed18b489815c7f9a6ccc75e5ecd82b372a561bf3627fa7b3b13a84` | 180 generic source-time markers |
| `manifest.json` | `4a75b4e352075114a7b6026c74acab3ab6c64eedddd52fc2b8514adfed80549c` | Existing restoration manifest inspected |
| `marked-preview/selection.json` | `915990d487466e9f9adcd571ad960df94ba94af0e07c6c5b4b99fd3b1eaef462` | 24 selected, 156 excluded, 25 composed callouts |
| `marked-preview/outcome.json` | `48c4d60759a0b328ec7975c2d4eff455934cd2ddf5a8ed6efcabcd909a91bac2` | Existing rendered outcome inspected; no rerender |

The [actual visual receipt](2026-10-05-marked-video-actual-visual.md) and its JSON
record decoded 3,621 VFR frames, preserved PTS from zero through video extent
150.885 s, mono 44.1 kHz delivery audio preservation, and six entirely suppressed
selected observations. This lane inspected those receipts rather than repeating
the full frame scan or claiming independent playback/listening. The original
source uses a `1/600` video time base and nominal `24/1`, with average
`108930/4549`; editor frame mapping remains unverified.

## Primary-source check and result

Official Apple timing, annotation and DTD pages were rechecked via browser and
their offered Markdown endpoints. Browser retrieval of Markdown was unsupported;
bounded Python HTTP responses were read in memory without writing downloads.
They establish rational seconds, containing-grid timing cautions, point markers
with one video-frame XML duration, and DTD 1.10 validity distinct from import
success. Sources are linked in the owned specification.

Earlier delegated read-only Blackmagic research established historical UI
source/range-marker semantics and staff guidance to installed scripting docs;
it did not establish a current manufacturer's Python marker contract. Large
Resolve 20/21 PDFs exceeded browser retrieval limits; no manuals or SDKs were
downloaded. Current app/SDK inventory leaves that contract unavailable.

Verification: documentation local links checked, syntax/diff checked, actual
marker/selection counts and listed input hashes read in memory. Future adapter
tests are specified but not executed because no adapter was implemented.

`resolve_marker_sources | two root-assigned documentation files; read-only local
app/SDK and run metadata | define next-week source-to-editor dry-run behavior
| R-HOOK-CONVERGENCE-20261004 R-N12/R-N13; operator parallel feature design
| generic markers and source-timed VFR preview exist; native editor contract
unverified | bounded inventory and decision-complete design recorded; native
implementation, calibration and app import remain pending`

No media files, shared specifications, scripts, recipes, project/library state,
host settings, SDK/model artifacts, or sibling repositories were changed.
