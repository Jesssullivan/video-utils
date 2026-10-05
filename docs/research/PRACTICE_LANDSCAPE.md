# Technical-guitar practice landscape

Primary documentation checked October 5, 2026 UTC and in the operator's
America/New_York session. Owner: `/root/plan_review`. This bounded comparison
covers eight adjacent products; it is not an exhaustive market survey or a
product benchmark. No account, installation, model download, microphone capture
or private-media upload was used.

There is substantial documented overlap with this project's practice workflow.
Moises combines performance video, stems, tempo and automatic sections;
Soundslice combines synchronized practice media, notation, stems and looping;
Guitar Pro supports custom nine-string notation. The proposed opportunity is
therefore a **working hypothesis**: a local, agent-assisted woodshedding workflow
for heavily distorted technical nine-string takes, preserving approximately
32 Hz content and giving source-timed, uncertainty-aware practice feedback.
The reviewed sources do not establish that this combination is universally
absent, nor do they establish any product's accuracy on this particular take.

## How to read the comparison

**Documented** means an official source describes the capability; it does not
mean we executed or independently verified it. **Unknown** means this pass did
not establish the capability or its quality. Documentation omission is not
evidence of absence. An explicit documented restriction is called out separately.
“Stem export” can mean rendering existing separate tracks or estimating sources
from a mixture; these are different operations. User-authored labels, tab
playback and tempo correction are different from detecting musical faults in a
captured performance. Open tuning metadata is different from recovering played
notes under distortion, polyphony and click overlap.

The comparison includes FOSS building blocks rather than treating all products
as interchangeable services. TuxGuitar's official site identifies LGPL licensing,
Sonic Visualiser's download page identifies GPL v2-or-later, Guitarix identifies
GPL v2, and Audacity identifies itself as open source. These are product-license
statements; any future code reuse needs a separate dependency/license review.
[TuxGuitar project](https://www.tuxguitar.app/index.html.en),
[Sonic Visualiser download](https://www.sonicvisualiser.org/download.html),
[Guitarix project](https://guitarix.org/),
[Audacity project](https://www.audacityteam.org/).

## Capture, playback and separation overlap

| Comparator and inspected scope | Audio/video | Stems and cleanup | Tempo, loops and practice |
| --- | --- | --- | --- |
| **Moises**, current unversioned feature/help pages | Mobile performance-video capture, existing-video upload, export/share documented | Instrument separation and mastering documented; recovered-stem fidelity unknown | BPM, smart metronome and automatic section loops documented |
| **Soundslice**, current unversioned help | Synchronized notation/tab with audio and video documented | Uploaded or automatically generated vocals/drums/bass/other stems; **MP3 recordings only**, explicitly excludes video stems | Pitch-preserving slowdown and loops; stem playback shares practice controls |
| **Guitar Pro 8**, versioned manual | Audio track synchronized to the score; captured-video practice workflow unknown in reviewed pages | Track mixing/focus is not evidence of automatic mixture separation | Loop, metronome, relative speed and progressive speed trainer; fixed tempo is explicitly unavailable with an audio track |
| **TuxGuitar 2.1.0**, current release plus development help | Multitrack tab/score playback and audio export; captured-video workflow unknown | Synthesized track export documented, not established mixture-source separation | Score tempo, metronome, marker navigation and loop/progressive-speed playback documented |
| **Sonic Visualiser 5.2.1** | Audio waveform/spectrogram analysis and synchronized annotation audition | Audio-region export and analysis-plugin ecosystem; automatic stems/cleanup quality unknown | Feature-extraction beat/pitch plugins, pitch-preserving time stretch and seamless comparison loops |
| **Guitarix 0.47.0** | Mono guitar input, processed amp/rack output and DAW routing | Amp/cabinet/effects, noise gate and neural amp modeling; modeling an amp is not separating a room recording | Guitar tone processing documented; practice-tempo/video workflow unknown |
| **Audacity 4.0.1**, with explicitly dated 3.x sources | Audio recording/editing; 4.x clip/label/loop behavior and per-track/label-region export | Noise-profile reduction/residue in development manual; older optional OpenVINO separation described separately | Automatic imported-loop tempo introduced in 3.5; current-version behavior requires a version-qualified check |
| **REAPER 7.82** | Multitrack audio and video decode/encode/process | Existing track/stem/region rendering, ReaFIR/ReaGate and plugin hosting; automatic mixture separation unknown here | Tempo/time-signature maps, rate/time stretch, markers/regions, looping and stretch markers are DAW mechanisms |

Sources and precise boundaries:

- Moises describes mobile-only capture, recording over a backing track or from
  scratch, existing-video upload, and camera-roll/social export. This overlaps
  the desired shareable practice-video product directly. The documentation also
  distinguishes headphone requirements for backing-track capture. These are
  vendor capability statements, not proof of room-capture or nine-string
  performance accuracy. [Official video documentation](https://moises.ai/features/video-recording/).
  Its section feature advertises automatic segment detection, renaming and
  downbeat-aligned looping, with BPM and instrument separation alongside it.
  Semantic sections are not demonstrated technical-riff correctness labels.
  [Official song-parts page](https://moises.ai/features/song-parts/),
  [feature catalog](https://moises.ai/features/).
- Soundslice's synchronized audio/video notation and loop/slowdown controls are
  a substantial practice competitor. Its stem help explicitly supports MP3
  recordings, aligned uploaded stems and automatic four-category estimates;
  video stems are expressly unsupported by this feature. [Player overview](https://www.soundslice.com/help/en/player/basic/99/overview/),
  [stem documentation](https://www.soundslice.com/help/en/creating/recordings/320/multitrack-stems/).
- Guitar Pro's inspected documentation is **version 8**, not an independently
  established exact installed patch release. It documents backing audio,
  notation and speed training. An audio track prevents the fixed-tempo option;
  relative speed remains a distinct control. [Feature overview](https://www.guitar-pro.com/c/14-guitar-pro-features),
  [version-8 playback speed](https://www.guitar-pro.com/docs/gp8/audio/playback/speed).
- TuxGuitar's release list identifies **2.1.0** as latest stable and a separate
  October 5 development prerelease. The inspected help is marked development
  documentation, so it is not silently attributed to every stable build.
  It describes score markers, loops and progressive speed. [Official releases](https://github.com/helge17/tuxguitar/releases),
  [markers/player help](https://www.tuxguitar.app/files/devel/desktop/help/detail_markers_player.html),
  [sound/export help](https://www.tuxguitar.app/files/devel/desktop/help/tools_sound.html).
- Sonic Visualiser explicitly covers editable points/segments, automated Vamp
  beat/pitch annotations, comparative loops and annotation export. Its download
  page identifies **5.2.1** and says no analysis plugins ship with the application;
  plugin availability/accuracy is a separate question. [Official features](https://www.sonicvisualiser.org/features.html),
  [current download scope](https://www.sonicvisualiser.org/download.html).
- Guitarix documents guitar-first amp/rack processing and JACK/DAW/LV2 use.
  **0.47.0** is the latest release listed during this pass, including neural amp
  model/IR use and tuner changes. Neither neural amp simulation nor a noise gate
  establishes source extraction or automatic practice grading. [Official project](https://guitarix.org/),
  [release 0.47.0](https://github.com/brummer10/guitarix/releases/tag/V0.47.0).
- Audacity's current changelog lists **4.0.1, September 30, 2026**. Its 4.0
  migration explicitly lists Macro Manager, scripting pipe, Vamp/LADSPA hosting
  and play-at-speed among features not present at that release. Do not transfer
  3.x automation assumptions to 4.x. [Current official changelog](https://www.audacityteam.org/changelog/).
  Automatic loop tempo is documented in the April 2024 **3.5** announcement.
  Noise-profile reduction/residue is described in the development manual, with
  warnings about damage to wanted signal; current UI/version compatibility was
  not exercised. Optional OpenVINO separation in the older vendor announcement
  is not proof of current 4.x/platform compatibility. [3.5 announcement](https://www.audacityteam.org/blog/audacity-3-5/),
  [noise-reduction manual](https://manual.audacityteam.org/man/noise_reduction.html),
  [OpenVINO announcement](https://www.audacityteam.org/blog/openvino-ai-effects/).
- REAPER's download page lists **7.82, October 4, 2026**. Official capabilities
  include programmable video, audio effects, stretch/pitch engines and plugin
  hosting. Rendered project stems are not automatically recovered original
  sources. [Current version](https://www.reaper.fm/download.php),
  [official capabilities](https://www.reaper.fm/about.php).

## Performance review, automation and the instrument

| Comparator | Practice/fault-marker boundary | Agent/API boundary | Custom nine-string / approximately 32 Hz boundary |
| --- | --- | --- | --- |
| Moises | Automatic song sections documented; missed-beat/note review on this instrument unknown | First-party MCP practice agent unknown in reviewed sources | Generic guitar features do not establish this tuning or low-F0 accuracy |
| Soundslice | Synced notation/practice and stem audition documented; automatic captured-performance faults unknown | First-party MCP analysis/review loop unknown | **Generic nine-/ten-string presets and per-string custom tuning documented**; distorted low-F0 transcription accuracy unknown |
| Guitar Pro 8 | Score reference and speed trainer documented; arbitrary take fault inference unknown | First-party MCP capture-analysis loop unknown | **3–10 strings and per-string custom tuning documented**; score representation does not validate 32 Hz capture analysis |
| TuxGuitar | User-authored score markers and playback feedback are not inferred performance faults | Source/plugin extension available; first-party MCP loop unknown | Custom tunings documented; exact nine-string stable-build capability not established in this bounded pass |
| Sonic Visualiser | Manual/automatic feature annotation is genuine overlap; specialized missed-beat grading unknown | **Sonic Annotator CLI** supports batch feature/CSV extraction; MCP unknown | Frequency visualization/plugin analysis is not validated exact-string or low-F0 performance assessment |
| Guitarix | Guitar effects/tuner are related practice tools; source-timed fault review unknown | JACK/LV2 routing is audio integration; MCP unknown | Guitar-oriented processing documented; exact tuning registry/F0 accuracy unknown |
| Audacity | Labels/subtitle export and repair are annotation mechanisms, not musician-fault ground truth | Version-specific automation; 4.0 scripting-pipe omission explicit; MCP unknown | Generic audio editing does not establish validated custom-tuning note review |
| REAPER | Markers/regions/stretch tools can support human review; automatic correctness unknown | **ReaScript EEL2/Lua/Python and extensive API documented**; first-party MCP unknown | Configurable audio/plugin host, not evidence of a validated nine-string transcriber |

Soundslice's custom-tuning page includes generic nine-/ten-string presets and
individual string-pitch editing; paid-plan requirements apply to custom tuning.
Guitar Pro explicitly allows 3–10 strings. This contradicts a claim that custom
nine-string support itself is absent from practice software. Neither source
demonstrates identifying a C1 fundamental in a highly distorted phone recording.
[Soundslice tuning](https://www.soundslice.com/help/en/creating/instruments/312/tunings/),
[Guitar Pro 8 tuning](https://www.guitar-pro.com/docs/gp8/score/track-settings/track-tuning).
TuxGuitar documents custom tunings but the exact stable-build string-count limit
was not established here. [Configuration help](https://www.tuxguitar.app/files/devel/desktop/help/tools_install_conf.html).

Sonic Annotator is a real programmable alternative for batch audio features and
CSV output; its own README warns against relying on changing default plugin
configurations in production. REAPER exposes scripts/actions/API suitable for
building local workflows. These are meaningful automation overlaps; neither
establishes a first-party MCP practice agent. Third-party MCP wrappers were not
enumerated, so their existence remains open. [Official Sonic Annotator source](https://github.com/sonic-visualiser/sonic-annotator),
[official ReaScript documentation](https://www.reaper.fm/sdk/reascript/reascript.php).

## Hypothesis to test next

The product should compete on the **complete practice loop and measured
usefulness**, not on claiming invention of denoising, stems, tempo, custom tuning,
looping or annotations. Test the narrower combination on explicit local takes:
heavily distorted nine-string C1 content; click/guitar overlap; fast palm-muted
subdivisions, odd groups, tapping/sweeps/legato; variable-frame-rate room video;
repeated phrases; and shareable cleaned clips with navigable review spans.

Compare preservation/listening, BPM half/double ambiguity, phrase boundary and
recurrence quality, false-positive review burden, and time needed to return to
practicing. Keep correct-note and missed-beat labels contingent on qualified
reference and timing evidence. Source separation from mono AAC remains an
estimate; an agent-controlled graph and a specialized tuning preset alone do
not establish better musical accuracy.

The next market-validation pass should add direct performance-feedback products
and vendor support questions, with separately authorized hands-on comparisons
on shareable fixtures. This eight-product documentation pass supports an
underserved-workflow hypothesis and clearly establishes feature overlap. It does
not prove market absence, purchase superiority, user demand or performance
accuracy, including for this repository's current candidates.
