# Guarded phrase arms: pre-holdout source freeze

Actor: `/root/phrase_dag`. Authority: root's explicit isolated A/B/C/D
implementation release; operator's parallel ten-hour goal;
R-HOOK-CONVERGENCE-20261004/R-N13. Freeze precedes held-out generation/inference.
Canonical workers, registry and first frozen ablation harness were not changed.

| Receipt | SHA256 |
| --- | --- |
| Experimental cache-only harness `docs/agent-notes/2026-10-05-phrase-guarded-arms.py` | `78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c` |
| Exact settings/formulas | `f50e31ee6eba0966580f78c9124938b4cdf116a6242eed2b0e7b2bb147f32edd` |
| Canonical frontend/search dependency | `2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe` |
| Development cache input index | `c2cfcb5146e8046d86a295e33e897721ec21321d8e78cd7cd665eac68f59e812` |
| Final development arm index | `a334f7244cf82db0de8e8a4414b45a9b64b209de1dff1e99ac770afc6ff4800b` |
| Final prediction/metric equivalence check | `67caa1a548542c7272b7a98d5590e27ca6c76718365c424f2860fc3b8edce042` |

Exact formulas are in `docs/spec/PHRASE_WINDOW_ABLATION_LANE.md`. A uses the
frozen short2/4/8/16 search. B subtracts the mean of the two anchor-specific
median nonoverlapping competitor cosines, excludes the exact selected partner,
requires contrast≥0.10 and ranks at most10. C uses a200ms acoustic-feature novelty
context, existing-style robust threshold, source-bound peak search within one
inferred pulse capped0.75s, deterministic ties, and full endpoint rollback on
invalid spans. D applies exactly C to exactly B. Unknown detector/boundary
confidence remains null; no arm confirms performance mistakes.

Validation command:

```sh
.venv/bin/python docs/agent-notes/2026-10-05-phrase-guarded-arms.py --self-test
```

Six structural tests passed in0.155s: independent two-anchor contrast oracle and
homogeneous rejection; deterministic cap/ties and arm-count composition;
ambiguous/invalid refinement retention; source-curve endpoint refinement and
onset rebasing; finite/time/frame/source bounds; and NPZ archive expansion/member
guards before allocation. An initially mistaken hand-calculated competitor count
was corrected: the second anchor has three competitors with cosines0,−1,−1.
The implementation formula and thresholds did not change to fit an audio score.

Existing six-case development caches were read without waveform decoding. Arm A
matches the prior frozen short-window output. All predictions were saved before
development truth was attached. Bounds/stable-input safeguards were strengthened
after the first development run; final source was rerun and its A/B/C/D arrays,
contrast audits and novelty thresholds match the original computed predictions
exactly. No numeric threshold or endpoint algorithm was retuned.

| Arm | TP / FP / FN at paired IoU0.5 | TP / FP / FN at IoU0.75 |
| --- | --- | --- |
| A short control | 3 / 11 / 1 | 1 / 13 / 3 |
| B contrast/ranking | 3 / 6 / 1 | 1 / 8 / 3 |
| C endpoint refinement | 3 / 11 / 1 | 0 / 14 / 4 |
| D combined | 3 / 6 / 1 | 0 / 9 / 4 |

B removes all five missing-fundamental false proposals in this development
subset; low32 sustain still has two. C/D visibly regress strict paired matches.
That regression remains part of the preregistration; it is not hidden by the
aggregate IoU0.5 score. Development quality does not qualify either held-out seed.

Both211/307 remain withheld from setting selection. No held-out waveform,
one-case proof audio, prediction or metric was inspected during implementation.
The root-owned full generator and subsequent inference/evaluation require their
separate releases. A future adoption proposal still requires control-level
held-out recall, lower negative false candidates on both seeds, improved matched
endpoint error, and no loss of IoU0.75 true matches. Failures stay frozen rather
than tuning the same held-out labels. These are development decision gates,
not real-player correctness, listening or production-executor acceptance.
