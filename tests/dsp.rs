//! Preregistered DSP verification (docs/spec/sprints/RUST_CORE_S2.md, M7-M11).
//!
//! Coefficients are re-derived here from the RBJ cookbook formulas instead of
//! being imported from `src`, so a formula error in the library cannot hide in
//! its own reference. Measured values are printed with a `MEASURED` prefix for
//! the run receipt (`cargo test --test dsp -- --nocapture`).

use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::f64::consts::PI;

use video_utils::dsp::{Biquad, BiquadCoefficients, DspError, PeakRms};
use video_utils::{MAX_BLOCK_SAMPLES, apply_gain};

// ---------------------------------------------------------------------------
// Counting allocator (per-thread, const-initialized so it never allocates).

struct CountingAllocator;

thread_local! {
    static ALLOCATIONS: Cell<usize> = const { Cell::new(0) };
}

fn bump() {
    let _ = ALLOCATIONS.try_with(|count| count.set(count.get() + 1));
}

unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        bump();
        unsafe { System.alloc(layout) }
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        bump();
        unsafe { System.alloc_zeroed(layout) }
    }

    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        bump();
        unsafe { System.realloc(ptr, layout, new_size) }
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}

#[global_allocator]
static GLOBAL: CountingAllocator = CountingAllocator;

fn allocations() -> usize {
    ALLOCATIONS.with(Cell::get)
}

// ---------------------------------------------------------------------------
// Independent cookbook reference.

#[derive(Clone, Copy, Debug)]
enum Kind {
    Peaking,
    LowShelf,
}

#[derive(Clone, Copy, Debug)]
struct Case {
    kind: Kind,
    fs: f64,
    f0: f64,
    gain_db: f64,
    q: f64,
}

/// Raw (b0, b1, b2, a0, a1, a2) from the RBJ Audio EQ Cookbook.
fn cookbook_raw(case: Case) -> [f64; 6] {
    let a = 10f64.powf(case.gain_db / 40.0);
    let w0 = 2.0 * PI * case.f0 / case.fs;
    let (sin, cos) = w0.sin_cos();
    let alpha = sin / (2.0 * case.q);
    match case.kind {
        Kind::Peaking => [
            1.0 + alpha * a,
            -2.0 * cos,
            1.0 - alpha * a,
            1.0 + alpha / a,
            -2.0 * cos,
            1.0 - alpha / a,
        ],
        Kind::LowShelf => {
            let k = 2.0 * a.sqrt() * alpha;
            [
                a * ((a + 1.0) - (a - 1.0) * cos + k),
                2.0 * a * ((a - 1.0) - (a + 1.0) * cos),
                a * ((a + 1.0) - (a - 1.0) * cos - k),
                (a + 1.0) + (a - 1.0) * cos + k,
                -2.0 * ((a - 1.0) + (a + 1.0) * cos),
                (a + 1.0) + (a - 1.0) * cos - k,
            ]
        }
    }
}

/// Normalized (b0, b1, b2, a1, a2).
fn cookbook(case: Case) -> [f64; 5] {
    let [b0, b1, b2, a0, a1, a2] = cookbook_raw(case);
    [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0]
}

fn build(case: Case) -> Biquad {
    match case.kind {
        Kind::Peaking => Biquad::peaking(case.fs, case.f0, case.q, case.gain_db).unwrap(),
        Kind::LowShelf => Biquad::low_shelf(case.fs, case.f0, case.q, case.gain_db).unwrap(),
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct C64 {
    re: f64,
    im: f64,
}

impl C64 {
    fn new(re: f64, im: f64) -> Self {
        Self { re, im }
    }
    fn add(self, o: Self) -> Self {
        Self::new(self.re + o.re, self.im + o.im)
    }
    fn sub(self, o: Self) -> Self {
        Self::new(self.re - o.re, self.im - o.im)
    }
    fn mul(self, o: Self) -> Self {
        Self::new(
            self.re * o.re - self.im * o.im,
            self.re * o.im + self.im * o.re,
        )
    }
    fn div(self, o: Self) -> Self {
        let d = o.re * o.re + o.im * o.im;
        Self::new(
            (self.re * o.re + self.im * o.im) / d,
            (self.im * o.re - self.re * o.im) / d,
        )
    }
    fn scale(self, k: f64) -> Self {
        Self::new(self.re * k, self.im * k)
    }
    fn abs(self) -> f64 {
        self.re.hypot(self.im)
    }
    fn arg(self) -> f64 {
        self.im.atan2(self.re)
    }
    /// p^n in polar form (no accumulated multiplication error).
    fn powi(self, n: i32) -> Self {
        let r = self.abs().powi(n);
        let t = self.arg() * f64::from(n);
        Self::new(r * t.cos(), r * t.sin())
    }
    fn recip(self) -> Self {
        Self::new(1.0, 0.0).div(self)
    }
}

/// B(z) = b0 + b1 z^-1 + b2 z^-2 evaluated at z.
fn numerator_at(c: [f64; 5], z: C64) -> C64 {
    let zi = z.recip();
    C64::new(c[0], 0.0)
        .add(zi.scale(c[1]))
        .add(zi.mul(zi).scale(c[2]))
}

/// Closed-form impulse response by pole-residue expansion:
/// H(z) = b2/a2 + R1/(1-p1 z^-1) + R2/(1-p2 z^-1), so
/// h[n] = (b2/a2) δ[n] + R1 p1^n + R2 p2^n (= 2 Re(R1 p1^n) for conjugate poles).
///
/// A repeated real pole (discriminant zero, which the Q = 0.5 RBJ shelf
/// produces exactly) has no simple-pole residues; its limit form is
/// h[n] = (b2/a2) δ[n] + n0 (n+1) p^n + n1 n p^(n-1) with
/// n0 = b0 - b2/a2 and n1 = b1 - a1 b2/a2.
fn closed_form_impulse(c: [f64; 5], n: usize) -> (Vec<f64>, &'static str) {
    let [b0, b1, b2, a1, a2] = c;
    let direct = b2 / a2;
    let disc = a1 * a1 - 4.0 * a2;
    if disc.abs() <= 1e-14 * a1 * a1 {
        let p = -a1 / 2.0;
        let (n0, n1) = (b0 - direct, b1 - a1 * direct);
        let h = (0..n)
            .map(|k| {
                let kf = k as f64;
                let pk = p.powi(i32::try_from(k).unwrap());
                let pk1 = if k == 0 {
                    0.0
                } else {
                    p.powi(i32::try_from(k - 1).unwrap())
                };
                let d = if k == 0 { direct } else { 0.0 };
                d + n0 * (kf + 1.0) * pk + n1 * kf * pk1
            })
            .collect();
        return (h, "repeated_real_pole");
    }
    let (p1, p2, form) = if disc < 0.0 {
        let im = (-disc).sqrt() / 2.0;
        (
            C64::new(-a1 / 2.0, im),
            C64::new(-a1 / 2.0, -im),
            "complex_conjugate_poles",
        )
    } else {
        let root = disc.sqrt();
        (
            C64::new((-a1 + root) / 2.0, 0.0),
            C64::new((-a1 - root) / 2.0, 0.0),
            "two_real_poles",
        )
    };
    let one = C64::new(1.0, 0.0);
    let r1 = numerator_at(c, p1).div(one.sub(p2.div(p1)));
    let r2 = numerator_at(c, p2).div(one.sub(p1.div(p2)));
    let h = (0..n)
        .map(|k| {
            let k = i32::try_from(k).unwrap();
            let d = if k == 0 { direct } else { 0.0 };
            if disc < 0.0 {
                d + 2.0 * r1.mul(p1.powi(k)).re
            } else {
                d + r1.mul(p1.powi(k)).re + r2.mul(p2.powi(k)).re
            }
        })
        .collect();
    (h, form)
}

/// |H(e^{jw})| in dB for normalized coefficients.
fn response_db(c: [f64; 5], frequency: f64, fs: f64) -> f64 {
    let w = 2.0 * PI * frequency / fs;
    let z1 = C64::new(w.cos(), -w.sin());
    let z2 = z1.mul(z1);
    let num = C64::new(c[0], 0.0).add(z1.scale(c[1])).add(z2.scale(c[2]));
    let den = C64::new(1.0, 0.0).add(z1.scale(c[3])).add(z2.scale(c[4]));
    20.0 * num.div(den).abs().log10()
}

fn src_coefficients(filter: &Biquad) -> [f64; 5] {
    let c: BiquadCoefficients = filter.coefficients();
    [c.b0, c.b1, c.b2, c.a1, c.a2]
}

fn grid() -> Vec<Case> {
    let mut cases = Vec::new();
    for fs in [44_100.0, 48_000.0] {
        for (f0, gain_db, q) in [(300.0, 1.0, 0.8), (160.0, 2.0, 0.7), (32.703, -3.0, 1.0)] {
            cases.push(Case {
                kind: Kind::Peaking,
                fs,
                f0,
                gain_db,
                q,
            });
        }
        for (f0, gain_db, q) in [(100.0, 3.0, 0.707), (40.0, 2.0, 0.5)] {
            cases.push(Case {
                kind: Kind::LowShelf,
                fs,
                f0,
                gain_db,
                q,
            });
        }
    }
    cases
}

/// Process an arbitrarily long signal in bounded blocks.
fn run_blocks(filter: &mut Biquad, signal: &mut [f32]) {
    for block in signal.chunks_mut(4096) {
        filter.process(block).unwrap();
    }
}

// ---------------------------------------------------------------------------
// M7

#[test]
fn impulse_matches_closed_form_rbj() {
    const N: usize = 4096;
    let cases = grid();
    assert_eq!(cases.len(), 10);
    let mut passed = 0;
    for case in &cases {
        let reference = cookbook(*case);
        let mut filter = build(*case);
        let mut impulse = vec![0.0f32; N];
        impulse[0] = 1.0;
        filter.process(&mut impulse).unwrap();
        let (expected, form) = closed_form_impulse(reference, N);
        assert!(
            expected.iter().all(|value| value.is_finite()),
            "{case:?}: non-finite reference"
        );
        assert!(
            impulse.iter().all(|value| value.is_finite()),
            "{case:?}: non-finite output"
        );
        let max_error = impulse
            .iter()
            .zip(&expected)
            .map(|(&got, &want)| (f64::from(got) - want).abs())
            .fold(0.0f64, f64::max);
        // Guard against a degenerate (all-zero) reference passing vacuously.
        assert!(
            (expected[0] - reference[0]).abs() <= 1e-12,
            "{case:?}: h[0] != b0"
        );
        let coefficient_error = reference
            .iter()
            .zip(src_coefficients(&filter))
            .map(|(a, b)| (a - b).abs())
            .fold(0.0f64, f64::max);
        println!(
            "MEASURED M7 {:?} fs={} f0={} g={} q={} form={form} max_abs_impulse_error={:.3e} max_coefficient_diff={:.3e}",
            case.kind, case.fs, case.f0, case.gain_db, case.q, max_error, coefficient_error
        );
        assert!(max_error <= 1e-6, "{case:?}: impulse error {max_error:e}");
        passed += 1;
    }
    println!("MEASURED M7 passed={passed}/{}", cases.len());
}

// ---------------------------------------------------------------------------
// M8

/// Goertzel magnitude at exactly `frequency` (non-integer bins allowed).
fn goertzel(signal: &[f32], frequency: f64, fs: f64) -> f64 {
    let w = 2.0 * PI * frequency / fs;
    let coeff = 2.0 * w.cos();
    let (mut s1, mut s2) = (0.0f64, 0.0f64);
    for &x in signal {
        let s0 = f64::from(x) + coeff * s1 - s2;
        s2 = s1;
        s1 = s0;
    }
    let re = s1 - s2 * w.cos();
    let im = s2 * w.sin();
    re.hypot(im)
}

fn tone_gain_db(case: Case, tone_hz: f64) -> (f64, f64) {
    let fs = case.fs;
    let settle = fs as usize;
    let measure = 4 * fs as usize;
    let input: Vec<f32> = (0..settle + measure)
        .map(|n| (0.5 * (2.0 * PI * tone_hz * n as f64 / fs).sin()) as f32)
        .collect();
    let mut output = input.clone();
    let mut filter = build(case);
    run_blocks(&mut filter, &mut output);
    let measured = 20.0
        * (goertzel(&output[settle..], tone_hz, fs) / goertzel(&input[settle..], tone_hz, fs))
            .log10();
    let analytic = response_db(cookbook(case), tone_hz, fs);
    (measured, analytic)
}

#[test]
fn low_string_tone_passes_300hz_peaking_band() {
    // C1 low string of the nine-string tuning (program/instrument.json).
    const LOW_C_HZ: f64 = 32.703;
    let mut passed = 0;
    for fs in [44_100.0, 48_000.0] {
        let case = Case {
            kind: Kind::Peaking,
            fs,
            f0: 300.0,
            gain_db: 1.0,
            q: 0.8,
        };
        let (measured, analytic) = tone_gain_db(case, LOW_C_HZ);
        println!(
            "MEASURED M8 band=300Hz+1dBQ0.8 fs={fs} tone={LOW_C_HZ}Hz gain_db={measured:.6} analytic_db={analytic:.6} diff_db={:.6}",
            measured - analytic
        );
        assert!(
            measured.abs() <= 0.05,
            "fs {fs}: |gain| {measured} dB > 0.05"
        );
        assert!(
            (measured - analytic).abs() <= 0.005,
            "fs {fs}: {measured} vs analytic {analytic}"
        );
        passed += 1;
    }
    println!("MEASURED M8 passed={passed}/2");
    // Disclosure only (not gated): the accepted profile's 160 Hz band.
    for fs in [44_100.0, 48_000.0] {
        let case = Case {
            kind: Kind::Peaking,
            fs,
            f0: 160.0,
            gain_db: 2.0,
            q: 0.7,
        };
        let (measured, analytic) = tone_gain_db(case, LOW_C_HZ);
        println!(
            "MEASURED M8-disclosure band=160Hz+2dBQ0.7 fs={fs} tone={LOW_C_HZ}Hz gain_db={measured:.6} analytic_db={analytic:.6} (not gated)"
        );
    }
}

// ---------------------------------------------------------------------------
// Response landmarks.

#[test]
fn peaking_center_and_shelf_asymptotes() {
    for case in grid() {
        let filter = build(case);
        let c = src_coefficients(&filter);
        match case.kind {
            Kind::Peaking => {
                let center = response_db(c, case.f0, case.fs);
                println!(
                    "MEASURED landmark peaking fs={} f0={} G={} center_db={center:.6}",
                    case.fs, case.f0, case.gain_db
                );
                assert!(
                    (center - case.gain_db).abs() <= 0.01,
                    "{case:?}: centre {center}"
                );
            }
            Kind::LowShelf => {
                let dc = response_db(c, 0.0, case.fs);
                let high = response_db(c, 0.45 * case.fs, case.fs);
                println!(
                    "MEASURED landmark lowshelf fs={} f0={} G={} dc_db={dc:.6} at_0.45fs_db={high:.6}",
                    case.fs, case.f0, case.gain_db
                );
                assert!((dc - case.gain_db).abs() <= 0.01, "{case:?}: DC {dc}");
                assert!(high.abs() <= 0.1, "{case:?}: 0.45 fs {high}");
                // Processed DC step settles to the same shelf gain.
                let mut processed =
                    Biquad::low_shelf(case.fs, case.f0, case.q, case.gain_db).unwrap();
                let mut step = vec![0.25f32; 3 * case.fs as usize];
                run_blocks(&mut processed, &mut step);
                let settled = 20.0 * (f64::from(*step.last().unwrap()) / 0.25).log10();
                assert!(
                    (settled - case.gain_db).abs() <= 0.01,
                    "{case:?}: settled DC {settled}"
                );
            }
        }
    }
}

// ---------------------------------------------------------------------------
// M9

fn warmed_filter() -> Biquad {
    let mut filter = Biquad::peaking(48_000.0, 1_000.0, 1.0, 24.0).unwrap();
    let mut warm = [0.5f32, -0.25, 0.125, 0.75];
    filter.process(&mut warm).unwrap();
    filter
}

fn bits32(samples: &[f32]) -> Vec<u32> {
    samples.iter().map(|s| s.to_bits()).collect()
}

#[test]
fn bounds_and_atomic_refusal() {
    let mut cases = 0;
    let mut check_filter =
        |label: &str, filter: &mut Biquad, samples: &mut [f32], expected: DspError| {
            let state = filter.state().to_bits();
            let coefficients = filter.coefficients().to_bits();
            let before = bits32(samples);
            assert_eq!(filter.process(samples), Err(expected), "{label}");
            assert_eq!(bits32(samples), before, "{label}: buffer changed");
            assert_eq!(filter.state().to_bits(), state, "{label}: state changed");
            assert_eq!(
                filter.coefficients().to_bits(),
                coefficients,
                "{label}: coefficients changed"
            );
            cases += 1;
        };

    let mut filter = warmed_filter();
    let mut oversized = vec![0.25f32; MAX_BLOCK_SAMPLES + 1];
    check_filter(
        "biquad oversized",
        &mut filter,
        &mut oversized,
        DspError::BlockTooLarge,
    );
    let mut nan_last = [0.25f32, -0.5, f32::NAN];
    check_filter(
        "biquad NaN last",
        &mut filter,
        &mut nan_last,
        DspError::NonFiniteSample,
    );
    let mut inf_last = [0.25f32, -0.5, f32::INFINITY];
    check_filter(
        "biquad +Inf last",
        &mut filter,
        &mut inf_last,
        DspError::NonFiniteSample,
    );
    let mut neg_inf_last = [0.25f32, -0.5, f32::NEG_INFINITY];
    check_filter(
        "biquad -Inf last",
        &mut filter,
        &mut neg_inf_last,
        DspError::NonFiniteSample,
    );
    let mut overflow = [0.25f32, f32::MAX];
    check_filter(
        "biquad peaking overflow",
        &mut filter,
        &mut overflow,
        DspError::Overflow,
    );
    let mut shelf = Biquad::low_shelf(48_000.0, 100.0, 0.707, 24.0).unwrap();
    let mut sustained = vec![f32::MAX; 4096];
    check_filter(
        "low shelf sustained overflow",
        &mut shelf,
        &mut sustained,
        DspError::Overflow,
    );

    // Invalid parameters: constructors refuse; setters leave coefficients/state unchanged.
    let fs = 48_000.0;
    let invalid: [(f64, f64, f64, f64, &str); 14] = [
        (fs, 0.0, 0.7, 1.0, "f0 = 0"),
        (fs, -10.0, 0.7, 1.0, "f0 < 0"),
        (fs, 0.49 * fs, 0.7, 1.0, "f0 = 0.49 fs"),
        (fs, 0.5 * fs, 0.7, 1.0, "f0 > 0.49 fs"),
        (fs, 300.0, 0.099, 1.0, "Q < 0.1"),
        (fs, 300.0, 40.01, 1.0, "Q > 40"),
        (fs, 300.0, 0.7, 24.01, "G > 24"),
        (fs, 300.0, 0.7, -24.01, "G < -24"),
        (7_999.0, 300.0, 0.7, 1.0, "fs < 8000"),
        (384_001.0, 300.0, 0.7, 1.0, "fs > 384000"),
        (f64::NAN, 300.0, 0.7, 1.0, "fs NaN"),
        (fs, f64::NAN, 0.7, 1.0, "f0 NaN"),
        (fs, 300.0, f64::NAN, 1.0, "Q NaN"),
        (fs, 300.0, 0.7, f64::INFINITY, "G Inf"),
    ];
    let mut parameter_cases = 0;
    for (rate, f0, q, gain, label) in invalid {
        for kind in [Kind::Peaking, Kind::LowShelf] {
            let mut filter = warmed_filter();
            let state = filter.state().to_bits();
            let coefficients = filter.coefficients().to_bits();
            let (constructed, set) = match kind {
                Kind::Peaking => (
                    Biquad::peaking(rate, f0, q, gain).err(),
                    filter.set_peaking(rate, f0, q, gain),
                ),
                Kind::LowShelf => (
                    Biquad::low_shelf(rate, f0, q, gain).err(),
                    filter.set_low_shelf(rate, f0, q, gain),
                ),
            };
            assert_eq!(
                constructed,
                Some(DspError::InvalidParameter),
                "{kind:?} {label}"
            );
            assert_eq!(set, Err(DspError::InvalidParameter), "{kind:?} {label}");
            assert_eq!(
                filter.state().to_bits(),
                state,
                "{kind:?} {label}: state changed"
            );
            assert_eq!(
                filter.coefficients().to_bits(),
                coefficients,
                "{kind:?} {label}: coefficients changed"
            );
            parameter_cases += 1;
        }
    }

    // A refused call followed by an identical valid call matches an untouched twin.
    let mut refused = warmed_filter();
    let mut twin = warmed_filter();
    let _ = refused.process(&mut [1.0, f32::NAN]);
    let mut a = [0.1f32, 0.2, -0.3];
    let mut b = a;
    refused.process(&mut a).unwrap();
    twin.process(&mut b).unwrap();
    assert_eq!(bits32(&a), bits32(&b));

    let mut meter_cases = 0;
    let mut meter = PeakRms::new();
    meter.process(&[0.5, -0.25]).unwrap();
    for (label, block, expected) in [
        (
            "meter oversized",
            vec![0.25f32; MAX_BLOCK_SAMPLES + 1],
            DspError::BlockTooLarge,
        ),
        (
            "meter NaN last",
            vec![0.25f32, f32::NAN],
            DspError::NonFiniteSample,
        ),
        (
            "meter Inf last",
            vec![0.25f32, f32::INFINITY],
            DspError::NonFiniteSample,
        ),
    ] {
        let before = meter.to_bits();
        assert_eq!(meter.process(&block), Err(expected), "{label}");
        assert_eq!(meter.to_bits(), before, "{label}: meter changed");
        meter_cases += 1;
    }
    let total = cases + parameter_cases + meter_cases;
    println!(
        "MEASURED M9 biquad_process_cases={cases} parameter_cases={parameter_cases} meter_cases={meter_cases} total={total}/{total}"
    );
    assert_eq!(total, 6 + 28 + 3);
}

// ---------------------------------------------------------------------------
// M10

#[test]
fn process_paths_do_not_allocate() {
    let mut peaking = Biquad::peaking(48_000.0, 300.0, 0.8, 1.0).unwrap();
    let mut shelf = Biquad::low_shelf(48_000.0, 100.0, 0.707, 3.0).unwrap();
    let mut meter = PeakRms::new();
    let mut block: Vec<f32> = (0..4096).map(|n| (n as f32 * 0.01).sin() * 0.5).collect();
    let mut counts = [usize::MAX; 4];

    let start = allocations();
    peaking.process(&mut block).unwrap();
    counts[0] = allocations() - start;

    let start = allocations();
    shelf.process(&mut block).unwrap();
    counts[1] = allocations() - start;

    let start = allocations();
    meter.process(&block).unwrap();
    counts[2] = allocations() - start;

    let start = allocations();
    apply_gain(&mut block, 0.5).unwrap();
    counts[3] = allocations() - start;

    // Sanity: the counter observes allocations on this thread.
    let start = allocations();
    let probe = std::hint::black_box(vec![0u8; 16]);
    assert!(allocations() > start);
    drop(probe);

    println!(
        "MEASURED M10 allocations peaking={} low_shelf={} peak_rms={} apply_gain={} zero_alloc={}/4",
        counts[0],
        counts[1],
        counts[2],
        counts[3],
        counts.iter().filter(|&&c| c == 0).count()
    );
    assert_eq!(counts, [0; 4]);
}

// ---------------------------------------------------------------------------
// M11 (optional): FFmpeg equalizer parity.

#[test]
#[ignore = "requires FFMPEG; run with --ignored ffmpeg_parity"]
fn ffmpeg_parity() {
    use std::io::Read;
    use std::process::{Command, Stdio};
    use std::time::{Duration, Instant};

    const N: usize = 4096;
    let Some(ffmpeg) = std::env::var_os("FFMPEG") else {
        println!("MEASURED M11 status=unmeasured reason=FFMPEG_unset");
        return;
    };
    let mut child = Command::new(ffmpeg)
        .args([
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=exprs=eq(n\\,0):s=44100:d=0.0928798185941043",
            "-af",
            "equalizer=f=300:t=q:w=0.8:g=1:b=0:r=f64",
            "-ac",
            "1",
            "-f",
            "f32le",
            "-",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn FFMPEG");
    let mut stdout = child.stdout.take().unwrap();
    let reader = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        stdout.read_to_end(&mut bytes).map(|_| bytes)
    });
    let deadline = Instant::now() + Duration::from_secs(30);
    let status = loop {
        if let Some(status) = child.try_wait().unwrap() {
            break status;
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            panic!("FFMPEG exceeded the 30 s deadline");
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    let bytes = reader.join().unwrap().unwrap();
    let mut stderr = String::new();
    let _ = child.stderr.take().unwrap().read_to_string(&mut stderr);
    assert!(status.success(), "ffmpeg failed: {stderr}");
    let theirs: Vec<f32> = bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect();
    assert!(
        theirs.len() >= N,
        "ffmpeg produced {} samples",
        theirs.len()
    );
    let mut ours = vec![0.0f32; N];
    ours[0] = 1.0;
    Biquad::peaking(44_100.0, 300.0, 0.8, 1.0)
        .unwrap()
        .process(&mut ours)
        .unwrap();
    let max_diff = ours
        .iter()
        .zip(&theirs[..N])
        .map(|(a, b)| (f64::from(*a) - f64::from(*b)).abs())
        .fold(0.0f64, f64::max);
    // Guard against a vacuous comparison (silent or truncated FFmpeg output).
    let energy: f64 = theirs[..N].iter().map(|v| f64::from(*v).powi(2)).sum();
    let nonzero = theirs[..N].iter().filter(|v| **v != 0.0).count();
    assert!(
        theirs[0] > 1.0 && energy > 1.0 && nonzero > N / 2,
        "degenerate FFmpeg output"
    );
    println!(
        "MEASURED M11 status=measured samples={N} max_abs_diff={max_diff:.3e} ffmpeg_samples={} ffmpeg_h0={:.9} ours_h0={:.9} ffmpeg_h1={:.9} ffmpeg_nonzero={nonzero} ffmpeg_energy={energy:.9}",
        theirs.len(),
        theirs[0],
        ours[0],
        theirs[1]
    );
    assert!(max_diff <= 1e-6, "FFmpeg parity max |diff| {max_diff:e}");
}
