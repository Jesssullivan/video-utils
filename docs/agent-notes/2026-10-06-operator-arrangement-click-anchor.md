# Operator arrangement: cached click and first-phrase anchor assessment

Actor `/root/meter_inference`; authority: root's explicit resumed bounded
read-only assignment under the operator's goal, repository AGENTS.md and R-N13.
Owned outputs are this note and the matching JSON receipt. No media decoding,
canonical analysis/reference mutation, marker edits or mistake grading occurred.

The operator's [durable arrangement prompt](2026-10-06-operator-arrangement-prompt.md)
and [source-bound expected fixture](../../program/demo-arrangement.json) supply
the mechanical-metronome start near5seconds, preceding windup, first musical
phrase around10–11seconds, approximately178 BPM and16 clicks per chorus phrase.
The404 intended musical clicks start at the first intended phrase, excluding
pre-phrase count-in. They are intended arrangement evidence, not an observed
metronome count or a precise source-time reference.

The [JSON receipt](2026-10-06-operator-arrangement-click-anchor.json), SHA256
`22700f59b1f4cafbf992838c30ebb0fb8e855a37971418805605c617a10748d3`,
records hashes before/after for the stronger run's existing analysis, click
artifact, manifest, source derivative, imported arrangement and exact prompt.
All remained unchanged. Its original recording identity is
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
Audio/source origin is0seconds. Numerical work used cached JSON only and
stdlib arithmetic, below the admitted60second limit; no numerical thread pool.

## Startup and first-phrase candidates

There is a cached broadband attack at **5.0025s**, followed by spectral-flux and
SuperFlux candidates at **5.040s**. These are compatible with the approximate
operator start but may include windup/startup or another transient. Their
identity and physical detector delay remain unknown. The next spectral event
at5.560s is0.520s later; subsequent events5.910,6.245,6.590,6.925 and7.270s
show much steadier spacing. A rigid global grid should not retroactively label
the entire startup as metronome clicks.

Within the operator's10–11second phrase-start bracket:

| Source-frame candidate | Spectral-flux candidate | SuperFlux candidate | Review status |
| --- | ---: | ---: | --- |
| 10.2775s | 10.315s | 10.320s | Possible first-phrase/clock anchor |
| 10.6275s | 10.655s | 10.660s | Possible first-phrase/clock anchor |
| 10.9775s | 10.990s | 10.995s | Possible first-phrase/clock anchor |

The source-frame candidates are cached broadband attacks. The middle candidate
also appears in the existing periodic high-frequency half-time candidates;
this extra periodic evidence does not establish that it is the first downbeat.
Spectral event correspondence is comparative timing evidence, not calibrated
onset latency or an intended note. No uncertainty probability or precise error
bound is available. Preserve all three as review candidates until the actual
first musical attack and an adjacent metronome click are independently reviewed.
There is also an unpaired spectral-flux candidate at10.210s in the same bracket.
It could mark guitar activity separate from the clock-adjacent candidates, but
its identity is unknown. Review must not assume that the first musical attack
coincides exactly with one of the three proposed clock anchors.

## Early clock evidence and count limitations

A simple provisional cached scan in6–10seconds starts from the first spectral
event in that interval. Its seed is the median adjacent-event interval in
0.25–0.45seconds. A greedy next-event sequence accepts events within75ms of
the preceding selected event plus that seed; least-squares fitting follows.
This fixed transparent scan excludes off-sequence transients, but is not a
qualified robust mechanical-metronome tracker or instrument classifier.

| Proxy | Selected events | Fitted period | Equivalent BPM | Median absolute fit residual |
| --- | ---: | ---: | ---: | ---: |
| Spectral flux | 12 | 0.339493s | 176.734 | 2.337ms |
| SuperFlux | 12 | 0.339983s | 176.480 | 2.162ms |

These local fits differ from the global faster alias **177.6029 BPM**, whose
period is0.337832s. The difference may reflect mechanical startup/drift,
detector behavior or mixture transients; none is separately proved. Small fit
residuals quantify internal timing regularity, not metronome identity or accuracy
relative to the performer. Keep an observed/local click clock separate from
operator tempo and future expected arrangement boundaries.

The existing click tool contains219 half-time candidates:3 before5seconds,
8 in5–10seconds and208 at/after10seconds. Its three early candidates cannot be
promoted to metronome events against the operator's reported click-free setup.
The581 spectral and495 SuperFlux candidates also mix clock and guitar evidence.
None of these counts can be directly compared with404 intended musical clicks;
interpolating the faster alias creates clock hypotheses rather than observed
clicks. Keep count-in, analysis misses/duplicates and end-tail coverage explicit.

For review planning only,404 intended click intervals at constant178 BPM span
136.1798seconds, yielding an end-exclusive boundary bracket **146.1798–147.1798s**
from the coarse10–11second first-phrase bracket. The global faster observed alias
instead yields **146.4843–147.4843s**. The last expected click is403 intervals
after the first click; the404th interval's endpoint is the next boundary. These
are hypothetical arrangement extents, not a detected ending or proof of missed
beats. Do not extrapolate the local startup fit across the full performance.

## Handoff

The reference lane should retain the operator's expected404-click arrangement,
source identity, end-exclusive indexing and unresolved first-phrase anchor.
The marker lane can expose this candidate bracket and the three anchors as
review-only observations, keeping metronome-start review separate from musical
phrase-start review. The first breakdown's possible rush/skip remains operator
concern until a qualified clock and observed boundaries support comparison.
The setup interval contains fan plus minor guitar/amp sounds, so it must not be
silently adopted as pure noise or a verified click-only template.
