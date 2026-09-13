#include <cstdio>
#include <cstdlib>
#include <random>
#include "Vtop.h"
#include "verilated.h"

// Drives 50k cycles of seeded random stimulus at the top level and relies on the bound-in SVA
// (rtl/sva/*.sv) to catch any weight-loading or psum-accumulation bug. A failing assertion
// executes $stop, which Verilator's VL_STOP_MT maps to gotError()/gotFinish() -- we poll that
// after every eval instead of scraping stderr.
static const int N = 4;

static void tick(Vtop* top) {
    top->clk = 0; top->eval();
    top->clk = 1; top->eval();
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Verilated::fatalOnError(false); // let $stop set gotFinish() instead of aborting the process
    Vtop* top = new Vtop;
    std::mt19937 rng(0xC0FFEE);
    std::uniform_int_distribution<int> byte8(-128, 127);
    std::uniform_int_distribution<int> pct(0, 99);

    top->rst = 1; top->weight_load = 0; top->act_in_flat = 0;
    for (int i = 0; i < 4; i++) top->weight_in_flat[i] = 0;
    tick(top);
    if (Verilated::gotFinish()) { printf("FAIL: assertion fired during initial reset\n"); return 1; }
    top->rst = 0;

    bool cover_hit = false;
    for (uint64_t cyc = 0; cyc < 50000; cyc++) {
        top->rst = (pct(rng) < 1) ? 1 : 0; // occasional mid-run reset pulse

        top->weight_load = (pct(rng) < 5) ? 1 : 0;
        uint32_t w_flat[4] = {0, 0, 0, 0};
        for (int i = 0; i < N * N; i++) {
            int bit = i * 8;
            w_flat[bit / 32] |= (uint32_t)(uint8_t)byte8(rng) << (bit % 32);
        }
        for (int i = 0; i < 4; i++) top->weight_in_flat[i] = w_flat[i];

        int8_t act[N];
        uint32_t act_flat = 0;
        for (int i = 0; i < N; i++) {
            act[i] = (int8_t)byte8(rng);
            act_flat |= (uint32_t)(uint8_t)act[i] << (i * 8);
        }
        top->act_in_flat = act_flat;

        // mirrors row 0's PE (a_in == act_in[r] directly), which drives WEIGHT_LOAD_WHILE_ACTIVE
        if (top->weight_load && !top->rst) {
            for (int i = 0; i < N; i++) if (act[i] != 0) cover_hit = true;
        }

        tick(top);

        if (Verilated::gotFinish()) {
            printf("FAIL: assertion fired at cycle %llu\n", (unsigned long long)cyc);
            delete top;
            return 1;
        }
    }

    if (!cover_hit) { printf("FAIL: WEIGHT_LOAD_WHILE_ACTIVE cover never hit\n"); return 1; }

    delete top;
    printf("PASS: 50000 cycles, no assertion failures, cover hit\n");
    return 0;
}
