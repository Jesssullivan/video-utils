# NR8 / NR10 comparison successor: closed producer versions

Owner `audio_research`; authority root's explicit successor source release under
R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13. The original
[method](2026-10-05-nr10-restoration-comparison-method.md) remains frozen at9c06.
Only exact application-producer binding and disclosure change in this successor;
no measurement/DSP/profile execution was released by this source task.

Root reports the original NR8 application succeeded on00a03, its initial NR10
attempt failed cleanup without publishing a candidate, and the resource repair
790ac passed fresh generated-native and independent qualification before the
separate NR10 retry. The [resource repair](2026-10-06-apply-capture-profile-inspection-repair.md)
records process-inspection retries/caps/reuse; authoring and media/DSP workers
are unchanged. This comparison lane does not substitute those source/generated
proofs for actual candidate binding, independent measurements or listening.

Before edits, exact historical driver and owner-test bytes were preserved in
[driver snapshot](source-freezes/2026-10-06-nr8-nr10-comparison-7f46a701.py)
SHA256 `7f46a7010f42558bf8d39f8a94fc9b0a6f513a12242e61d6be553267d6e9b26e` and
[test snapshot](source-freezes/2026-10-06-nr8-nr10-comparison-tests-cd819f20.py)
SHA256 `cd819f20f73a79ebae94f32c1275bb9635622de3bbae46b1ac9aabcb445fe47e`.
These are exact byte snapshots, not relocated runnable entrypoints; their
original path-dependent imports are deliberately not rewritten. Historical
qualification stays with those bytes.

## Successor pins and release schema

Current [driver](2026-10-06-nr8-nr10-comparison.py) SHA256:
`2322d9e1d2f2309802ba667a80f004261615e16b358d5432123d182dfef72ee2`.
Current [owner tests](../../tests/test_nr8_nr10_comparison.py) SHA256:
`3cc0c862c22e9890ae03794ebe6c5e38a9baa5db89a74579f170909a68d3d241`.

The root measurement release must now add this exact closed map to the
[existing release schema](2026-10-06-nr8-nr10-comparison-source.md):

```json
"approved_application_producers": {
  "nr8": "00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6",
  "nr10": "790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584"
}
```

The required map cannot be omitted, broadened, swapped or replaced by an
arbitrary producer whitelist. Each candidate application receipt must have its
role's exact producer. Candidate manifest/application/export selectors and
hashes remain strict. Both candidates must retain authoring7d282 and shared
media/DSP914431 plus identical source/capture/settings outside NR. The current
owned measurement runner is pinned790ac, independent of historical NR8 producer.
The [archived NR8 application](source-freezes/2026-10-06-apply-capture-profile-00a03ef9.py)
is hashed at00a03; the [new resource-qualification JSON](2026-10-06-capture-application-resource-qualification-result.json)
is pinned at `3ad6a3c119c4e3196604f8818630ec74960028cb1df33e3f3e7c0e3abcb09603`.
Both become rechecked read-only provenance bindings.

Result metadata exposes the approved map, each observed application producer,
the differing resource-runner revisions, archived old source, generated repair
qualification identity and shared DSP-worker hashes. This is not a hidden
single-producer experiment; root's repair qualification supplies the resource
change classification, while unchanged worker/settings hashes are independently
checked by this driver. The new root input release still must bind both actual
published candidates and all protected identities before any measurement.

## Tests, measurements and listening boundary

Locked-env21 owner tests passed12.852 seconds, including the prior timer,
partial-result, meter-input, native-clock, residue-context and32Hz/coherence
oracles plus exact-role producer acceptance/refusal, unapproved old NR10/hash
refusal, release-map extras/swaps, shared author/media changes and preserved
historical snapshots. The standard-library invocation ran21 cases in4.339
seconds:18 passes and three explicit optional NumPy/SciPy skips. Final source
and test compile passed. These use in-memory synthetic signals, mocked
metadata/meters and an owned inert Python process; no FFmpeg or actual take
samples are processed. Separate successor independent source closure is pending.

The55-second processing timer, reserved cleanup/reporting within nominal60s,
two-thread limit, source WAV loaded once, fixed intervals/anchors, complete
protected-hash readback and honest partial coverage remain unchanged. No
original-movie decode or inference is added. Meter only the new candidate master
and final AAC; delivery eligibility is structural success plus AAC −18±0.3LUFS
and true peak≤−1.75dBTP at reported meter precision. It is not master adoption.

Operator now reports minor guitar/amp activity and mechanical wind-up before
5seconds. The4.10–4.95 capture remains contamination-uncertain, never noise-only.
Compare pure-denoise NR10−NR8 quiet4–5 and opening0–1 changes before makeup;
inspect fixed low20–45Hz, attack/tail/end-gesture panels and unity-gain residue.
Then listen to matched masters for low-string weight, pick texture, sustain and
legato/tapping, retaining articulation uncertainty. Residue may contain guitar.
No fan-only gain, isolated music attenuation, confirmed note correctness,
preferred winner or audible acceptance follows from completed measurements.

Process receipt: actor audio_research | target root-released successor source
and exact owned archives | reason compare only two qualified application
versions with unchanged DSP | ruling R-N11/R-N12/R-N13 | prior_state historical
7f46 source audited, actual comparison unreleased | result successor21 source/
inert tests pass, historical bytes retained; independent closure and exact
actual measurement input release remain separate.
