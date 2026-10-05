#ifndef VIDEO_UTILS_GAIN_H
#define VIDEO_UTILS_GAIN_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum vu_gain_status {
    VU_OK = 0,
    VU_INVALID_POINTER = 1,
    VU_BLOCK_TOO_LARGE = 2,
    VU_INVALID_GAIN = 3,
    VU_NON_FINITE_SAMPLE = 4,
    VU_OVERFLOW = 5
};

uint32_t vu_gain_abi_version(void);
uint32_t vu_gain_max_samples(void);

/* Version 1: finite gain in [0,16], maximum 65536 samples per call.
 * The caller owns valid, initialized, aligned writable storage with exclusive
 * access. NULL is allowed only when count==0. No allocation or clipping occurs.
 * Every detected error leaves the entire sample buffer unchanged. Invalid or
 * dangling foreign pointers cannot be made safe by these checks.
 */
int32_t vu_gain_process(float *samples, uint32_t count, float gain);

#ifdef __cplusplus
}
#endif
#endif
