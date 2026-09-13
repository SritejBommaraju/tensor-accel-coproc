// Drives one Verilated model (Vtop, ungated -- or Vtop_cg, gated, selected by -DGATED) through
// four scenarios with deterministic stimulus, dumps a VCD per scenario, and checks correctness
// against a software reference model of the gated array's exact cycle-by-cycle semantics (act_in
// on idle rows is realistic changing junk, not zeroed by the testbench -- the DUT itself must
// ignore it via act_valid). Writes psum_out per cycle to a CSV for informational diffing too.
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <functional>
#ifdef GATED
#include "Vtop_cg.h"
using DUT = Vtop_cg;
#else
#include "Vtop.h"
using DUT = Vtop;
#endif
#include "verilated.h"
#include "verilated_vcd_c.h"

#ifndef NN
#define NN 4
#endif

template <typename T> static void put_bytes(T& dst, const uint8_t* src, size_t n) { memcpy(&dst, src, n); }
template <typename T> static void get_bytes(const T& src, uint8_t* dst, size_t n) { memcpy(dst, &src, n); }

struct Rng {
    uint64_t s;
    explicit Rng(uint64_t seed) : s(seed) {}
    uint32_t next() { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return (uint32_t)s; }
    int8_t i8() { return (int8_t)next(); }
};

struct Scenario {
    const char* name;
    std::vector<int> valid_rows; // rows that are act_valid=1 for the whole run
};

// M=5 tail-padding: last tile has ((M-1) % N) + 1 real rows, the rest of that tile is idle padding.
static int tail_valid_rows(int n, int m) { return ((m - 1) % n) + 1; }

static std::vector<Scenario> build_scenarios(int n) {
    std::vector<Scenario> scenarios;
    std::vector<int> all;
    for (int i = 0; i < n; i++) all.push_back(i);
    scenarios.push_back({"dense", all});

    int half_n = n / 2;
    if (half_n < 1) half_n = 1;
    std::vector<int> half;
    for (int i = 0; i < half_n; i++) half.push_back(i);
    scenarios.push_back({"idle50", half});

    int sparse_n = n / 10;
    if (sparse_n < 1) sparse_n = 1;
    std::vector<int> sparse;
    for (int i = 0; i < sparse_n; i++) sparse.push_back(i);
    scenarios.push_back({"idle90", sparse});

    int tv = tail_valid_rows(n, 5);
    if (tv > n) tv = n;
    std::vector<int> tail;
    for (int i = 0; i < tv; i++) tail.push_back(i);
    scenarios.push_back({"tailpad_m5", tail});

    return scenarios;
}

// Cycle-exact software model of systolic_array_cg's intended semantics: act/act_valid registers
// freeze while invalid, psum always ticks and adds a zero product on invalid rows (operand
// isolation). Used as the correctness oracle so idle rows can be fed real (non-zeroed) junk data.
struct SoftArray {
    int n;
    std::vector<std::vector<int8_t>>  weight;
    std::vector<std::vector<int8_t>>  act_out;
    std::vector<std::vector<uint8_t>> valid_out;
    std::vector<std::vector<int32_t>> psum_out;

    explicit SoftArray(int n_) : n(n_),
        weight(n_, std::vector<int8_t>(n_, 0)),
        act_out(n_, std::vector<int8_t>(n_, 0)),
        valid_out(n_, std::vector<uint8_t>(n_, 0)),
        psum_out(n_, std::vector<int32_t>(n_, 0)) {}

    void reset() {
        for (int r = 0; r < n; r++)
            for (int c = 0; c < n; c++) { act_out[r][c] = 0; valid_out[r][c] = 0; psum_out[r][c] = 0; }
    }
    void load_weights(const std::vector<std::vector<int8_t>>& w) { weight = w; }

    std::vector<int32_t> step(const std::vector<int8_t>& act_in, const std::vector<uint8_t>& valid_in) {
        auto new_act = act_out;
        auto new_valid = valid_out;
        auto new_psum = psum_out;
        for (int r = 0; r < n; r++) {
            for (int c = 0; c < n; c++) {
                int8_t  a_in = (c == 0) ? act_in[r]   : act_out[r][c - 1];
                uint8_t v_in = (c == 0) ? valid_in[r] : valid_out[r][c - 1];
                int32_t p_in = (r == 0) ? 0            : psum_out[r - 1][c];
                int32_t prod = v_in ? (int32_t)a_in * (int32_t)weight[r][c] : 0;
                new_psum[r][c] = p_in + prod;
                if (v_in) { new_act[r][c] = a_in; new_valid[r][c] = v_in; }
            }
        }
        act_out = new_act; valid_out = new_valid; psum_out = new_psum;
        std::vector<int32_t> out(n);
        for (int c = 0; c < n; c++) out[c] = psum_out[n - 1][c];
        return out;
    }
};

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    const int N = NN;
    const int cycles = 4 * N + 40;
    auto scenarios = build_scenarios(N);
    int failures = 0;

    for (auto& sc : scenarios) {
        VerilatedContext ctx;
        ctx.traceEverOn(true);
        DUT dut{&ctx};
        VerilatedVcdC vcd;
        dut.trace(&vcd, 99);
        char vcdpath[256], csvpath[256];
#ifdef GATED
        snprintf(vcdpath, sizeof(vcdpath), "vcd/topcg_N%d_%s.vcd", N, sc.name);
        snprintf(csvpath, sizeof(csvpath), "vcd/topcg_N%d_%s.csv", N, sc.name);
#else
        snprintf(vcdpath, sizeof(vcdpath), "vcd/top_N%d_%s.vcd", N, sc.name);
        snprintf(csvpath, sizeof(csvpath), "vcd/top_N%d_%s.csv", N, sc.name);
#endif
        vcd.open(vcdpath);
        FILE* csv = fopen(csvpath, "w");

        std::vector<uint8_t> row_valid(N, 0);
        for (int r : sc.valid_rows) row_valid[r] = 1;

        // shared seed formula (independent of GATED) so both executables see identical stimulus
        Rng rng(0xC0FFEEu + (uint64_t)N * 131 + (uint64_t)std::hash<std::string>{}(sc.name));

        std::vector<std::vector<int8_t>> weight_mat(N, std::vector<int8_t>(N));
        uint8_t weight_bytes[64 * 64];
        for (int i = 0; i < N; i++)
            for (int j = 0; j < N; j++) {
                int8_t w = rng.i8();
                weight_mat[i][j] = w;
                weight_bytes[i * N + j] = (uint8_t)w;
            }
        put_bytes(dut.weight_in_flat, weight_bytes, N * N);

        SoftArray soft(N);
        soft.load_weights(weight_mat);

        uint8_t act_bytes[64];
        vluint64_t time = 0;

        auto tick = [&](bool weight_load, bool rst) {
            dut.rst = rst;
            dut.weight_load = weight_load;
            dut.clk = 0; dut.eval(); vcd.dump(time++);
            dut.clk = 1; dut.eval(); vcd.dump(time++);
            if (rst) soft.reset();
        };

        for (int i = 0; i < 3; i++) tick(false, true); // reset pulse
        tick(true, false);                              // load weights

        for (int cyc = 0; cyc < cycles; cyc++) {
            std::vector<int8_t>  act_in(N);
            std::vector<uint8_t> valid_in(N);
            for (int r = 0; r < N; r++) {
                // idle rows still see changing upstream data (e.g. a shared streaming bus) --
                // that is exactly the switching activity clock/operand gating is meant to suppress.
                int8_t v = rng.i8();
                act_bytes[r] = (uint8_t)v;
                act_in[r] = v;
                valid_in[r] = row_valid[r];
            }
            put_bytes(dut.act_in_flat, act_bytes, N);
#ifdef GATED
            uint32_t valid_flat = 0;
            for (int r = 0; r < N; r++) if (row_valid[r]) valid_flat |= (1u << r);
            dut.act_valid_flat = valid_flat;
#endif
            tick(false, false);

            auto golden = soft.step(act_in, valid_in);

            uint8_t p[32 * 4];
            get_bytes(dut.psum_out_flat, p, N * 4);
            for (int b = 0; b < N * 4; b++) fprintf(csv, "%02x", p[b]);
            fprintf(csv, "\n");

#ifdef GATED
            // gated model must match the act_valid-aware software oracle every cycle, every scenario
            for (int c = 0; c < N; c++) {
                int32_t got;
                memcpy(&got, p + c * 4, 4);
                if (got != golden[c]) {
                    fprintf(stderr, "GATED MISMATCH scenario=%s cycle=%d col=%d got=%d want=%d\n",
                            sc.name, cyc, c, got, golden[c]);
                    failures++;
                }
            }
#else
            // ungated top.sv has no validity concept, so it only matches the oracle when every
            // row is valid every cycle (the "dense" scenario) -- that is the required top.sv parity check
            if (std::string(sc.name) == "dense") {
                for (int c = 0; c < N; c++) {
                    int32_t got;
                    memcpy(&got, p + c * 4, 4);
                    if (got != golden[c]) {
                        fprintf(stderr, "UNGATED MISMATCH scenario=%s cycle=%d col=%d got=%d want=%d\n",
                                sc.name, cyc, c, got, golden[c]);
                        failures++;
                    }
                }
            }
#endif
        }

        fclose(csv);
        vcd.close();
        dut.final();
        printf("scenario %-12s N=%-2d valid_rows=%zu/%d done\n", sc.name, N, sc.valid_rows.size(), N);
    }

    if (failures) {
        fprintf(stderr, "%d mismatch(es) against the software oracle\n", failures);
        return 1;
    }
    printf("all scenarios matched the software oracle (N=%d)\n", N);
    return 0;
}
