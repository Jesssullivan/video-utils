# Low-register audition: owned browser verification

Authority: root's named local audition QA lane in the operator-authorized active
parallel goal; repository AGENTS.md, R-HOOK-CONVERGENCE-20261004 / R-N11 / R-N13.
Owner `/root/repo_patterns` owns this receipt and ignored
`artifacts/audition-browser-qa-20261006T0140/` only. Existing audition/master/source/
DSP/default/latest files and root documentation are outside the write scope.

The audio owner explicitly froze
`artifacts/experiments/low-register-actual-diagnostic/audition-20261006T0128/`:
HTML SHA256 `f50a07fc64e9190d6c2660bcd8693c99ff627b347274526043883ee1c9814545`;
audition manifest SHA256
`1bfd585883b153bf010f25fff0f11a7941641dfe3916285aedc0ee40a32eafdb`.
Verified all nine source/processed/residue WAV hashes and native PCM24headers:
44.1kHz mono,441,000frames,10seconds each. The manifest's pending browser-QA
field stays historical and immutable; this external receipt records actual QA.

## Actual visual and browser results

Playwright core1.62.1 was found in the existing Codex runtime dependency tree;
no package/browser/model installation occurred. The available node_repl tool's
actual execution instructions were inspected first. Its standard `playwright`
import was unavailable, so Node's `createRequire` loaded that installed
`playwright-core` by its explicit absolute package path. It launched only an
owned headless Google Chrome154.0.8037.98 with a fresh temporary profile and
global `--mute-audio`, not the user's existing Chrome session/profile.

| Check | Actual result |
| --- | --- |
| Desktop viewport |1440×900; client/document/visual widths1440; no painted text overflow |
| Narrow viewport |390×844; client/document/visual widths390; no painted text overflow |
| Expanded timing/evidence |Open in both screenshots; hashes and captions wrap inside viewport |
| All nine players |Each duration10seconds, readyState4, null media error, initially paused/unmuted at volume1 |
| Shared volume control |Slider input0.37 updates all nine actual player volumes to0.37 |
| Muted actual playback |Original player advances0.997585seconds; muted=true, one player active, null media error |
| Full marked-video link |HTTP HEAD200; browser media duration150.960998s,1620×1080,readyState4,null error |
| Browser diagnostics |No console messages, page exceptions or observed player errors |

Both full-page screenshots were inspected visually: headings, original/processed/
residue labels, shared level control, uncertain-edge notice, download links and
provenance text are legible; every player label uses16px type. The390px layout
stacks the processed/residue controls with332px label/player content widths.
The desktop layout uses paired players. The uncertainty captions remain explicit:
fan/guitar overlap, residue containing possible music, unboosted residues,
unsupported edges, no preferred winner and no accepted replacement master.

Screenshot PNG dimensions exceed viewport heights because they capture the
full page; the layout was measured at the requested viewport sizes. This proves
Chrome rendering at those dimensions, not physical-device/Safari acceptance.

Ignored evidence and identities:

- `mobile-390x844.png` (390×3480), SHA256
  `4e9aad01892c0d81a5ff9b3d84380d52157d04a67de68ff54f78b2005f623303`.
- `desktop-1440x900.png` (1440×2193), SHA256
  `be0de1addb69badb41fb73ee4de8137ee4cb9357f833b288b2e41d6d08851a1f`.
- `browser-evidence.json`, SHA256
  `7c2300849780d3edac7fefd1a8c86fd62dbcd005ac563f804f6800bed3ba113f`;
  contains all nine media states, label/box/text metrics, shared volume values,
  muted playback clocks, linked-video headers/metadata and browser diagnostics.
- `preservation-cleanup.json`, SHA256
  `62a2c552d230e3d791a62f7a7687ad8dda8dece31030df39a5b90494c5264b05`.

No page/source correction was necessary. Playback was explicitly muted and the
browser also globally disabled audio output. No audible listening, tone/musical
transparency acceptance, preferred setting, new DSP or master/default adoption
is established by these checks.

## Owned server/browser and actual cleanup

Started only the read-only range-capable proof server
`python3 artifacts/audition-browser-qa-20261006T0140/serve.py`, PID30487,
bound to ephemeral `127.0.0.1:56446`. Its served root is the local `artifacts`
directory so the existing relative full marked-video link resolves. It rejects
paths outside that root, symlink components, directory listing and writes.
`server.json` records exact resolved argv, PID, served root and authority.

Playwright launched owned Chrome PID31493. Its exact argv and live startup
command are saved in `browser-owner.json`; its unique profile was
`/var/folders/z6/7m3zpx6j3x982j_fzwg1lppw0000gn/T/playwright_chromiumdev_profile-2qykvp`.
The browser had `--mute-audio`, a two-renderer ceiling and disabled background
networking/component updates. The page context allowed only loopback requests.
The actual browser PID/profile identity was checked immediately before closing
the owned context/browser/server objects; Chrome exited0 and its temporary
profile was removed by the owned launcher.

Immediately before server termination, `ps` verified PID30487 still executing
the exact task-specific server script. Only that PID received SIGINT; the
server caught it, closed its listener and exited0. Subsequent independent `ps`
checks found neither owned PID live, and a socket connection to the previously
owned port was refused. No user browser process/session or host configuration
was changed or signalled. Exact process receipts are in
`browser-cleanup.json` and `server-cleanup.json` under the ignored evidence root.

Pre/post hashes of all12target files are identical: HTML, audition manifest,
nine WAVs and the linked155,215,112-byte marked video. This lane made no writes
to source/DSP/default/latest/master files. No diagnostic capture or audio export
was rerun.

Receipt: `repo_patterns | own Chrome PID31493/profile and loopback server
PID30487/script only | read-only audition browser QA completed | R-N11/R-N13,
R-HOOK-CONVERGENCE-20261004 | exact live PID/argv/profile verified before close |
Chrome0/server0, both PIDs absent, listener closed, temporary profile removed;
12target file hashes preserved, browser QA PASS, listening acceptance unknown`.
