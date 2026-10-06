//! Frozen S2 au_auval biquad ABI checks (docs/spec/sprints/AU_AUVAL_S2.md):
//! FFI-vs-Rust bit parity (150 cases), refusal atomicity (20 cases), the
//! count-0 positive case and render-call allocation counting (2048 calls).

use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

use video_utils::dsp::Biquad;
use video_utils_gain_ffi::*;

thread_local! {
    static TRACK: Cell<bool> = const { Cell::new(false) };
    static ALLOCATIONS: Cell<usize> = const { Cell::new(0) };
}

struct CountingAllocator;

fn note_allocation() {
    let _ = TRACK.try_with(|tracking| {
        if tracking.get() {
            let _ = ALLOCATIONS.try_with(|count| count.set(count.get() + 1));
        }
    });
}

// Counts Rust global-allocator calls on the measuring thread only. Raw malloc
// from foreign code is outside this counter's scope.
unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        note_allocation();
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        note_allocation();
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        unsafe { System.dealloc(pointer, layout) }
    }
    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        note_allocation();
        unsafe { System.realloc(pointer, layout, size) }
    }
}

#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

const LENGTH: usize = 48_000;
const RATES: [f64; 2] = [44_100.0, 48_000.0];
const C1_HZ: f64 = 32.703;

/// (kind, frequency Hz, Q, gain dB). The first two are the accepted FULLER
/// run's peaking_eq bands (applied-profile.json sha256 a1229c84...b826).
const CONFIGS: [(u32, f64, f64, f64); 5] = [
    (VU_BIQUAD_PEAKING, 160.0, 0.7, 2.0),
    (VU_BIQUAD_PEAKING, 300.0, 0.8, 1.0),
    (VU_BIQUAD_PEAKING, C1_HZ, 1.0, 3.0),
    (VU_BIQUAD_LOW_SHELF, 80.0, 0.707, 4.0),
    (VU_BIQUAD_PEAKING, 2500.0, 1.2, -3.0),
];

/// Numerical Recipes 32-bit LCG.
struct Lcg(u32);

impl Lcg {
    fn next(&mut self) -> u32 {
        self.0 = self.0.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
        self.0
    }
    /// `(u32 >> 8) / 2^24 * 2 - 1`, in f64.
    fn unit(&mut self) -> f64 {
        f64::from(self.next() >> 8) / 16_777_216.0 * 2.0 - 1.0
    }
}

fn signals(sample_rate: f64) -> Vec<(&'static str, Vec<f32>)> {
    let mut impulse = vec![0.0_f32; LENGTH];
    impulse[0] = 1.0;
    let sine = (0..LENGTH)
        .map(|n| (0.5 * (2.0 * std::f64::consts::PI * C1_HZ * n as f64 / sample_rate).sin()) as f32)
        .collect();
    let mut lcg = Lcg(20_261_006);
    let noise = (0..LENGTH).map(|_| (0.25 * lcg.unit()) as f32).collect();
    vec![
        ("impulse", impulse),
        ("sine_c1", sine),
        ("lcg_noise", noise),
    ]
}

fn partitions() -> Vec<(&'static str, Vec<usize>)> {
    let fixed = |size: usize| {
        let mut sizes = vec![size; LENGTH / size];
        if LENGTH % size != 0 {
            sizes.push(LENGTH % size);
        }
        sizes
    };
    let mut lcg = Lcg(20_261_007);
    let mut irregular = Vec::new();
    let mut remaining = LENGTH;
    while remaining > 0 {
        let size = (1 + (lcg.next() >> 8) as usize % 997).min(remaining);
        irregular.push(size);
        remaining -= size;
    }
    vec![
        ("single", vec![LENGTH]),
        ("fixed64", fixed(64)),
        ("fixed128", fixed(128)),
        ("fixed4096", fixed(4096)),
        ("irregular_1_997", irregular),
    ]
}

fn reference(kind: u32, rate: f64, f: f64, q: f64, db: f64) -> Biquad {
    match kind {
        VU_BIQUAD_PEAKING => Biquad::peaking(rate, f, q, db).unwrap(),
        _ => Biquad::low_shelf(rate, f, q, db).unwrap(),
    }
}

#[test]
fn ffi_matches_rust_biquad_bit_for_bit() {
    let partitions = partitions();
    let mut cases = 0;
    let mut identical = 0;
    for rate in RATES {
        for (signal_name, signal) in signals(rate) {
            for &(kind, f, q, db) in &CONFIGS {
                let mut expected = signal.clone();
                let mut rust = reference(kind, rate, f, q, db);
                rust.process(&mut expected).unwrap();
                for (partition_name, sizes) in &partitions {
                    cases += 1;
                    let mut filter = VuBiquad::zeroed();
                    let mut actual = signal.clone();
                    unsafe {
                        assert_eq!(vu_biquad_init(&mut filter, kind, rate, f, q, db), VU_BQ_OK);
                        let mut offset = 0;
                        for &size in sizes {
                            let code = vu_biquad_process(
                                &mut filter,
                                actual.as_mut_ptr().add(offset),
                                size as u32,
                            );
                            assert_eq!(code, VU_BQ_OK, "{signal_name} {partition_name}");
                            offset += size;
                        }
                        assert_eq!(offset, LENGTH);
                    }
                    let (state, coefficients) = biquad_slot_snapshot(&filter).unwrap();
                    let same_samples = actual
                        .iter()
                        .zip(&expected)
                        .all(|(a, b)| a.to_bits() == b.to_bits());
                    let same_state = state.to_bits() == rust.state().to_bits()
                        && coefficients.to_bits() == rust.coefficients().to_bits();
                    assert!(
                        same_samples && same_state,
                        "parity failed: rate {rate} signal {signal_name} config {kind}/{f}/{q}/{db} partition {partition_name}"
                    );
                    identical += 1;
                }
            }
        }
    }
    assert_eq!(cases, 150);
    assert_eq!(identical, 150);
}

fn initialized() -> VuBiquad {
    let mut filter = VuBiquad::zeroed();
    let mut warm = [0.25_f32, -0.125, 0.5, 0.0];
    unsafe {
        assert_eq!(
            vu_biquad_init(&mut filter, VU_BIQUAD_PEAKING, 48_000.0, 160.0, 0.7, 2.0),
            VU_BQ_OK
        );
        assert_eq!(
            vu_biquad_process(&mut filter, warm.as_mut_ptr(), 4),
            VU_BQ_OK
        );
    }
    filter
}

/// One refusal case: run `call` on (filter, samples) and require the code
/// plus bitwise-unchanged samples and slot.
fn refusal(
    name: &str,
    expected: i32,
    mut filter: VuBiquad,
    mut samples: Vec<f32>,
    call: impl FnOnce(*mut VuBiquad, *mut f32) -> i32,
) -> bool {
    let filter_before = filter;
    let samples_before: Vec<u32> = samples.iter().map(|value| value.to_bits()).collect();
    let code = call(&mut filter, samples.as_mut_ptr());
    let samples_after: Vec<u32> = samples.iter().map(|value| value.to_bits()).collect();
    let ok = code == expected && filter == filter_before && samples_after == samples_before;
    assert!(ok, "refusal {name}: code {code}, expected {expected}");
    ok
}

#[test]
fn refusals_are_atomic() {
    let fs = 48_000.0;
    let normal = || vec![0.25_f32, -0.5, 0.125, 0.0];
    let mut passed = 0;
    let mut total = 0;
    let mut check = |ok: bool| {
        total += 1;
        passed += usize::from(ok);
    };
    unsafe {
        // 1 NULL filter on process.
        check(refusal(
            "null_filter",
            VU_BQ_INVALID_POINTER,
            initialized(),
            normal(),
            |_, s| vu_biquad_process(std::ptr::null_mut(), s, 4),
        ));
        // 2 misaligned filter.
        let mut backing = [VuBiquad::zeroed(); 2];
        let misaligned = backing.as_mut_ptr().cast::<u8>().add(1).cast::<VuBiquad>();
        check(refusal(
            "misaligned_filter",
            VU_BQ_INVALID_POINTER,
            initialized(),
            normal(),
            |_, s| vu_biquad_process(misaligned, s, 4),
        ));
        assert!(backing.iter().all(|slot| *slot == VuBiquad::zeroed()));
        // 3 NULL samples with count 1.
        check(refusal(
            "null_samples",
            VU_BQ_INVALID_POINTER,
            initialized(),
            normal(),
            |f, _| vu_biquad_process(f, std::ptr::null_mut(), 1),
        ));
        // 4 misaligned samples.
        check(refusal(
            "misaligned_samples",
            VU_BQ_INVALID_POINTER,
            initialized(),
            normal(),
            |f, s| vu_biquad_process(f, s.cast::<u8>().add(1).cast::<f32>(), 2),
        ));
        // 5 count 65537.
        check(refusal(
            "count_65537",
            VU_BQ_BLOCK_TOO_LARGE,
            initialized(),
            normal(),
            |f, s| vu_biquad_process(f, s, 65_537),
        ));
        // 6-8 uninitialized (zeroed) slot on process, set, reset.
        check(refusal(
            "uninit_process",
            VU_BQ_UNINITIALIZED,
            VuBiquad::zeroed(),
            normal(),
            |f, s| vu_biquad_process(f, s, 4),
        ));
        check(refusal(
            "uninit_set",
            VU_BQ_UNINITIALIZED,
            VuBiquad::zeroed(),
            normal(),
            |f, _| vu_biquad_set(f, VU_BIQUAD_PEAKING, fs, 160.0, 0.7, 2.0),
        ));
        check(refusal(
            "uninit_reset",
            VU_BQ_UNINITIALIZED,
            VuBiquad::zeroed(),
            normal(),
            |f, _| vu_biquad_reset(f),
        ));
        // 9-10 non-finite samples.
        check(refusal(
            "nan_sample",
            VU_BQ_NON_FINITE_SAMPLE,
            initialized(),
            vec![0.25, f32::NAN, 0.125, 0.0],
            |f, s| vu_biquad_process(f, s, 4),
        ));
        check(refusal(
            "inf_sample",
            VU_BQ_NON_FINITE_SAMPLE,
            initialized(),
            vec![0.25, 0.5, f32::INFINITY, 0.0],
            |f, s| vu_biquad_process(f, s, 4),
        ));
        // 11 overflow: f32::MAX through a +24 dB peaking band.
        let mut hot = VuBiquad::zeroed();
        assert_eq!(
            vu_biquad_init(&mut hot, VU_BIQUAD_PEAKING, fs, 1000.0, 1.0, 24.0),
            VU_BQ_OK
        );
        check(refusal(
            "overflow",
            VU_BQ_OVERFLOW,
            hot,
            vec![0.25, f32::MAX, 0.0, 0.0],
            |f, s| vu_biquad_process(f, s, 4),
        ));
        // 12-19 init parameter refusals on an initialized, warmed slot.
        let init_cases: [(&str, u32, f64, f64, f64, f64); 8] = [
            ("f_zero", VU_BIQUAD_PEAKING, fs, 0.0, 0.7, 2.0),
            ("f_0_49_fs", VU_BIQUAD_PEAKING, fs, 0.49 * fs, 0.7, 2.0),
            ("q_0_05", VU_BIQUAD_PEAKING, fs, 160.0, 0.05, 2.0),
            ("gain_24_5", VU_BIQUAD_PEAKING, fs, 160.0, 0.7, 24.5),
            ("nan_rate", VU_BIQUAD_PEAKING, f64::NAN, 160.0, 0.7, 2.0),
            ("rate_7999", VU_BIQUAD_LOW_SHELF, 7_999.0, 80.0, 0.707, 4.0),
            ("kind_0", 0, fs, 160.0, 0.7, 2.0),
            ("kind_3_no_highpass", 3, fs, 80.0, 0.707, 0.0),
        ];
        for (name, kind, rate, f, q, db) in init_cases {
            check(refusal(
                name,
                VU_BQ_INVALID_PARAMETER,
                initialized(),
                normal(),
                |filter, _| vu_biquad_init(filter, kind, rate, f, q, db),
            ));
        }
        // 20 samples aliasing the slot storage.
        let mut aliased = initialized();
        let before = aliased;
        let inside = (&mut aliased as *mut VuBiquad)
            .cast::<u8>()
            .add(64)
            .cast::<f32>();
        let code = vu_biquad_process(&mut aliased, inside, 4);
        check(code == VU_BQ_ALIASED && aliased == before);
    }
    assert_eq!(total, 20);
    assert_eq!(passed, 20);
}

#[test]
fn zero_count_with_null_samples_is_ok_and_keeps_state() {
    let mut filter = initialized();
    let before = filter;
    let code = unsafe { vu_biquad_process(&mut filter, std::ptr::null_mut(), 0) };
    assert_eq!(code, VU_BQ_OK);
    assert_eq!(filter, before);
}

#[test]
fn set_keeps_delay_line_and_reset_zeroes_it() {
    let mut filter = initialized();
    let state = biquad_slot_snapshot(&filter).unwrap().0;
    unsafe {
        assert_eq!(
            vu_biquad_set(&mut filter, VU_BIQUAD_LOW_SHELF, 48_000.0, 80.0, 0.707, 4.0),
            VU_BQ_OK
        );
    }
    let (after, coefficients) = biquad_slot_snapshot(&filter).unwrap();
    assert_eq!(after.to_bits(), state.to_bits());
    let expected = Biquad::low_shelf(48_000.0, 80.0, 0.707, 4.0)
        .unwrap()
        .coefficients();
    assert_eq!(coefficients.to_bits(), expected.to_bits());
    let before = filter;
    unsafe {
        assert_eq!(
            vu_biquad_set(&mut filter, VU_BIQUAD_PEAKING, 48_000.0, 0.0, 0.7, 2.0),
            VU_BQ_INVALID_PARAMETER
        );
    }
    assert_eq!(filter, before);
    unsafe { assert_eq!(vu_biquad_reset(&mut filter), VU_BQ_OK) };
    assert_eq!(biquad_slot_snapshot(&filter).unwrap().0.to_bits(), [0; 4]);
}

#[test]
fn render_calls_do_not_allocate() {
    let source: Vec<f32> = (0..4096)
        .map(|n| (0.25 * (2.0 * std::f64::consts::PI * C1_HZ * n as f64 / 48_000.0).sin()) as f32)
        .collect();
    let mut block = source.clone();
    let mut filters = [VuBiquad::zeroed(), VuBiquad::zeroed()];
    unsafe {
        assert_eq!(
            vu_biquad_init(
                &mut filters[0],
                VU_BIQUAD_PEAKING,
                48_000.0,
                160.0,
                0.7,
                2.0
            ),
            VU_BQ_OK
        );
        assert_eq!(
            vu_biquad_init(
                &mut filters[1],
                VU_BIQUAD_LOW_SHELF,
                48_000.0,
                80.0,
                0.707,
                4.0
            ),
            VU_BQ_OK
        );
    }
    let mut calls = 0_usize;
    let mut failures = 0_usize;
    ALLOCATIONS.with(|count| count.set(0));
    for filter in filters.iter_mut() {
        for _ in 0..1024 {
            block.copy_from_slice(&source);
            TRACK.with(|tracking| tracking.set(true));
            let code = unsafe { vu_biquad_process(filter, block.as_mut_ptr(), 4096) };
            TRACK.with(|tracking| tracking.set(false));
            failures += usize::from(code != VU_BQ_OK);
            calls += 1;
        }
    }
    assert_eq!(calls, 2048);
    assert_eq!(failures, 0);
    assert_eq!(ALLOCATIONS.with(Cell::get), 0);
}
