# Future practice studio design

This package records the operator's October 6 web, mastering, overlay and
classification request. It is a queued development direction; the current
local restoration and marked-video work continues separately.

Start with the [queued goal](GOAL_WEB_PRACTICE_STUDIO.md),
[budget and milestones](MILESTONES.md), and
[Linear goal TIN-5546](https://linear.app/tinyland/issue/TIN-5546/future-goal-private-guitar-practice-studio-mastering-and-explainable).
The [ticket manifest](linear-ready-tickets.json) retains the complete proposed
scope, including tracker writes pending service availability.

| Area | Design |
| --- | --- |
| Upload, process, compare, annotate, iterate, download | [Web UI](WEB_UI_DESIGN.md) |
| Durable jobs, progress, cancellation, private artifacts | [Web backend](WEB_BACKEND.md) |
| Shared CLI/MCP/web controls and repo navigation | [Capabilities and repository evolution](CAPABILITIES_AND_REPO_EVOLUTION.md) |
| Compact video labels, issue classes and user timestamps | [Overlays and annotations](OVERLAYS_AND_ANNOTATIONS.md) |
| Low-end fullness, tonal balance and capture references | [Mastering and capture response](MASTERING_AND_CAPTURE_RESPONSE.md) |
| User labels, PCEN/mel features and model evaluation | [Audio classification](AUDIO_CLASSIFICATION.md) |

The existing UI provides local playback and source-bound annotations. Uploads,
durable server jobs and hosted access are proposed work. The operator selected
compact section/phrase labels, BPM and brief issue badges for shareable videos;
the review interface can show more detail. Musical context, detector hypotheses
and user-reported issues remain distinct.

SLOs in these designs are proposed engineering targets to measure on declared
hardware and workloads. They are not production guarantees or an SLA. Preserve
the 35–70-hour next-week constraint when selecting work: design estimates are
alternatives and dependencies, not an additive commitment to ship everything.
