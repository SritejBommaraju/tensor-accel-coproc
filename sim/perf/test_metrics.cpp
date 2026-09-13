// Plain C++ known-answer test for PerfCounters arithmetic. No Verilator needed.
#include <cstdio>
#include <cmath>
#include "metrics.h"

static int failures = 0;

static void expect_near(const char* name, double got, double want, double tol) {
    if (std::fabs(got - want) > tol) {
        printf("FAIL %s: got %f want %f (tol %f)\n", name, got, want, tol);
        failures++;
    } else {
        printf("PASS %s: %f\n", name, got);
    }
}

static void expect_eq(const char* name, long long got, long long want) {
    if (got != want) {
        printf("FAIL %s: got %lld want %lld\n", name, got, want);
        failures++;
    } else {
        printf("PASS %s: %lld\n", name, got);
    }
}

int main() {
    // N=4, M=256, cycles=262 -> utilization 97.71% (M/(M+2N-2) = 256/262)
    {
        PerfResult r = compute_perf(256, 4, 262);
        expect_eq("ideal_macs", r.ideal_macs, 256LL * 4 * 4);
        expect_near("utilization_pct", r.utilization_pct, 97.709924, 0.01);
        expect_near("macs_per_cycle", r.macs_per_cycle, 4096.0 / 262.0, 1e-9);
    }

    // small N=16, M=16 tile-reload case (extra weight-load cycle) should sit well below 50%.
    {
        PerfResult r = compute_perf(16, 16, 1 + (16 + 2 * 16 - 2));
        expect_eq("tile_reload_cycles", r.total_cycles, 47);
        if (r.utilization_pct >= 50.0) {
            printf("FAIL tile_reload_utilization: got %f, expected < 50\n", r.utilization_pct);
            failures++;
        } else {
            printf("PASS tile_reload_utilization: %f\n", r.utilization_pct);
        }
    }

    // PerfCounters wrapper matches the pure function.
    {
        PerfCounters pc;
        pc.begin_op(256, 4);
        for (int i = 0; i < 262; i++) pc.tick(16); // arbitrary valid-PE count, doesn't affect the metric
        pc.end_op();
        expect_eq("counters_total_cycles", pc.total_cycles(), 262);
        expect_eq("counters_fill_cycles", pc.fill_cycles(), 3);
        expect_eq("counters_drain_cycles", pc.drain_cycles(), 3);
        expect_near("counters_utilization_pct", pc.utilization_pct(), 97.709924, 0.01);
        expect_near("counters_tops_500mhz", pc.tops(500.0), (4096.0 / 262.0) * 2.0 * 500e6 / 1e12, 1e-9);
    }

    if (failures == 0) {
        printf("ALL TESTS PASSED\n");
        return 0;
    }
    printf("%d TEST(S) FAILED\n", failures);
    return 1;
}
