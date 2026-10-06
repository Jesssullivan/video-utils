/* Frozen S2 au_auval C harness for video_utils_biquad.h (AU_AUVAL_S2.md
 * metric 5): layout, 9 status assertions and 30 bit-identical parity cases
 * against an independent C Direct Form I oracle. The oracle recomputes the
 * RBJ coefficients in C with the same evaluation order as src/dsp.rs; compile
 * with -ffp-contract=off so neither side fuses multiply-adds.
 */
#include "video_utils_biquad.h"
#include "video_utils_gain.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define LENGTH 48000
#define RATE 48000.0
#define C1_HZ 32.703

static const double PI_D = 3.14159265358979323846264338327950288;

typedef struct { double b0, b1, b2, a1, a2; } coeffs;
typedef struct { uint32_t kind; double f, q, db; } config;

static const config CONFIGS[5] = {
    {VU_BIQUAD_PEAKING, 160.0, 0.7, 2.0},
    {VU_BIQUAD_PEAKING, 300.0, 0.8, 1.0},
    {VU_BIQUAD_PEAKING, C1_HZ, 1.0, 3.0},
    {VU_BIQUAD_LOW_SHELF, 80.0, 0.707, 4.0},
    {VU_BIQUAD_PEAKING, 2500.0, 1.2, -3.0},
};

static coeffs design(const config *c, double fs) {
    double a = pow(10.0, c->db / 40.0);
    double w0 = 2.0 * PI_D * c->f / fs;
    double alpha = sin(w0) / (2.0 * c->q);
    double cos_w0 = cos(w0);
    coeffs out;
    if (c->kind == VU_BIQUAD_PEAKING) {
        double a0 = 1.0 + alpha / a;
        out.b0 = (1.0 + alpha * a) / a0;
        out.b1 = (-2.0 * cos_w0) / a0;
        out.b2 = (1.0 - alpha * a) / a0;
        out.a1 = (-2.0 * cos_w0) / a0;
        out.a2 = (1.0 - alpha / a) / a0;
    } else {
        double root_a_alpha = 2.0 * sqrt(a) * alpha;
        double a0 = (a + 1.0) + (a - 1.0) * cos_w0 + root_a_alpha;
        out.b0 = a * ((a + 1.0) - (a - 1.0) * cos_w0 + root_a_alpha) / a0;
        out.b1 = 2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0) / a0;
        out.b2 = a * ((a + 1.0) - (a - 1.0) * cos_w0 - root_a_alpha) / a0;
        out.a1 = -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0) / a0;
        out.a2 = ((a + 1.0) + (a - 1.0) * cos_w0 - root_a_alpha) / a0;
    }
    return out;
}

static void oracle(const coeffs *c, float *samples, int count) {
    double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (int n = 0; n < count; n++) {
        double x = (double)samples[n];
        double y = c->b0 * x + c->b1 * x1 + c->b2 * x2 - c->a1 * y1 - c->a2 * y2;
        x2 = x1; x1 = x; y2 = y1; y1 = y;
        samples[n] = (float)y;
    }
}

static uint32_t lcg_state;
static uint32_t lcg_next(void) {
    lcg_state = lcg_state * 1664525u + 1013904223u;
    return lcg_state;
}

static float input[LENGTH], expected[LENGTH], actual[LENGTH];
static int status_passed, status_total, parity_passed, parity_total;

static void status_check(int ok, const char *name) {
    status_total++;
    if (ok) status_passed++;
    else fprintf(stderr, "status assertion failed: %s\n", name);
}

static int run_partition(vu_biquad *filter, int partition) {
    int offset = 0;
    lcg_state = 20261007u;
    while (offset < LENGTH) {
        int size;
        if (partition == 0) size = LENGTH;
        else if (partition == 1) size = 128;
        else size = 1 + (int)((lcg_next() >> 8) % 997u);
        if (size > LENGTH - offset) size = LENGTH - offset;
        if (vu_biquad_process(filter, actual + offset, (uint32_t)size) != VU_BQ_OK) return 0;
        offset += size;
    }
    return 1;
}

int main(void) {
    /* Layout (not counted in the 39). */
    if (vu_biquad_storage_size() > sizeof(vu_biquad) || vu_biquad_storage_align() > _Alignof(vu_biquad)
        || sizeof(vu_biquad) != 128) {
        fprintf(stderr, "layout mismatch\n");
        return 1;
    }
    /* Nine status assertions. */
    vu_biquad filter;
    memset(&filter, 0, sizeof filter);
    float block[4] = {0.25f, -0.5f, 0.125f, 0.0f};
    status_check(vu_biquad_abi_version() == 1, "abi_version");
    status_check(vu_biquad_max_samples() == 65536, "max_samples");
    status_check(vu_biquad_process(NULL, block, 4) == VU_BQ_INVALID_POINTER, "null_filter");
    status_check(vu_biquad_process(&filter, block, 4) == VU_BQ_UNINITIALIZED, "uninitialized");
    status_check(vu_biquad_init(&filter, 3, RATE, 80.0, 0.707, 0.0) == VU_BQ_INVALID_PARAMETER, "kind3_no_highpass");
    status_check(vu_biquad_init(&filter, VU_BIQUAD_PEAKING, RATE, 160.0, 0.7, 2.0) == VU_BQ_OK, "init");
    status_check(vu_biquad_process(&filter, NULL, 0) == VU_BQ_OK, "count0_null");
    status_check(vu_biquad_process(&filter, block, 65537) == VU_BQ_BLOCK_TOO_LARGE, "count65537");
    block[1] = NAN;
    status_check(vu_biquad_process(&filter, block, 4) == VU_BQ_NON_FINITE_SAMPLE && block[0] == 0.25f,
                 "nan_atomic");
    /* Both headers coexist: the gain ABI is still linked and unchanged. */
    if (vu_gain_abi_version() != 1 || VU_OK != 0) return 1;

    /* 5 configs x 2 signals x 3 partitions = 30 parity cases at 48 kHz. */
    for (int signal = 0; signal < 2; signal++) {
        lcg_state = 20261006u;
        for (int n = 0; n < LENGTH; n++) {
            if (signal == 0) input[n] = (float)(0.5 * sin(2.0 * PI_D * C1_HZ * (double)n / RATE));
            else input[n] = (float)(0.25 * ((double)(lcg_next() >> 8) / 16777216.0 * 2.0 - 1.0));
        }
        for (int c = 0; c < 5; c++) {
            coeffs k = design(&CONFIGS[c], RATE);
            memcpy(expected, input, sizeof input);
            oracle(&k, expected, LENGTH);
            for (int partition = 0; partition < 3; partition++) {
                parity_total++;
                memcpy(actual, input, sizeof input);
                memset(&filter, 0, sizeof filter);
                int ok = vu_biquad_init(&filter, CONFIGS[c].kind, RATE, CONFIGS[c].f, CONFIGS[c].q,
                                        CONFIGS[c].db) == VU_BQ_OK
                         && run_partition(&filter, partition)
                         && memcmp(actual, expected, sizeof actual) == 0;
                if (ok) parity_passed++;
                else fprintf(stderr, "parity failed: signal %d config %d partition %d\n", signal, c, partition);
            }
        }
    }
    int passed = status_passed + parity_passed;
    int total = status_total + parity_total;
    printf("{\"c_biquad_abi\":\"%s\",\"abi_version\":1,\"storage_size\":%u,\"storage_align\":%u,"
           "\"status_assertions\":{\"passed\":%d,\"total\":%d},"
           "\"parity_cases\":{\"passed\":%d,\"total\":%d},\"passed\":%d,\"total\":%d,"
           "\"oracle\":\"independent C DF1 with C-computed RBJ coefficients, -ffp-contract=off\"}\n",
           passed == total && total == 39 ? "passed" : "failed", vu_biquad_storage_size(),
           vu_biquad_storage_align(), status_passed, status_total, parity_passed, parity_total, passed, total);
    return passed == total && total == 39 ? 0 : 1;
}
