#include <cstdio>
#include "Vtop.h"
#include "verilated.h"

// Loads an identity weight matrix, holds one activation vector steady, waits for the
// pipeline to fill, then checks psum_out[c] == act_in[c] (diagonal weights isolate each term).
static const int N = 4;

static void tick(Vtop* top) {
    top->clk = 0; top->eval();
    top->clk = 1; top->eval();
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vtop* top = new Vtop;

    // weight_in_flat/psum_out_flat are 128-bit (N*N*8 / N*32), Verilator packs them as uint32_t[4]
    top->rst = 1; top->weight_load = 0; top->act_in_flat = 0;
    for (int i = 0; i < 4; i++) top->weight_in_flat[i] = 0;
    tick(top);
    top->rst = 0;

    // identity weight matrix, byte per element, bit offset (i*N+i)*8
    for (int i = 0; i < N; i++) {
        int bit = (i * N + i) * 8;
        top->weight_in_flat[bit / 32] |= (uint32_t)1 << (bit % 32);
    }
    top->weight_load = 1;
    tick(top);
    top->weight_load = 0;
    for (int i = 0; i < 4; i++) top->weight_in_flat[i] = 0;

    int8_t act[N] = {1, 2, 3, 4};
    uint32_t act_flat = 0;
    for (int i = 0; i < N; i++) act_flat |= (uint32_t)(uint8_t)act[i] << (i * 8);
    top->act_in_flat = act_flat; // held steady, not pulsed, so output reaches steady state

    for (int i = 0; i < 2 * N; i++) tick(top);

    bool pass = true;
    for (int c = 0; c < N; c++) {
        int bit = c * 32;
        int32_t got = (int32_t)top->psum_out_flat[bit / 32];
        if (got != act[c]) {
            printf("FAIL: psum_out[%d] = %d, expected %d\n", c, got, act[c]);
            pass = false;
        }
    }

    delete top;
    if (pass) { printf("PASS\n"); return 0; }
    return 1;
}
