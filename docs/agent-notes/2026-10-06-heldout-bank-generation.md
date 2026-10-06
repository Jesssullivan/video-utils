# Admitted holdout generation: external authority and actual receipt

Authority: operator's active ten-hour goal and root's named holdout lane,
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. Root message to `repo_patterns`
explicitly released full generation after reviewing worker051d868/14tests and
freezing A/B/C/D harness78ca89de/settingsf50e31/6structural tests. That message
authorized serial12/120 generation in a fresh local directory, structural
verification and handoff of the frozen index; no inference in this lane.

This external receipt records subsequent admission without modifying the
immutable plan's historical `pending_root_admission` or
`full_generation_admitted:false` fields. Generated metadata is not an approval
authority. Both211and307 remain withheld from choosing the admitted settings.
The previous single-case proof and published development banks are preserved.

Admitted identities:

- PlanSHA256:
  `495ad2f3f553b0bd7030ac797b6e8589f37748df657219c075d0fc4ce7491e74`.
- RecipeSHA256:
  `0f8223e9adc4deb113c87a5b231b76bec33f573feabb03ec32bd8f565a5a3c63`.
- GeneratorSHA256:
  `051d8689364564513c34a1ab00a2c23560407e474da12c2bf25e7513dbc81709`.
- Preregistered comparison harnessSHA256:
  `78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c`.
- Comparison settingsSHA256:
  `f50e31ee6eba0966580f78c9124938b4cdf116a6242eed2b0e7b2bb147f32edd`.

Command actually started after matching the generator hash and checking fresh
output nonexistence:

```sh
python3 scripts/benchmark_holdout.py generate \
  --plan artifacts/benchmarks/holdout-admission-211-307/holdout-plan.json \
  --output artifacts/benchmarks/heldout-211-307-20261006T0020 \
  --timeout-seconds 600
```

Root also authorized the separate experiment owners to execute only the
preregistered comparisons after this bank passes structural validation. They
must save/hash predictions before evaluation reads generated truth. This lane
does not execute inference, score algorithms, label the actual take, or establish
musician ground truth/listening acceptance. Actual generation/verification
results follow after execution completes; launch is not a successful bank receipt.

## Actual generation and independent saved-bank verification

Generation completed successfully in **38.866400375seconds**. Immutable index
`artifacts/benchmarks/heldout-211-307-20261006T0020/fixtures.json` SHA256
`3828ef756c3b2d36890e5b2f444c9323960ec9c0b358d02fe02a8c13ba89936b`.
Twelve cases /120 unique source seconds /48 mono48kHz480,000-frame PCM16 WAVs,
46,082,112total component bytes including headers. No inference/quality score.

A separate saved-byte validator checked all48WAV hashes/native headers and
12truth hashes (60artifacts), source-versus-mixture receipts, index/worker/frozen
dependency bindings,106event ideal/actual native-to-source axes,378click axes and
pitch-region extents. Rendered mixture minus separately quantized clean+click+
noise has maximum absolute error **1PCM16 LSB**, within the bound2. No bank,
worker, prior proof or admitted metadata was rewritten by verification.

Both timing pairs have identical noise/click byte hashes and identical ideal
IDs/sample times. Reference cases contain12unedited events; each error case has
the fixed +1200,-1200,+2880,-2880sample timing offsets (±25/60ms at48kHz), one
explicit null omission and one added event. Positive MIDI24reference frequencies
equal true C1 **32.70319566257483Hz**; the low32 sentinel is separately32Hz.

| Generated construction | Seed211 | Seed307 | Evidence scope |
| --- | --- | --- | --- |
| Clean32Hz coherent amplitude, independently recomputed |0.160128345927868|0.14287029124449233|Generated clean PCM1–7s; matches admitted amplitude within5e-5 |
| Missing-F0 fitted fundamental coefficient |3.6627856445151484e-8|3.010215093401226e-7|Published joint-regression renderer verification, saved coefficient/harmonic bounds checked independently |

Both missing-F0 clean components have harmonics2/3/4/5/7, no post-synthesis
nonlinearity and joint-fit absolute tolerance5e-5 after quantization. Their
underlying periodicity is generated C1; this is not a model's C1 recovery result.
Both sustain cohorts have an explicitly empty generated recurrence reference.

Root's previously authorized structural gate is satisfied. Sent the exact frozen
index to `phrase_dag` for frozen78ca89de/settingsf50e31 A/B/C/D execution and
component-only paths/hashes to `xod_spectrogram` for its preregistered secondary
probe. No score/onset/phrase labels were supplied in the PCEN handoff. Discovery
must use opaque waveforms and inferred pulse only; predictions/features must be
saved and hashed before truth evaluation. That handoff is authorization/evidence,
not a forecast of detector accuracy or real musical acceptance.

Reproduce the saved-file header/hash/quantization checks without inference:

```python
import array, hashlib, json, sys, wave
from pathlib import Path
base=Path('artifacts/benchmarks/heldout-211-307-20261006T0020')
raw=(base/'fixtures.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='3828ef756c3b2d36890e5b2f444c9323960ec9c0b358d02fe02a8c13ba89936b'
index=json.loads(raw)
assert len(index['cases'])==12 and len(list(base.rglob('*.wav')))==48
for case in index['cases']:
    traw=(base/case['truth']['path']).read_bytes()
    assert hashlib.sha256(traw).hexdigest()==case['truth']['sha256']
    truth=json.loads(traw)
    assert truth['source']==case['source']
    assert truth['components']==case['components']
    parts={}
    for name,receipt in case['components'].items():
        path=base/receipt['path']
        assert not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['sha256']
        with wave.open(str(path),'rb') as stream:
            assert (stream.getnchannels(),stream.getsampwidth(),stream.getframerate(),stream.getnframes())==(1,2,48000,480000)
            data=array.array('h');data.frombytes(stream.readframes(480000))
        if sys.byteorder!='little':data.byteswap()
        parts[name]=data
    assert max(abs(m-a-b-c) for m,a,b,c in zip(parts['mix'],parts['clean'],parts['click'],parts['noise']))<=2
    for event in truth['generated_score']['events']:
        for native,seconds in [('ideal_onset_native_sample','ideal_onset_seconds'),('onset_native_sample','onset_source_seconds')]:
            if event[native] is None:
                assert event[seconds] is None and event['injected_edit']=='omitted_attack'
            else:
                assert event[seconds]==event[native]/48000
```
