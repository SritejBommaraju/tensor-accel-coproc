#!/usr/bin/env python3
"""Cross-checks the ungated and gated tb_power runs.

Both tb_power executables already assert their own psum_out against a software oracle every
cycle (gated: act_valid-aware oracle, every scenario; ungated: plain oracle, dense scenario only
-- see tb_power.cpp) and fail loudly (non-zero exit) if that assertion trips. This script adds
the direct comparison required for the "dense" scenario: when every row is act_valid=1, the
gated and ungated RTL must be bit-for-bit identical, cycle for cycle.
"""
import sys
import os

def main():
    n = int(sys.argv[1])
    vcd_dir = os.path.join(os.path.dirname(__file__), "vcd")
    a = open(os.path.join(vcd_dir, f"top_N{n}_dense.csv")).read().splitlines()
    b = open(os.path.join(vcd_dir, f"topcg_N{n}_dense.csv")).read().splitlines()
    if a != b:
        mismatches = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        print(f"N={n} dense: FAIL at cycles {mismatches[:5]}")
        sys.exit(1)
    print(f"N={n} dense: OK ({len(a)} cycles bit-exact, gated == ungated)")

if __name__ == "__main__":
    main()
