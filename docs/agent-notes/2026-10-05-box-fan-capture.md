# Box-fan capture characterization receipt

Plan before measurement. Owner `clip_baseline`; authority root's bounded
actual-noise characterization delegation under the operator's stronger
restoration authorization, R-HOOK-CONVERGENCE-20261004 R-N12/R-N13. Exclusive
durable writes: this receipt and `docs/research/BOX_FAN_CAPTURE.md`. Existing
restoration comparison evidence is frozen. Coordinated complementary
low-register separability work with `audio_research`.

Read current AGENTS.md and applied guitar-noise: quietness/stationarity cannot
confirm fan-only sound. Read original hash-bound decoded WAV samples in only
three intervals, 4.10–4.95, 149–150 and 0–1 seconds. Bound the worker to two
numeric threads and less than ten seconds of actual selected audio. Rehash
original recording and decoded WAV before/after. Native Welch observations,
coarse peak widths and block-level stationarity only; no rendered audio,
filter/model/environment/root-file change or private recording upload.

## Completed scope and results

Only the two delegated Markdown files were written. Primary sources checked
October 5: LONGWELL's updated 2026-08-23 fan mechanism reference, NASA's
turbofan broadband-source report (household-frequency applicability limited),
SciPy Welch documentation, and UNSW equal-temperament equations. The
[research result](../research/BOX_FAN_CAPTURE.md) separates spectral facts,
possible mixture explanations and unverified fan/note/AGC identification.

First native measurement analyzed 2.85 seconds of selected float32 samples in
1.52 seconds wall time with two numeric threads. A bounded peak-check pass
reanalyzed the same 2.85 seconds, 3.52 seconds wall time, verifying WAV identity.
Both passes together inspected 5.70 seconds of selected audio; no decoding,
audio output, filters, models, installations, environment package/root-file
changes or cross-session signalling.

Capture/tail/opening RMS is −35.35/−34.30/−25.10 dBFS. Spectral differences
exclude one identical spectrum with a single scalar gain, but cannot assign
cause to fan output, guitar, handling or AGC. The nearest C1 bin is not a local
maximum in these estimates; absence of a peak cannot prove absence of music.
The 43 Hz range maximum is not a local peak in capture/tail, so the initial
range-based width estimate is explicitly rejected. Only opening's 43 Hz local
maximum has a coarse approximately 40–49 Hz crossing bracket. Musical-harmonic
proximity around theoretical Eb2 further limits any noise-only interpretation.
These corrected findings were sent to root and audio_research before handoff.

First-pass full measured JSON is below. Its range-maximum half-power brackets
are algorithmic outputs: the 75.37 Hz capture bracket and 8.07 Hz tail bracket
do **not** represent valid local-peak linewidths, because those range maxima
are not local peaks. The research document supplies the corrected local-peak
interpretation and second-pass strongest-peak crossing brackets.

```json
{
  "source_sha256": "a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6",
  "wav_sha256": "d68e49688293b1fb8c7c2566e2ecd6e31df9972af013dd23454e15864654bd2a",
  "sample_rate": 44100,
  "dtype": "float32",
  "total_selected_seconds": 2.85,
  "wall_seconds": 1.5234862079996674,
  "unchanged": true,
  "rows": [
    {
      "interval_seconds": [
        4.1,
        4.95
      ],
      "frames": 37485,
      "rms_dbfs": -35.34526643630114,
      "welch_segments": 3,
      "bin_hz": 2.691650390625,
      "band_power_dbfs": {
        "20-45": -65.34244516145301,
        "45-120": -48.94776752866274,
        "120-250": -38.716060396231754,
        "250-1000": -38.999640899314095,
        "1000-2000": -47.31819078027131,
        "2000-8000": -49.87117691421764,
        "8000-16000": -61.43311206166452
      },
      "low_peak": {
        "frequency_bin_hz": 43.06640625,
        "density_dbfs_per_hz": -74.67951159890522,
        "half_power_crossing_bracket_hz": [
          32.2998046875,
          107.666015625
        ],
        "bracket_width_hz": 75.3662109375,
        "range_peak_minus_median_db": 6.600782368837173
      },
      "prominent_peaks_10_1000_hz": [
        {
          "bin_hz": 174.957275390625,
          "density_dbfs_per_hz": -49.660599563377204
        },
        {
          "bin_hz": 269.1650390625,
          "density_dbfs_per_hz": -54.233286007299725
        },
        {
          "bin_hz": 199.18212890625,
          "density_dbfs_per_hz": -54.85992546619609
        },
        {
          "bin_hz": 156.11572265625,
          "density_dbfs_per_hz": -56.8510264797073
        },
        {
          "bin_hz": 312.2314453125,
          "density_dbfs_per_hz": -57.95642531298736
        },
        {
          "bin_hz": 390.289306640625,
          "density_dbfs_per_hz": -58.06476913344201
        },
        {
          "bin_hz": 339.14794921875,
          "density_dbfs_per_hz": -58.77530599484387
        },
        {
          "bin_hz": 298.773193359375,
          "density_dbfs_per_hz": -58.94794002728071
        }
      ],
      "blocks": [
        {
          "frames": 7497,
          "rms_dbfs": -36.51104275394023,
          "band_power_dbfs": {
            "20-45": -66.82331008031797,
            "45-120": -48.16985696769567,
            "120-250": -43.115594055407314,
            "250-1000": -39.503815076780235,
            "1000-2000": -48.17469281662327,
            "2000-8000": -50.54778549107769,
            "8000-16000": -63.13112860096133
          }
        },
        {
          "frames": 7497,
          "rms_dbfs": -36.04035349991131,
          "band_power_dbfs": {
            "20-45": -70.48739416270784,
            "45-120": -47.88605014698032,
            "120-250": -42.552064614981234,
            "250-1000": -38.8959109088477,
            "1000-2000": -47.757469947227136,
            "2000-8000": -50.11247184218267,
            "8000-16000": -63.507224544825185
          }
        },
        {
          "frames": 7497,
          "rms_dbfs": -35.37820891655025,
          "band_power_dbfs": {
            "20-45": -63.024666700371235,
            "45-120": -49.22288624914981,
            "120-250": -40.070574959743006,
            "250-1000": -39.583178455386744,
            "1000-2000": -47.419653427311474,
            "2000-8000": -50.97636447851155,
            "8000-16000": -63.203364193567936
          }
        },
        {
          "frames": 7497,
          "rms_dbfs": -34.139878707101495,
          "band_power_dbfs": {
            "20-45": -63.178361365579704,
            "45-120": -50.85787465312917,
            "120-250": -36.22608151095016,
            "250-1000": -37.80952234415216,
            "1000-2000": -46.770870090828424,
            "2000-8000": -47.66589520050198,
            "8000-16000": -57.785131807325804
          }
        },
        {
          "frames": 7497,
          "rms_dbfs": -35.04744061130533,
          "band_power_dbfs": {
            "20-45": -58.62325216199444,
            "45-120": -48.94575226699486,
            "120-250": -41.08288754338222,
            "250-1000": -36.32357899728564,
            "1000-2000": -46.50382076530466,
            "2000-8000": -46.98676247968776,
            "8000-16000": -62.895595564660965
          }
        }
      ],
      "block_rms_range_db": 2.371164046838736,
      "block_band_range_db": {
        "20-45": 11.864142000713407,
        "45-120": 2.971824506148856,
        "120-250": 6.889512544457155,
        "250-1000": 3.259599458101107,
        "1000-2000": 1.6708720513186108,
        "2000-8000": 3.9896019988237867,
        "8000-16000": 5.722092737499381
      }
    },
    {
      "interval_seconds": [
        149,
        150
      ],
      "frames": 44100,
      "rms_dbfs": -34.29958907632339,
      "welch_segments": 4,
      "bin_hz": 2.691650390625,
      "band_power_dbfs": {
        "20-45": -62.625156128799865,
        "45-120": -45.85730831445633,
        "120-250": -41.77214882099311,
        "250-1000": -38.91049737670634,
        "1000-2000": -40.860215152387184,
        "2000-8000": -41.53001109938272,
        "8000-16000": -56.5602901328696
      },
      "low_peak": {
        "frequency_bin_hz": 43.06640625,
        "density_dbfs_per_hz": -70.32095427270876,
        "half_power_crossing_bracket_hz": [
          40.374755859375,
          48.44970703125
        ],
        "bracket_width_hz": 8.074951171875,
        "range_peak_minus_median_db": 11.21067323987559
      },
      "prominent_peaks_10_1000_hz": [
        {
          "bin_hz": 156.11572265625,
          "density_dbfs_per_hz": -54.64416990254403
        },
        {
          "bin_hz": 118.4326171875,
          "density_dbfs_per_hz": -55.82080859078169
        },
        {
          "bin_hz": 312.2314453125,
          "density_dbfs_per_hz": -56.068978054257855
        },
        {
          "bin_hz": 129.19921875,
          "density_dbfs_per_hz": -56.65617648026742
        },
        {
          "bin_hz": 271.856689453125,
          "density_dbfs_per_hz": -57.27780590117817
        },
        {
          "bin_hz": 390.289306640625,
          "density_dbfs_per_hz": -57.84316826375039
        },
        {
          "bin_hz": 234.173583984375,
          "density_dbfs_per_hz": -57.994159721384115
        },
        {
          "bin_hz": 239.556884765625,
          "density_dbfs_per_hz": -60.56705512989982
        }
      ],
      "blocks": [
        {
          "frames": 8820,
          "rms_dbfs": -33.44672063539497,
          "band_power_dbfs": {
            "20-45": -66.23744261853089,
            "45-120": -47.04088770476648,
            "120-250": -43.8608509884947,
            "250-1000": -39.762458937885626,
            "1000-2000": -44.4615704136887,
            "2000-8000": -45.081794447268734,
            "8000-16000": -61.346071298739595
          }
        },
        {
          "frames": 8820,
          "rms_dbfs": -36.06286647536442,
          "band_power_dbfs": {
            "20-45": -60.616552491040196,
            "45-120": -47.76829815365766,
            "120-250": -40.65009171632815,
            "250-1000": -39.259373339150585,
            "1000-2000": -47.024700275710565,
            "2000-8000": -47.00769829311091,
            "8000-16000": -61.721028530633816
          }
        },
        {
          "frames": 8820,
          "rms_dbfs": -33.53352021930199,
          "band_power_dbfs": {
            "20-45": -62.408727695812374,
            "45-120": -46.34507113769665,
            "120-250": -40.56860470665535,
            "250-1000": -37.98603439852994,
            "1000-2000": -36.684552839333385,
            "2000-8000": -37.08986756449008,
            "8000-16000": -51.244220207713376
          }
        },
        {
          "frames": 8820,
          "rms_dbfs": -35.997951383546514,
          "band_power_dbfs": {
            "20-45": -64.61330419315135,
            "45-120": -45.33043040154521,
            "120-250": -41.53942334636011,
            "250-1000": -39.539210917358375,
            "1000-2000": -45.686089854255286,
            "2000-8000": -47.143111710699685,
            "8000-16000": -62.8021669528399
          }
        },
        {
          "frames": 8820,
          "rms_dbfs": -33.339319584790005,
          "band_power_dbfs": {
            "20-45": -62.954061423610305,
            "45-120": -48.10050994603551,
            "120-250": -40.46303876390763,
            "250-1000": -39.55088358669683,
            "1000-2000": -41.20637315203506,
            "2000-8000": -41.44766413209822,
            "8000-16000": -56.385383548392014
          }
        }
      ],
      "block_rms_range_db": 2.7235468905744185,
      "block_band_range_db": {
        "20-45": 5.620890127490696,
        "45-120": 2.770079544490301,
        "120-250": 3.3978122245870637,
        "250-1000": 1.7764245393556877,
        "1000-2000": 10.34014743637718,
        "2000-8000": 10.053244146209607,
        "8000-16000": 11.557946745126522
      }
    },
    {
      "interval_seconds": [
        0,
        1
      ],
      "frames": 44100,
      "rms_dbfs": -25.101370410395273,
      "welch_segments": 4,
      "bin_hz": 2.691650390625,
      "band_power_dbfs": {
        "20-45": -59.31930728995959,
        "45-120": -38.34656383795195,
        "120-250": -27.377360837853125,
        "250-1000": -28.844439058358773,
        "1000-2000": -45.59816051380456,
        "2000-8000": -47.0600133471212,
        "8000-16000": -62.89616437727158
      },
      "low_peak": {
        "frequency_bin_hz": 43.06640625,
        "density_dbfs_per_hz": -64.95731284856782,
        "half_power_crossing_bracket_hz": [
          40.374755859375,
          48.44970703125
        ],
        "bracket_width_hz": 8.074951171875,
        "range_peak_minus_median_db": 15.648537861551972
      },
      "prominent_peaks_10_1000_hz": [
        {
          "bin_hz": 166.88232421875,
          "density_dbfs_per_hz": -37.83250954603109
        },
        {
          "bin_hz": 174.957275390625,
          "density_dbfs_per_hz": -39.87387914815321
        },
        {
          "bin_hz": 306.84814453125,
          "density_dbfs_per_hz": -41.007398894254095
        },
        {
          "bin_hz": 336.456298828125,
          "density_dbfs_per_hz": -42.636213219985244
        },
        {
          "bin_hz": 129.19921875,
          "density_dbfs_per_hz": -45.31969678003201
        },
        {
          "bin_hz": 234.173583984375,
          "density_dbfs_per_hz": -46.14170951652085
        },
        {
          "bin_hz": 266.473388671875,
          "density_dbfs_per_hz": -46.837840827617754
        },
        {
          "bin_hz": 199.18212890625,
          "density_dbfs_per_hz": -49.27468440664771
        }
      ],
      "blocks": [
        {
          "frames": 8820,
          "rms_dbfs": -25.22579834398018,
          "band_power_dbfs": {
            "20-45": -65.37696038715413,
            "45-120": -41.783351898476255,
            "120-250": -24.09212463675374,
            "250-1000": -32.93192511929698,
            "1000-2000": -45.87536197053733,
            "2000-8000": -48.82999963040052,
            "8000-16000": -62.928643355031674
          }
        },
        {
          "frames": 8820,
          "rms_dbfs": -24.690571068754483,
          "band_power_dbfs": {
            "20-45": -61.775321570860115,
            "45-120": -38.7874961200888,
            "120-250": -30.783855475572956,
            "250-1000": -28.791457716065658,
            "1000-2000": -45.697940166484614,
            "2000-8000": -44.64828201587637,
            "8000-16000": -62.81347679865903
          }
        },
        {
          "frames": 8820,
          "rms_dbfs": -23.857832839565525,
          "band_power_dbfs": {
            "20-45": -60.732064694428445,
            "45-120": -38.037428626583456,
            "120-250": -27.361976024658013,
            "250-1000": -27.458594555990487,
            "1000-2000": -45.11595169180933,
            "2000-8000": -48.42783796425184,
            "8000-16000": -63.631270880825596
          }
        },
        {
          "frames": 8820,
          "rms_dbfs": -25.64988034838305,
          "band_power_dbfs": {
            "20-45": -68.02912465693238,
            "45-120": -42.45205007581568,
            "120-250": -26.255846742305838,
            "250-1000": -29.88086756467256,
            "1000-2000": -46.743447977464655,
            "2000-8000": -49.46874429274594,
            "8000-16000": -63.043571240771016
          }
        },
        {
          "frames": 8820,
          "rms_dbfs": -26.551353994295198,
          "band_power_dbfs": {
            "20-45": -63.437353015386826,
            "45-120": -42.53081318723904,
            "120-250": -28.925284968087333,
            "250-1000": -33.721576686657116,
            "1000-2000": -46.65216404731201,
            "2000-8000": -49.99136593240313,
            "8000-16000": -62.90158946058512
          }
        }
      ],
      "block_rms_range_db": 2.693521154729673,
      "block_band_range_db": {
        "20-45": 7.297059962503937,
        "45-120": 4.493384560655585,
        "120-250": 6.691730838819215,
        "250-1000": 6.262982130666629,
        "1000-2000": 1.627496285655326,
        "2000-8000": 5.3430839165267585,
        "8000-16000": 0.8177940821665644
      }
    }
  ]
}
```

## Bounded reproduction

Run from repo root with the existing environment. This emits measurements to
stdout only and verifies the original and frozen source WAV before/after.
Thread settings affect this subprocess only; no environment file is edited.

```sh
.venv/bin/python - <<'PY'
import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '2'
import hashlib, json
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import welch, find_peaks
manifest = json.loads(Path(
    'artifacts/runs/20261005T211103Z-c6d0bac2fcd2/manifest.json').read_text())
original = Path(manifest['source']['path'])
wav = Path(manifest['run_dir']) / 'source.wav'
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()
before = {str(p): sha(p) for p in (original, wav)}
assert before[str(original)] == manifest['source']['sha256']
assert before[str(wav)] == manifest['output_sha256']['source.wav']
rate, samples = wavfile.read(wav, mmap=True)
assert rate == 44100 and samples.ndim == 1
bands = [(20,45), (45,120), (120,250), (250,1000),
         (1000,2000), (2000,8000), (8000,16000)]
def db(value):
    return float(10*np.log10(max(float(value), 1e-300)))
for start, end in [(4.1,4.95), (149,150), (0,1)]:
    x = np.array(samples[round(start*rate):round(end*rate)], dtype=np.float64)
    f, p = welch(x, fs=rate, window='hann', nperseg=16384,
                 noverlap=8192, detrend=False, scaling='density')
    df = f[1]-f[0]
    peaks, _ = find_peaks(10*np.log10(np.maximum(p,1e-300)), prominence=3)
    peaks = sorted((int(i) for i in peaks if 10 <= f[i] <= 1000),
                   key=lambda i: p[i], reverse=True)[:8]
    widths = []
    for i in peaks[:4]:
        left = right = i
        while left > 0 and p[left] > p[i]/2: left -= 1
        while right < len(p)-1 and p[right] > p[i]/2: right += 1
        widths.append([float(f[i]), float(f[left]), float(f[right])])
    blocks = []
    for block in np.array_split(x, 5):
        ff, pp = welch(block, fs=rate, window='hann', nperseg=len(block),
                       noverlap=0, detrend=False, scaling='density')
        blocks.append({'rms_dbfs': db(np.mean(block**2)),
            'bands': {str((lo,hi)): db(pp[(ff>=lo)&(ff<hi)].sum()*(ff[1]-ff[0]))
                      for lo,hi in bands}})
    print(json.dumps({'interval':[start,end], 'frames':len(x),
        'rms_dbfs':db(np.mean(x*x)), 'bin_hz':float(df),
        'bands':{str((lo,hi)):db(p[(f>=lo)&(f<hi)].sum()*df)
                 for lo,hi in bands},
        'peak_bins_hz':[float(f[i]) for i in peaks],
        'strongest_local_halfpower_brackets':widths, 'blocks':blocks}))
assert before == {str(p): sha(p) for p in (original, wav)}
print('Original and decoded source unchanged; no output media')
PY
```

Validation: read back both owned documents; check local links, whitespace and
the embedded reproduction script's syntax. Prior comparison evidence remains
unchanged. Durable measurements establish interval variation and spectral
ambiguity; fan-only identification, actual gain-control history and musical
preservation remain unresolved.

Process receipt: actor clip_baseline | target original/frozen decoded source
short-interval read-only characterization | reason operator's box-fan cleanup
and low-register preservation question | ruling R-HOOK-CONVERGENCE-20261004
R-N12/R-N13 | prior_state root-reviewed capture with contamination uncertainty |
result hash-bound short PSD/stability observations; no fan RPM, notch, note
identity, automatic master preference or isolated stem claim.
