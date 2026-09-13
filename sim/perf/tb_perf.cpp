// Utilization / MACs-per-cycle measurement harness over the unmodified rtl/top.sv.
// Separate from sim/tb_main.cpp so functional and perf testbenches never collide.
//
// Timing model (derived from the RTL, not assumed): with weight W stationary at PE(r,c)
// and activation row m fed into port act_in[r] at tick (m+r+1) (1-indexed ticks, row-skewed),
// output row m appears de-skewed as psum_out[c] at tick (m+N+c). A full run of M rows takes
// exactly M+2N-2 ticks (N-1 fill, M steady, N-1 drain) -- utilization = M/(M+2N-2).
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <random>
#include <vector>
#include "Vtop.h"
#include "verilated.h"
#include "metrics.h"

static constexpr int N = TB_N;

static void tick(Vtop* top) {
    top->clk = 0; top->eval();
    top->clk = 1; top->eval();
}

// Generic byte-level accessors: Verilator represents wide ports as scalar CData/IData/QData
// or as a contiguous little-endian word array (WData/VlWide) depending on width -- either
// way the port object is byte-addressable in-place, which is all we need.
template <typename T>
static void set_byte(T& field, int byte_idx, uint8_t val) {
    reinterpret_cast<uint8_t*>(&field)[byte_idx] = val;
}
template <typename T>
static uint8_t get_byte(const T& field, int byte_idx) {
    return reinterpret_cast<const uint8_t*>(&field)[byte_idx];
}

static void set_weight(Vtop* top, int8_t w[N][N]) {
    for (int r = 0; r < N; r++)
        for (int c = 0; c < N; c++)
            set_byte(top->weight_in_flat, r * N + c, (uint8_t)w[r][c]);
}

static void set_act(Vtop* top, int8_t act[N]) {
    for (int r = 0; r < N; r++) set_byte(top->act_in_flat, r, (uint8_t)act[r]);
}

static int32_t get_psum(Vtop* top, int c) {
    uint32_t v = 0;
    for (int b = 0; b < 4; b++) v |= (uint32_t)get_byte(top->psum_out_flat, c * 4 + b) << (8 * b);
    return (int32_t)v;
}

static void reset(Vtop* top) {
    top->rst = 1;
    top->weight_load = 0;
    memset(&top->weight_in_flat, 0, sizeof(top->weight_in_flat));
    memset(&top->act_in_flat, 0, sizeof(top->act_in_flat));
    tick(top);
    top->rst = 0;
}

// Loads W (uncounted if pc==nullptr, otherwise ticked+counted with 0 valid PEs -- for
// the per-tile-reload scenario where the load itself is part of the measured cost).
static void load_weight(Vtop* top, int8_t w[N][N], PerfCounters* pc) {
    set_weight(top, w);
    top->weight_load = 1;
    tick(top);
    if (pc) pc->tick(0);
    top->weight_load = 0;
    memset(&top->weight_in_flat, 0, sizeof(top->weight_in_flat));
}

// Streams M activation rows through the (already loaded) array, de-skews the output,
// and checks it against the int32 reference. Returns true on match.
static bool stream_and_verify(Vtop* top, int8_t w[N][N], std::vector<std::vector<int8_t>>& A,
                               int M, PerfCounters& pc) {
    std::vector<std::vector<int32_t>> got(M, std::vector<int32_t>(N, 0));
    std::vector<bool> filled(M, false);

    long long total_cycles = M + 2 * N - 2;
    for (long long n = 1; n <= total_cycles; n++) {
        int8_t act[N];
        for (int r = 0; r < N; r++) {
            long long m = n - r - 1;
            act[r] = (m >= 0 && m < M) ? A[(size_t)m][r] : 0;
        }
        set_act(top, act);
        tick(top);

        long long valid = 0;
        for (int r = 0; r < N; r++)
            for (int c = 0; c < N; c++) {
                long long m = n - c - r - 1;
                if (m >= 0 && m < M) valid++;
            }
        pc.tick(valid);

        for (int c = 0; c < N; c++) {
            long long m = n - N - c;
            if (m >= 0 && m < M) {
                got[(size_t)m][c] = get_psum(top, c);
                filled[(size_t)m] = true;
            }
        }
    }

    for (int m = 0; m < M; m++) {
        if (!filled[m]) { printf("FAIL: row %d never captured\n", m); return false; }
        for (int c = 0; c < N; c++) {
            int32_t ref = 0;
            for (int k = 0; k < N; k++) ref += (int32_t)A[m][k] * (int32_t)w[k][c];
            if (got[m][c] != ref) {
                printf("FAIL: M=%d row %d col %d got %d want %d\n", M, m, c, got[m][c], ref);
                return false;
            }
        }
    }
    return true;
}

static void print_row(FILE* f, int N_, int M, const char* scenario, PerfCounters& pc, double freq_mhz) {
    fprintf(f, "%d,%d,%s,%lld,%lld,%.6f,%.4f,%.6f\n",
            N_, M, scenario, pc.total_cycles(), pc.ideal_macs(), pc.macs_per_cycle(),
            pc.utilization_pct(), pc.tops(freq_mhz));
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vtop* top = new Vtop;

    double freq_mhz = 500.0;
    const char* csv_path = nullptr;
    for (int i = 1; i < argc; i++) {
        if (strncmp(argv[i], "+freq_mhz=", 10) == 0) freq_mhz = atof(argv[i] + 10);
        if (strncmp(argv[i], "+csv=", 5) == 0) csv_path = argv[i] + 5;
    }

    FILE* csv = nullptr;
    if (csv_path) {
        bool need_header = false;
        FILE* probe = fopen(csv_path, "r");
        if (!probe) need_header = true;
        else fclose(probe);
        csv = fopen(csv_path, "a");
        if (!csv) { printf("FAIL: cannot open %s\n", csv_path); return 1; }
        if (need_header) fprintf(csv, "N,M,scenario,cycles,ideal_macs,macs_per_cycle,utilization_pct,tops_at_freq\n");
    }

    const int Ms[] = {N, 4 * N, 16 * N, 64 * N, 256};
    printf("%-4s %-6s %-18s %10s %12s %14s %10s %10s\n",
           "N", "M", "scenario", "cycles", "ideal_macs", "macs/cycle", "util%", "TOPS");

    bool all_pass = true;
    for (int M : Ms) {
        // scenario A: single weight load, then stream M rows.
        {
            std::mt19937 rng(1000u * N + M);
            std::uniform_int_distribution<int> dist(-16, 16);
            int8_t w[N][N];
            for (int r = 0; r < N; r++) for (int c = 0; c < N; c++) w[r][c] = (int8_t)dist(rng);
            std::vector<std::vector<int8_t>> A((size_t)M, std::vector<int8_t>(N));
            for (int m = 0; m < M; m++) for (int r = 0; r < N; r++) A[(size_t)m][r] = (int8_t)dist(rng);

            reset(top);
            load_weight(top, w, nullptr);
            PerfCounters pc;
            pc.begin_op(M, N);
            bool ok = stream_and_verify(top, w, A, M, pc);
            pc.end_op();
            all_pass &= ok;
            printf("%-4d %-6d %-18s %10lld %12lld %14.4f %9.2f%% %10.4f  %s\n",
                   N, M, "single_load", pc.total_cycles(), pc.ideal_macs(), pc.macs_per_cycle(),
                   pc.utilization_pct(), pc.tops(freq_mhz), ok ? "OK" : "MISMATCH");
            if (csv) print_row(csv, N, M, "single_load", pc, freq_mhz);
        }

        // scenario B: weight reload counted as part of the op -- models a weight-stationary
        // tile switch, so the fill/drain penalty of reloading every M-row batch is visible.
        {
            std::mt19937 rng(2000u * N + M);
            std::uniform_int_distribution<int> dist(-16, 16);
            int8_t w[N][N];
            for (int r = 0; r < N; r++) for (int c = 0; c < N; c++) w[r][c] = (int8_t)dist(rng);
            std::vector<std::vector<int8_t>> A((size_t)M, std::vector<int8_t>(N));
            for (int m = 0; m < M; m++) for (int r = 0; r < N; r++) A[(size_t)m][r] = (int8_t)dist(rng);

            reset(top);
            PerfCounters pc;
            pc.begin_op(M, N);
            load_weight(top, w, &pc);
            bool ok = stream_and_verify(top, w, A, M, pc);
            pc.end_op();
            all_pass &= ok;
            printf("%-4d %-6d %-18s %10lld %12lld %14.4f %9.2f%% %10.4f  %s\n",
                   N, M, "per_tile_reload", pc.total_cycles(), pc.ideal_macs(), pc.macs_per_cycle(),
                   pc.utilization_pct(), pc.tops(freq_mhz), ok ? "OK" : "MISMATCH");
            if (csv) print_row(csv, N, M, "per_tile_reload", pc, freq_mhz);
        }
    }

    if (csv) fclose(csv);
    delete top;
    if (!all_pass) { printf("FAIL: one or more scenarios mismatched the reference\n"); return 1; }
    printf("PASS: all scenarios verified against reference\n");
    return 0;
}
