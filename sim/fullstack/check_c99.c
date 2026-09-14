/* Proves sw/coproc_driver.h + sw/int8_mlp.h are portable, warning-clean C99 (also compiles as
 * C++): plain translation unit, no Verilator/TB headers, bare-metal ops path only. */
#define COPROC_BAREMETAL
#include "../../sw/coproc_driver.h"
#include "../../sw/int8_mlp.h"

int main(void) {
    coproc_buffers bufs;
    int i;
    for (i = 0; i < COPROC_QDEPTH; i++) {
        bufs.w_base[i] = (uint64_t)i * 16;
        bufs.a_base[i] = (uint64_t)i * 4096 + 1024;
        bufs.c_base[i] = (uint64_t)i * 16384;
    }

    int8_t x[MLP_IN] = {0};
    int32_t logits[MLP_OUT] = {0};
    int8_t W1[MLP_IN * MLP_HIDDEN] = {0};
    int32_t b1[MLP_HIDDEN] = {0};
    int8_t W2[MLP_HIDDEN * MLP_OUT] = {0};
    int32_t b2[MLP_OUT] = {0};
    int8_mlp_weights wt;
    wt.W1_i8 = W1; wt.b1_i32 = b1; wt.W2_i8 = W2; wt.b2_i32 = b2;
    wt.M0_1 = 1; wt.shift_1 = 0;

    (void)bufs; (void)x; (void)logits; (void)wt;
    (void)int8_mlp_argmax(logits);
    (void)int8_mlp_requant(0, 1, 0);
    (void)int8_mlp_clip_relu(0);

    return 0;
}
