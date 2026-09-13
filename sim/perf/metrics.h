#pragma once
// Header-only utilization / MACs-per-cycle instrumentation for the systolic array TB.
#include <cstdint>

struct PerfResult {
    long long total_cycles   = 0;
    long long fill_cycles    = 0;
    long long drain_cycles   = 0;
    long long ideal_macs     = 0;
    double    macs_per_cycle = 0.0;
    double    utilization_pct = 0.0;
};

// Pure function so the arithmetic is checkable without Verilator: M activation rows,
// NxN array, total_cycles measured for the whole streamed op.
inline PerfResult compute_perf(long long M, long long N, long long total_cycles) {
    PerfResult r;
    r.total_cycles = total_cycles;
    r.fill_cycles  = N - 1;
    r.drain_cycles = N - 1;
    r.ideal_macs   = M * N * N;
    if (total_cycles > 0) {
        r.macs_per_cycle  = (double)r.ideal_macs / (double)total_cycles;
        r.utilization_pct = (double)r.ideal_macs / ((double)total_cycles * (double)N * (double)N) * 100.0;
    }
    return r;
}

// tops = macs/cycle * 2 flops/mac * freq(Hz) / 1e12
inline double macs_per_cycle_to_tops(double macs_per_cycle, double freq_mhz) {
    return macs_per_cycle * 2.0 * freq_mhz * 1e6 / 1e12;
}

class PerfCounters {
public:
    void begin_op(long long M, long long N) {
        M_ = M; N_ = N; cycles_ = 0; valid_pe_sum_ = 0; result_ = PerfResult{};
    }

    // valid_pes: number of (r,c) PEs holding a real (non-padding) activation this cycle.
    void tick(long long valid_pes) {
        cycles_++;
        valid_pe_sum_ += valid_pes;
    }

    void end_op() { result_ = compute_perf(M_, N_, cycles_); }

    long long total_cycles() const { return result_.total_cycles; }
    long long fill_cycles() const { return result_.fill_cycles; }
    long long drain_cycles() const { return result_.drain_cycles; }
    long long ideal_macs() const { return result_.ideal_macs; }
    double macs_per_cycle() const { return result_.macs_per_cycle; }
    double utilization_pct() const { return result_.utilization_pct; }
    long long valid_pe_sum() const { return valid_pe_sum_; }
    double tops(double freq_mhz) const { return macs_per_cycle_to_tops(result_.macs_per_cycle, freq_mhz); }

private:
    long long M_ = 0, N_ = 0;
    long long cycles_ = 0;
    long long valid_pe_sum_ = 0;
    PerfResult result_;
};
