#include "video_utils_gain.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdio.h>

int main(void) {
    assert(vu_gain_abi_version() == 1);
    assert(vu_gain_max_samples() == 65536);
    assert(vu_gain_process(NULL, 0, 1) == VU_OK);
    assert(vu_gain_process(NULL, 1, 1) == VU_INVALID_POINTER);
    assert(vu_gain_process(NULL, 65537, 1) == VU_BLOCK_TOO_LARGE);
    float storage[2] = {.25f, -.25f};
    assert(vu_gain_process((float *)((char *)storage + 1), 1, 1) == VU_INVALID_POINTER);
    assert(vu_gain_process(storage, 2, NAN) == VU_INVALID_GAIN);
    assert(storage[0] == .25f && storage[1] == -.25f);
    assert(vu_gain_process(storage, 2, 2) == VU_OK);
    assert(storage[0] == .5f && storage[1] == -.5f);
    storage[1] = INFINITY;
    assert(vu_gain_process(storage, 2, 2) == VU_NON_FINITE_SAMPLE);
    assert(storage[0] == .5f);
    storage[1] = FLT_MAX;
    assert(vu_gain_process(storage, 2, 2) == VU_OVERFLOW);
    assert(storage[0] == .5f && storage[1] == FLT_MAX);
    puts("{\"c_abi\":\"passed\",\"abi_version\":1}");
    return 0;
}
