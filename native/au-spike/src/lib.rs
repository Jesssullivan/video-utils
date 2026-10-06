//! Versioned C boundaries for the existing, allocation-free gain primitive
//! (`video_utils_gain.h`) and the root crate's RBJ peaking/low-shelf biquad
//! (`video_utils_biquad.h`).
//!
//! Pointer validity and exclusive ownership remain the foreign caller's duty.
//! An exported C function cannot unwind into the host; release uses panic=abort.

use video_utils::dsp::{Biquad, BiquadCoefficients, DspError};
use video_utils::{GainError, MAX_BLOCK_SAMPLES, apply_gain};

pub const VU_OK: i32 = 0;
pub const VU_INVALID_POINTER: i32 = 1;
pub const VU_BLOCK_TOO_LARGE: i32 = 2;
pub const VU_INVALID_GAIN: i32 = 3;
pub const VU_NON_FINITE_SAMPLE: i32 = 4;
pub const VU_OVERFLOW: i32 = 5;

#[unsafe(no_mangle)]
pub extern "C" fn vu_gain_abi_version() -> u32 {
    1
}

#[unsafe(no_mangle)]
pub extern "C" fn vu_gain_max_samples() -> u32 {
    MAX_BLOCK_SAMPLES as u32
}

fn status(error: GainError) -> i32 {
    match error {
        GainError::BlockTooLarge => VU_BLOCK_TOO_LARGE,
        GainError::InvalidGain => VU_INVALID_GAIN,
        GainError::NonFiniteSample => VU_NON_FINITE_SAMPLE,
        GainError::Overflow => VU_OVERFLOW,
    }
}

/// Apply gain in place with no allocation, clipping, logging or locks.
///
/// # Safety
/// For nonzero `count`, `samples` must reference an aligned, writable allocation
/// holding at least `count` initialized floats. This allocation must remain live
/// and exclusively mutable for the call. Null is allowed only for zero count.
/// Detected validation errors leave the entire sample buffer unchanged.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vu_gain_process(samples: *mut f32, count: u32, gain: f32) -> i32 {
    let count = count as usize;
    if count > MAX_BLOCK_SAMPLES {
        return VU_BLOCK_TOO_LARGE;
    }
    if count == 0 {
        return apply_gain(&mut [], gain).map_or_else(status, |()| VU_OK);
    }
    if samples.is_null() || !(samples as usize).is_multiple_of(std::mem::align_of::<f32>()) {
        return VU_INVALID_POINTER;
    }
    // SAFETY: The foreign caller provides live initialized, exclusively mutable
    // storage. Bounds/alignment above reject detectable malformed arguments.
    let buffer = unsafe { std::slice::from_raw_parts_mut(samples, count) };
    apply_gain(buffer, gain).map_or_else(status, |()| VU_OK)
}

// ---------------------------------------------------------------------------
// Biquad ABI version 1 (`include/video_utils_biquad.h`).
//
// The filter itself is `video_utils::dsp::Biquad`; nothing here reimplements
// it. There is deliberately no high-pass, low-cut or notch kind, so this ABI
// cannot remove the ~32.7 Hz C1 fundamental of the nine-string by construction.
// ---------------------------------------------------------------------------

pub const VU_BQ_OK: i32 = 0;
pub const VU_BQ_INVALID_POINTER: i32 = 1;
pub const VU_BQ_BLOCK_TOO_LARGE: i32 = 2;
pub const VU_BQ_INVALID_PARAMETER: i32 = 3;
pub const VU_BQ_NON_FINITE_SAMPLE: i32 = 4;
pub const VU_BQ_OVERFLOW: i32 = 5;
pub const VU_BQ_UNINITIALIZED: i32 = 6;
pub const VU_BQ_ALIASED: i32 = 7;
pub const VU_BQ_INTERNAL_PANIC: i32 = 8;

pub const VU_BIQUAD_PEAKING: u32 = 1;
pub const VU_BIQUAD_LOW_SHELF: u32 = 2;
pub const VU_BIQUAD_ABI_VERSION: u32 = 1;
pub const VU_BIQUAD_STORAGE_WORDS: usize = 16;
/// "VUBQ" plus ABI version; written last by a successful init only.
pub const VU_BIQUAD_MAGIC: u64 = 0x5655_4251_0000_0001;

/// Caller-preallocated opaque storage (128 bytes, 8-byte aligned). Mirrors
/// `vu_biquad` in the C header. Foreign callers must not interpret the words.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct VuBiquad {
    pub opaque: [u64; VU_BIQUAD_STORAGE_WORDS],
}

impl VuBiquad {
    pub const fn zeroed() -> Self {
        Self {
            opaque: [0; VU_BIQUAD_STORAGE_WORDS],
        }
    }
}

/// Rust view of the opaque storage. Every field is plain numeric data
/// (`Biquad` holds only `f64`), so any bit pattern, including all-zero
/// storage, is a valid value; validity is tracked by `magic`/`kind`/`abi`.
#[repr(C)]
struct Slot {
    magic: u64,
    kind: u32,
    abi: u32,
    biquad: Biquad,
}

const _: () = {
    assert!(std::mem::size_of::<Slot>() <= std::mem::size_of::<VuBiquad>());
    assert!(std::mem::align_of::<Slot>() <= 8);
    assert!(std::mem::size_of::<VuBiquad>() == 128);
    assert!(std::mem::align_of::<VuBiquad>() == 8);
};

fn bq_status(error: DspError) -> i32 {
    match error {
        DspError::BlockTooLarge => VU_BQ_BLOCK_TOO_LARGE,
        DspError::InvalidParameter => VU_BQ_INVALID_PARAMETER,
        DspError::NonFiniteSample => VU_BQ_NON_FINITE_SAMPLE,
        DspError::Overflow => VU_BQ_OVERFLOW,
    }
}

/// Run an exported body without letting a panic cross the C ABI. Under the
/// release profile (`panic = "abort"`) a panic aborts before reaching here;
/// under an unwind profile it is caught and reported. No allocation occurs on
/// the non-panic path.
#[inline(always)]
fn guarded(body: impl FnOnce() -> i32) -> i32 {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(body)).unwrap_or(VU_BQ_INTERNAL_PANIC)
}

fn filter_pointer_ok(filter: *const VuBiquad) -> bool {
    !filter.is_null() && (filter as usize) % std::mem::align_of::<VuBiquad>() == 0
}

fn coefficients(
    kind: u32,
    sample_rate: f64,
    frequency: f64,
    q: f64,
    gain_db: f64,
) -> Result<BiquadCoefficients, i32> {
    match kind {
        VU_BIQUAD_PEAKING => BiquadCoefficients::peaking(sample_rate, frequency, q, gain_db),
        VU_BIQUAD_LOW_SHELF => BiquadCoefficients::low_shelf(sample_rate, frequency, q, gain_db),
        _ => return Err(VU_BQ_INVALID_PARAMETER),
    }
    .map_err(bq_status)
}

fn slot_initialized(slot: &Slot) -> bool {
    slot.magic == VU_BIQUAD_MAGIC
        && slot.abi == VU_BIQUAD_ABI_VERSION
        && matches!(slot.kind, VU_BIQUAD_PEAKING | VU_BIQUAD_LOW_SHELF)
}

#[cfg(test)]
thread_local! {
    /// Unit-test-only fault hook: forces a panic inside the guarded process
    /// body after validation and before any mutation.
    static INJECT_PROCESS_PANIC: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}

#[unsafe(no_mangle)]
pub extern "C" fn vu_biquad_abi_version() -> u32 {
    VU_BIQUAD_ABI_VERSION
}

#[unsafe(no_mangle)]
pub extern "C" fn vu_biquad_max_samples() -> u32 {
    MAX_BLOCK_SAMPLES as u32
}

#[unsafe(no_mangle)]
pub extern "C" fn vu_biquad_storage_size() -> u32 {
    std::mem::size_of::<Slot>() as u32
}

#[unsafe(no_mangle)]
pub extern "C" fn vu_biquad_storage_align() -> u32 {
    std::mem::align_of::<Slot>() as u32
}

/// Validate parameters and write a fresh slot with a zero delay line.
///
/// # Safety
/// `filter` must reference live, writable, exclusively owned `vu_biquad`
/// storage. On any error the storage is bitwise unchanged.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vu_biquad_init(
    filter: *mut VuBiquad,
    kind: u32,
    sample_rate: f64,
    frequency: f64,
    q: f64,
    gain_db: f64,
) -> i32 {
    guarded(|| {
        if !filter_pointer_ok(filter) {
            return VU_BQ_INVALID_POINTER;
        }
        let coefficients = match coefficients(kind, sample_rate, frequency, q, gain_db) {
            Ok(value) => value,
            Err(code) => return code,
        };
        let slot = filter.cast::<Slot>();
        // SAFETY: aligned, non-null caller storage of at least size_of::<Slot>()
        // bytes (compile-time asserted). Fields are written individually and
        // `magic` last; all field types accept any bit pattern.
        unsafe {
            std::ptr::addr_of_mut!((*slot).kind).write(kind);
            std::ptr::addr_of_mut!((*slot).abi).write(VU_BIQUAD_ABI_VERSION);
            std::ptr::addr_of_mut!((*slot).biquad).write(Biquad::new(coefficients));
            std::ptr::addr_of_mut!((*slot).magic).write(VU_BIQUAD_MAGIC);
        }
        VU_BQ_OK
    })
}

/// Retune an initialized slot, keeping its delay line.
///
/// # Safety
/// As `vu_biquad_init`; never call concurrently with `vu_biquad_process` on
/// the same storage. On any error the storage is bitwise unchanged.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vu_biquad_set(
    filter: *mut VuBiquad,
    kind: u32,
    sample_rate: f64,
    frequency: f64,
    q: f64,
    gain_db: f64,
) -> i32 {
    guarded(|| {
        if !filter_pointer_ok(filter) {
            return VU_BQ_INVALID_POINTER;
        }
        // SAFETY: aligned, non-null, exclusively owned caller storage; every
        // bit pattern is a valid `Slot`.
        let slot = unsafe { &mut *filter.cast::<Slot>() };
        if !slot_initialized(slot) {
            return VU_BQ_UNINITIALIZED;
        }
        let result = match kind {
            VU_BIQUAD_PEAKING => slot.biquad.set_peaking(sample_rate, frequency, q, gain_db),
            VU_BIQUAD_LOW_SHELF => slot
                .biquad
                .set_low_shelf(sample_rate, frequency, q, gain_db),
            _ => return VU_BQ_INVALID_PARAMETER,
        };
        match result {
            Ok(()) => {
                slot.kind = kind;
                VU_BQ_OK
            }
            Err(error) => bq_status(error),
        }
    })
}

/// Zero the delay line of an initialized slot; coefficients are kept.
///
/// # Safety
/// As `vu_biquad_set`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vu_biquad_reset(filter: *mut VuBiquad) -> i32 {
    guarded(|| {
        if !filter_pointer_ok(filter) {
            return VU_BQ_INVALID_POINTER;
        }
        // SAFETY: as in `vu_biquad_set`.
        let slot = unsafe { &mut *filter.cast::<Slot>() };
        if !slot_initialized(slot) {
            return VU_BQ_UNINITIALIZED;
        }
        slot.biquad.reset();
        VU_BQ_OK
    })
}

/// Filter `count` samples in place through `video_utils::dsp::Biquad::process`.
///
/// Render-thread safe: no allocation, lock, I/O, logging or syscall. Check
/// order: filter pointer, count bound, zero count (NULL samples allowed),
/// samples pointer, aliasing with the filter storage, initialization. Every
/// error leaves samples and slot bitwise unchanged.
///
/// # Safety
/// `filter` as in `vu_biquad_set`. For nonzero `count`, `samples` must
/// reference `count` initialized, aligned, writable floats exclusively owned
/// for the call. Invalid or dangling foreign pointers cannot be detected.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vu_biquad_process(
    filter: *mut VuBiquad,
    samples: *mut f32,
    count: u32,
) -> i32 {
    guarded(|| {
        if !filter_pointer_ok(filter) {
            return VU_BQ_INVALID_POINTER;
        }
        let count = count as usize;
        if count > MAX_BLOCK_SAMPLES {
            return VU_BQ_BLOCK_TOO_LARGE;
        }
        if count == 0 {
            return VU_BQ_OK;
        }
        if samples.is_null() || (samples as usize) % std::mem::align_of::<f32>() != 0 {
            return VU_BQ_INVALID_POINTER;
        }
        let sample_start = samples as usize;
        let Some(sample_end) = count
            .checked_mul(std::mem::size_of::<f32>())
            .and_then(|bytes| sample_start.checked_add(bytes))
        else {
            return VU_BQ_INVALID_POINTER;
        };
        let filter_start = filter as usize;
        let Some(filter_end) = filter_start.checked_add(std::mem::size_of::<VuBiquad>()) else {
            return VU_BQ_INVALID_POINTER;
        };
        if sample_start < filter_end && filter_start < sample_end {
            return VU_BQ_ALIASED;
        }
        // SAFETY: aligned, non-null, exclusively owned storage that does not
        // overlap the sample range (checked above); every bit pattern is valid.
        let slot = unsafe { &mut *filter.cast::<Slot>() };
        if !slot_initialized(slot) {
            return VU_BQ_UNINITIALIZED;
        }
        #[cfg(test)]
        if INJECT_PROCESS_PANIC.with(std::cell::Cell::get) {
            panic!("injected unit-test fault before mutation");
        }
        // SAFETY: the caller provides live, initialized, exclusively mutable
        // storage for `count` floats; detectable malformed arguments and
        // overlap with the filter storage were rejected above.
        let buffer = unsafe { std::slice::from_raw_parts_mut(samples, count) };
        match slot.biquad.process(buffer) {
            Ok(()) => VU_BQ_OK,
            Err(error) => bq_status(error),
        }
    })
}

/// Test/diagnostic accessor (not part of the C ABI): the delay line and
/// coefficients of an initialized slot, or `None` when uninitialized.
#[doc(hidden)]
pub fn biquad_slot_snapshot(
    filter: &VuBiquad,
) -> Option<(video_utils::dsp::BiquadState, BiquadCoefficients)> {
    // SAFETY: `VuBiquad` is 8-aligned and at least as large as `Slot`, and
    // every bit pattern is a valid `Slot`.
    let slot = unsafe { &*(filter as *const VuBiquad).cast::<Slot>() };
    slot_initialized(slot).then(|| (slot.biquad.state(), slot.biquad.coefficients()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::cell::Cell;

    thread_local! {
        static TRACK: Cell<bool> = const { Cell::new(false) };
        static ALLOCATIONS: Cell<usize> = const { Cell::new(0) };
    }

    struct CountingAllocator;

    // Count allocations on the current test thread only. Preparation and test
    // harness allocations are excluded from the measured process calls.
    unsafe impl GlobalAlloc for CountingAllocator {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            let _ = TRACK.try_with(|tracking| {
                if tracking.get() {
                    let _ = ALLOCATIONS.try_with(|count| count.set(count.get() + 1));
                }
            });
            unsafe { System.alloc(layout) }
        }
        unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
            unsafe { System.dealloc(pointer, layout) }
        }
        unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            let _ = TRACK.try_with(|tracking| {
                if tracking.get() {
                    let _ = ALLOCATIONS.try_with(|count| count.set(count.get() + 1));
                }
            });
            unsafe { System.realloc(pointer, layout, size) }
        }
    }

    #[global_allocator]
    static ALLOCATOR: CountingAllocator = CountingAllocator;

    #[test]
    fn pointer_and_bounds_contract() {
        assert_eq!(vu_gain_abi_version(), 1);
        assert_eq!(vu_gain_max_samples(), 65_536);
        unsafe {
            assert_eq!(vu_gain_process(std::ptr::null_mut(), 0, 1.0), VU_OK);
            assert_eq!(
                vu_gain_process(std::ptr::null_mut(), 1, 1.0),
                VU_INVALID_POINTER
            );
            assert_eq!(
                vu_gain_process(std::ptr::null_mut(), 65_537, 1.0),
                VU_BLOCK_TOO_LARGE
            );
            let mut backing = [0.0_f32; 2];
            let misaligned = backing.as_mut_ptr().cast::<u8>().add(1).cast::<f32>();
            assert_eq!(vu_gain_process(misaligned, 1, 1.0), VU_INVALID_POINTER);
        }
    }

    #[test]
    fn finite_validation_is_atomic() {
        let mut bad_sample = [0.25, f32::INFINITY];
        let mut overflowing = [0.25, f32::MAX];
        let mut normal = [0.25, -0.25];
        unsafe {
            assert_eq!(
                vu_gain_process(bad_sample.as_mut_ptr(), 2, 2.0),
                VU_NON_FINITE_SAMPLE
            );
            assert_eq!(
                vu_gain_process(overflowing.as_mut_ptr(), 2, 2.0),
                VU_OVERFLOW
            );
            assert_eq!(
                vu_gain_process(normal.as_mut_ptr(), 2, f32::NAN),
                VU_INVALID_GAIN
            );
            assert_eq!(vu_gain_process(normal.as_mut_ptr(), 2, 2.0), VU_OK);
        }
        assert_eq!(bad_sample[0], 0.25);
        assert_eq!(overflowing, [0.25, f32::MAX]);
        assert_eq!(normal, [0.5, -0.5]);
    }

    #[test]
    fn render_sized_calls_do_not_allocate() {
        let mut samples = [0.25_f32; 8192];
        ALLOCATIONS.with(|count| count.set(0));
        TRACK.with(|tracking| tracking.set(true));
        let mut failure = false;
        for _ in 0..1024 {
            failure |= unsafe { vu_gain_process(samples.as_mut_ptr(), samples.len() as u32, 1.0) }
                != VU_OK;
        }
        TRACK.with(|tracking| tracking.set(false));
        assert!(!failure);
        assert_eq!(ALLOCATIONS.with(Cell::get), 0);
    }

    #[test]
    fn caught_panic_returns_internal_panic_and_leaves_slot_unchanged() {
        let mut filter = VuBiquad::zeroed();
        let mut samples = [0.25_f32, -0.5, 0.125, 0.0];
        unsafe {
            assert_eq!(
                vu_biquad_init(&mut filter, VU_BIQUAD_PEAKING, 48_000.0, 160.0, 0.7, 2.0),
                VU_BQ_OK
            );
            assert_eq!(
                vu_biquad_process(&mut filter, samples.as_mut_ptr(), 4),
                VU_BQ_OK
            );
        }
        let slot_before = filter;
        let samples_before = samples.map(f32::to_bits);
        let previous_hook = std::panic::take_hook();
        std::panic::set_hook(Box::new(|_| {}));
        INJECT_PROCESS_PANIC.with(|flag| flag.set(true));
        let code = unsafe { vu_biquad_process(&mut filter, samples.as_mut_ptr(), 4) };
        INJECT_PROCESS_PANIC.with(|flag| flag.set(false));
        std::panic::set_hook(previous_hook);
        assert_eq!(code, VU_BQ_INTERNAL_PANIC);
        assert_eq!(filter, slot_before);
        assert_eq!(samples.map(f32::to_bits), samples_before);
        // The slot remains usable after the caught panic.
        assert_eq!(
            unsafe { vu_biquad_process(&mut filter, samples.as_mut_ptr(), 4) },
            VU_BQ_OK
        );
    }

    #[test]
    fn biquad_layout_and_versions() {
        assert_eq!(vu_biquad_abi_version(), 1);
        assert_eq!(vu_biquad_max_samples(), 65_536);
        assert!(vu_biquad_storage_size() as usize <= std::mem::size_of::<VuBiquad>());
        assert!(vu_biquad_storage_align() as usize <= std::mem::align_of::<VuBiquad>());
        assert!(biquad_slot_snapshot(&VuBiquad::zeroed()).is_none());
    }
}
