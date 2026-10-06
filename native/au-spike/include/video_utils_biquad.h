#ifndef VIDEO_UTILS_BIQUAD_H
#define VIDEO_UTILS_BIQUAD_H

/* Biquad ABI version 1: the root crate's RBJ peaking / low-shelf Direct Form I
 * biquad (f64 coefficients and delay line, f32 samples), one instance per
 * planar channel. The filter is video_utils::dsp::Biquad; this header only
 * exposes it. There is deliberately no high-pass, low-cut or notch kind, so
 * the ABI cannot remove the ~32.7 Hz C1 fundamental by construction. Not
 * adopted by the AU render callback, GainKernel or any profile/master.
 *
 * Status codes use a VU_BQ_ prefix so this header and video_utils_gain.h can
 * be included together.
 */

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define VU_BIQUAD_STORAGE_WORDS 16

/* Caller-preallocated opaque storage: 128 bytes, 8-byte aligned. It must be
 * zero-initialized or initialized by vu_biquad_init before other calls. The
 * caller must not interpret or modify the words. The library never allocates.
 */
typedef struct vu_biquad {
    uint64_t opaque[VU_BIQUAD_STORAGE_WORDS];
} vu_biquad;

enum vu_biquad_kind {
    VU_BIQUAD_PEAKING = 1,
    VU_BIQUAD_LOW_SHELF = 2
};

enum vu_biquad_status {
    VU_BQ_OK = 0,
    VU_BQ_INVALID_POINTER = 1,   /* NULL/misaligned filter; NULL/misaligned samples with count > 0 */
    VU_BQ_BLOCK_TOO_LARGE = 2,   /* count > vu_biquad_max_samples() */
    VU_BQ_INVALID_PARAMETER = 3, /* out-of-range/non-finite parameter or unknown kind */
    VU_BQ_NON_FINITE_SAMPLE = 4,
    VU_BQ_OVERFLOW = 5,          /* output would be non-finite */
    VU_BQ_UNINITIALIZED = 6,     /* set/reset/process on storage not initialized by vu_biquad_init */
    VU_BQ_ALIASED = 7,           /* sample range overlaps the filter storage (detectable aliasing only) */
    VU_BQ_INTERNAL_PANIC = 8     /* caught Rust panic; reachable only in unwind (test) builds */
};

uint32_t vu_biquad_abi_version(void);  /* returns 1 */
uint32_t vu_biquad_max_samples(void);  /* returns 65536 */
uint32_t vu_biquad_storage_size(void); /* real Rust slot size, <= sizeof(vu_biquad) */
uint32_t vu_biquad_storage_align(void);/* real Rust slot alignment, <= _Alignof(vu_biquad) */

/* Parameter bounds (src/dsp.rs): 8000 <= sample_rate <= 384000 Hz,
 * 0 < frequency < 0.49 * sample_rate, 0.1 <= q <= 40, |gain_db| <= 24.
 *
 * Control thread. Validates, then writes a fresh slot with a zero delay line.
 * On error the storage is bitwise unchanged. */
int32_t vu_biquad_init(vu_biquad *filter, uint32_t kind, double sample_rate,
                       double frequency, double q, double gain_db);

/* Control thread, never concurrent with vu_biquad_process on the same storage.
 * Retunes an initialized slot and keeps the delay line. Atomic on error. */
int32_t vu_biquad_set(vu_biquad *filter, uint32_t kind, double sample_rate,
                      double frequency, double q, double gain_db);

/* Control thread. Zeroes the delay line of an initialized slot only. */
int32_t vu_biquad_reset(vu_biquad *filter);

/* Render thread. Filters count samples in place; no allocation, lock, I/O,
 * logging or syscall. Check order: filter pointer, count bound, count == 0
 * (returns VU_BQ_OK, NULL samples allowed), samples pointer, aliasing,
 * initialization. Every error leaves samples and slot bitwise unchanged.
 *
 * The caller owns valid, initialized, aligned writable sample storage with
 * exclusive access for the call. Invalid or dangling foreign pointers cannot
 * be made safe by these checks. */
int32_t vu_biquad_process(vu_biquad *filter, float *samples, uint32_t count);

#ifdef __cplusplus
}
#endif
#endif
