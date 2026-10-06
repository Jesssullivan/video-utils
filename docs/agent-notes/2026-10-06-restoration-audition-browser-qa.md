# Restoration audition browser QA

Authority: root's explicit bounded local audition QA lane relayed by the audio
owner, active operator restoration iteration; R-HOOK-CONVERGENCE-20261004,
R-N11/R-N13 and repository AGENTS.md. Owner `/root/repo_patterns` writes only
this dated receipt and ignored `artifacts/restoration-audition-browser-qa-20261006T0445/`.
No public server, host/user browser-profile edits, audio/DSP regeneration,
inference, analysis adoption or selected-master changes occurred.

Initially inspected frozen0430 HTML00317c50/auditionb6fdb976. All six player
metadata loaded; final layout/actions paused when the audio owner supplied a
new FULLER acceptance page. That historical initial evidence is preserved as
`0430-initial-browser-evidence.json`; no0430 artifact was overwritten.

Final tested page:
`artifacts/experiments/restoration-audition-20261006T0438/index.html`, SHA256
`3e4acad986239fca1224c7b7c7805e76ab38b34bd2ea644c4a7e7f7b9832f10b`.
Frozen `audition.json` SHA256
`da0514e6884a576cb752d4fb1dfe1b803dc624613b052c3ac35b36bc75b14b03`;
`listening-acceptance.json` SHA256
`0f8d3dbff43e8f8c2bdaed94856d697b94f3de9cf78cf5f72a0e6ee982578e92`.
The successor changes acceptance text only; the same six assets and player JS
remain. The manifest's pending-QA field stays historical; this external receipt
records completed browser evidence.

## Actual checks

| Check | Result |
| --- | --- |
| Desktop1440×900 | Document/client width1440; zero horizontal element overflow |
| Narrow390×844 | Document/client width390; zero horizontal element overflow |
| Labels/actions |16px labels/buttons and20px candidate headings; wrapped labels readable |
| Six initial players | Native controls enabled; paused at unity volume; autoplay false |
| Three WAV players | Browser duration150.961111s; decode readiness4; no media errors |
| Three MOV players | Browser duration150.960998s;1620×1080; readiness4; no media errors |
| Shared slider |0.37 applied to all six players |
| Shared mute | Muting one native player synchronizes all six; all playback explicitly muted |
| Common114s seek | All six at114.0s, paused, seeking complete |
| Explicit play buttons | Each of six advances from114s; only chosen player active; others paused |
| Common149s tail seek | All six at149.0s, paused, seeking complete |
| NR10 arrangement link | HTTP HEAD200; explicitly NR10, distinct from accepted FULLER audio |
| Diagnostics | Empty console/page-error lists; no observed media errors |

Actual muted advances: NR8 audio0.243333s/video0.703171s; NR10 audio0.162567s/
video0.157208s; FULLER audio0.125651s/video0.483709s. These establish browser
playback clocks and exclusive playback, not acoustic synchronization or tone.
Final screenshot frames show all three videos decoded at114s, paused and muted.
Both full-page screenshots were inspected visually. Candidate labels, source-time
buttons, controls, download links, tradeoff paragraphs and evidence limits fit
and remain legible. Full-page image height is longer than viewport height;
layout measurements were taken at the specified viewport dimensions.

The page correctly records only root-relayed exact user QuickTime feedback
“sounds excellent!  great work!” for FULLER, with NR8/NR10 still comparison
candidates. It retains source-bound exact asset identities and false master
adoption/model accuracy/other-candidate acceptance. Its1.64dB deep-band and
5.55/5.33dB quiet-mixture tradeoffs remain visible; cleanup measurements are not
promoted to isolated fan or guitar gains. This browser lane performed no audible
listening; operator listening approval comes from the separate acceptance
receipt, not these muted checks. Physical-device/Safari behavior remains untested.

Ignored evidence:

- `desktop-1440x900.png` SHA819d96700d7edf3c4102bd786a62780818186c9cf536785976e52d102de37798.
- `mobile-390x844.png` SHA96e36be9654fa8406669ab36b1a6e994c8e7f9d8c8ef89e110f166cf71eb22ec.
- `browser-evidence.json` SHA33f869aae8fc2e4ad21fa99de3a7147b86e1e5c6efa8d1e1abee90c8c65a7cf9.
- Historical `0430-initial-browser-evidence.json` SHAa917452f08e2ba0fefaf2aba6a07254e88385f40346460aa26e7ce8fcc285e00.
- `preservation-cleanup.json` SHA7f0e0b678650b470f67ceabb39bff5a2d9ccc5bee0bf7aca828240b882ac2802.

## Process ownership and cleanup

Inspected available node_repl tool execution instructions, then reused existing
Playwright core1.62.1 by explicit runtime package path; no installation. Owned
headless Chrome154.0.8037.98 PID15971 used a new temporary profile,
`--mute-audio`, two-renderer ceiling and disabled background updates/networking.
The context allowed only127.0.0.1 requests. Exact browser argv is recorded in
`browser-owner.json`; no existing user Chrome profile/session was attached.

Owned read-only range server exact argv:
`python3 artifacts/restoration-audition-browser-qa-20261006T0445/serve.py`,
PID15824, ephemeral127.0.0.1:57409, scoped to repository `artifacts` for existing
relative links. It refuses symlink/out-of-root paths, directory listing and
writes. `server.json` records authority, PID, argv and served root.

Immediately before closing, live ps confirmed both exact task argv identities;
Chrome object PID/argv/live status additionally matched its ownership receipt.
Closed only the owned context/browser/server; Chrome exit0. Rechecked exact
Python server argv before signalling only that owned PID with SIGINT; server
exit0. Postchecks found both PIDs absent, loopback connection refused(errno61),
and the unique temporary profile removed. No other browser/server was signalled.

All11 checked target hashes remain identical: two0430 metadata files, six shared
WAV/MOV assets, and three0438 metadata files. The page/source/default/latest/
selected-master artifacts were not written by this lane. No must-fix found.

Receipt: `repo_patterns | owned server15824/argv/port57409 and Chrome15971/fresh
profile only | completed root-authorized local audition QA | R-N11/R-N13,
R-HOOK-CONVERGENCE-20261004 | ownership/live checks before close | browser0,
server0,PIDs absent,port closed,profile removed;11 hashes unchanged;0438
browser QA PASS, no audible acceptance or master adoption by this lane`.
