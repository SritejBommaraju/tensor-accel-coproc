// Persistent 4x4-tile server over the Verilator top module. Line protocol on stdin/stdout:
//   in:  "TILE <M>", then 16 int8 weights (row-major, one per line), then M lines of 4 int8 acts
//   out: M lines of 4 int32 results, then "END <cycles>"
// Loops until EOF. See sched/tiler.py for the skew/de-skew math this implements.
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <array>
#include "Vtop.h"
#include "verilated.h"

static const int TN = 4; // systolic array size (fixed via -GN=4)

static void tick(Vtop* top) {
    top->clk = 0; top->eval();
    top->clk = 1; top->eval();
}

static void set_weight_flat(Vtop* top, const int8_t w[TN][TN]) {
    for (int i = 0; i < 4; i++) top->weight_in_flat[i] = 0;
    for (int i = 0; i < TN; i++)
        for (int j = 0; j < TN; j++) {
            int bit = (i * TN + j) * 8;
            top->weight_in_flat[bit / 32] |= (uint32_t)(uint8_t)w[i][j] << (bit % 32);
        }
}

static void set_act(Vtop* top, const int8_t act[TN]) {
    uint32_t flat = 0;
    for (int i = 0; i < TN; i++) flat |= (uint32_t)(uint8_t)act[i] << (i * 8);
    top->act_in_flat = flat;
}

static int32_t read_psum(Vtop* top, int c) {
    int bit = c * 32;
    return (int32_t)top->psum_out_flat[bit / 32];
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vtop* top = new Vtop;

    char line[256];
    while (fgets(line, sizeof(line), stdin)) {
        int M;
        if (sscanf(line, "TILE %d", &M) != 1) continue;

        int8_t w[TN][TN];
        for (int i = 0; i < TN; i++)
            for (int j = 0; j < TN; j++) {
                int v;
                if (!fgets(line, sizeof(line), stdin)) return 1;
                sscanf(line, "%d", &v);
                w[i][j] = (int8_t)v;
            }

        std::vector<std::array<int8_t, TN>> acts(M);
        for (int m = 0; m < M; m++) {
            if (!fgets(line, sizeof(line), stdin)) return 1;
            int a0, a1, a2, a3;
            sscanf(line, "%d %d %d %d", &a0, &a1, &a2, &a3);
            acts[m] = {(int8_t)a0, (int8_t)a1, (int8_t)a2, (int8_t)a3};
        }

        // reset, then load the weight tile (both drain any prior job's pipeline garbage)
        int8_t zero_act[TN] = {0, 0, 0, 0};
        top->rst = 1; top->weight_load = 0; set_act(top, zero_act);
        for (int i = 0; i < 4; i++) top->weight_in_flat[i] = 0;
        tick(top);
        top->rst = 0;
        set_weight_flat(top, w);
        top->weight_load = 1;
        tick(top);
        top->weight_load = 0;

        std::vector<std::array<int32_t, TN>> results(M);
        int stream_ticks = M + 2 * (TN - 1) + 1;
        for (int j = 0; j < stream_ticks; j++) {
            int8_t a[TN];
            for (int r = 0; r < TN; r++) {
                int m = j - r;
                a[r] = (m >= 0 && m < M) ? acts[m][r] : (int8_t)0;
            }
            set_act(top, a);
            tick(top);
            for (int c = 0; c < TN; c++) {
                int m = j - (TN - 1) - c;
                if (m >= 0 && m < M) results[m][c] = read_psum(top, c);
            }
        }

        for (int m = 0; m < M; m++)
            printf("%d %d %d %d\n", results[m][0], results[m][1], results[m][2], results[m][3]);
        int cycles = 2 + stream_ticks;
        printf("END %d\n", cycles);
        fflush(stdout);
    }

    delete top;
    return 0;
}
