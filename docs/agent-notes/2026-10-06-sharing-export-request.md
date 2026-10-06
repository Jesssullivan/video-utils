# Repeatable small sharing exports

Operator request, verbatim:

> compressed audio, complressd / fixed resolution video suitable for sharin gwih minimalal file size is wirj adding a just recipe for explort operations

This extends the approved candidate's Desktop-export request with a reusable
repository operation. Root assigns `scripts/share_export.py` and its own tests/
spec to rhythm_analysis; typed tool30 integration to tool_hooks; the matching
media-share-export skill to tool_skills; independent refusal/timing review to
release_review. Root owns just recipes, README, actual delivery and publication.

The existing approved full-quality movie and master remain unchanged. The first
Desktop attempt used HEVC medium and copied AAC; it hit its encode deadline and
was not published. A fresh veryfast attempt is running with the same 720-height
VFR and audio-copy gates. Its qualified compressed picture may be reused for
the new 96 kbps AAC export without another video encode. The first result and
failure remain evidence rather than being overwritten.

The reusable operation should expose named, bounded size/quality knobs instead
of arbitrary FFmpeg filters: height, codec, CRF, audio bitrate and deadline.
Default is HEVC/hvc1, 720-height with preserved aspect ratio/no upscaling,
veryfast CRF26, AAC96 and faststart. H264 is a compatibility option; explicit
video-copy mode requires an already suitable height. Preserve sample rate and
channels, record lossy audio compression, verify output timing and encoded peak,
and publish only to a fresh destination with original identity intact.

Source, generated integration, actual sharing export, compressed text inspection
and operator listening remain separate evidence. This task adds no authority to
modify the accepted master or to label review candidates as proven mistakes.

Authority: operator's explicit export and recipe requests; repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004 / R-N11 / R-N12 / R-N13.

Empirical default update before tool admission: the second HEVC veryfast attempt
also reached its 500-second encode bound. Root released a separate H264 veryfast
CRF27 attempt and changed the reusable default to H264/CRF27. HEVC remains an
explicit option; this records behavior of the installed build on this take, not
a universal codec-performance comparison. All other planned controls remain.
