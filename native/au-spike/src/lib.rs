//! Versioned C boundary for the existing, allocation-free gain primitive.
//!
//! Pointer validity and exclusive ownership remain the foreign caller's duty.
//! An exported C function cannot unwind into the host; release uses panic=abort.

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
    if samples.is_null() || (samples as usize) % std::mem::align_of::<f32>() != 0 {
        return VU_INVALID_POINTER;
    }
    // SAFETY: The foreign caller provides live initialized, exclusively mutable
    // storage. Bounds/alignment above reject detectable malformed arguments.
    let buffer = unsafe { std::slice::from_raw_parts_mut(samples, count) };
    apply_gain(buffer, gain).map_or_else(status, |()| VU_OK)
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
}
