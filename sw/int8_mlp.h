// 784-64-10 quantized MLP inference on top of coproc_driver.h. Integer math mirrors
// sched/mnist/quantize.py's int8_forward/apply_requant bit-for-bit (int64 fixed-point,
// no floats). C99 (also valid C++).
#ifndef INT8_MLP_H
#define INT8_MLP_H

#include <stdint.h>
#include "coproc_driver.h"

#define MLP_IN     784
#define MLP_HIDDEN 64
#define MLP_OUT    10

typedef struct {
    const int8_t  *W1_i8;   // [MLP_IN][MLP_HIDDEN]
    const int32_t *b1_i32;  // [MLP_HIDDEN]
    const int8_t  *W2_i8;   // [MLP_HIDDEN][MLP_OUT]
    const int32_t *b2_i32;  // [MLP_OUT]
    int32_t M0_1;
    int32_t shift_1;
} int8_mlp_weights;

// round(acc * M0 / 2**31 * 2**shift) using pure int64 arithmetic, identical to
// sched/mnist/quantize.py::apply_requant (rs = 31 - shift branch and its rounding term).
static inline int64_t int8_mlp_requant(int32_t acc, int32_t M0, int32_t shift) {
    int64_t prod = (int64_t)acc * (int64_t)M0;
    int rs = 31 - shift;
    if (rs >= 0) {
        int64_t round_val = (rs > 0) ? ((int64_t)1 << (rs - 1)) : 0;
        return (prod + round_val) >> rs;
    }
    return prod << (-rs);
}

static inline int8_t int8_mlp_clip_relu(int64_t v) {
    if (v < 0) v = 0;
    if (v > 127) v = 127;
    return (int8_t)v;
}

// runs one 1x784 image through both layers; logits_i32[MLP_OUT] gets the raw (unrequantized)
// int32 layer-2 output, matching quantize.py::int8_forward's return value exactly.
static inline void int8_mlp_infer(const coproc_ops *ops, const int8_mlp_weights *wt,
                                   const int8_t x_i8[MLP_IN], int32_t logits_i32[MLP_OUT],
                                   const coproc_buffers *bufs) {
    int32_t acc1[MLP_HIDDEN];
    coproc_matmul_tiled(ops, x_i8, 1, MLP_IN, wt->W1_i8, MLP_HIDDEN, acc1, bufs);

    int8_t h_i8[MLP_HIDDEN];
    for (int j = 0; j < MLP_HIDDEN; j++) {
        int64_t r = int8_mlp_requant(acc1[j] + wt->b1_i32[j], wt->M0_1, wt->shift_1);
        h_i8[j] = int8_mlp_clip_relu(r);
    }

    int32_t acc2[MLP_OUT];
    coproc_matmul_tiled(ops, h_i8, 1, MLP_HIDDEN, wt->W2_i8, MLP_OUT, acc2, bufs);

    for (int c = 0; c < MLP_OUT; c++) logits_i32[c] = acc2[c] + wt->b2_i32[c];
}

static inline int int8_mlp_argmax(const int32_t logits_i32[MLP_OUT]) {
    int best = 0;
    for (int c = 1; c < MLP_OUT; c++)
        if (logits_i32[c] > logits_i32[best]) best = c;
    return best;
}

#endif // INT8_MLP_H
