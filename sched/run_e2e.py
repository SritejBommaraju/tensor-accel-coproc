#!/usr/bin/env python3
"""End-to-end check: drive the real Verilator array through the tiler and diff vs numpy."""
import argparse
import sys
import numpy as np

from tiler import plan, execute, VerilatorBackend

SHAPES = [(4, 4, 4), (16, 12, 8), (5, 7, 3), (1, 4, 4), (64, 64, 64), (33, 17, 9)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--shapes", default=None, help="e.g. '4,4,4;16,12,8'")
    args = ap.parse_args()

    shapes = SHAPES
    if args.shapes:
        shapes = [tuple(int(x) for x in s.split(",")) for s in args.shapes.split(";")]

    rng = np.random.default_rng(args.seed)
    backend = VerilatorBackend()
    ok = True
    for M, K, N in shapes:
        A = rng.integers(-128, 128, size=(M, K), dtype=np.int8)
        W = rng.integers(-128, 128, size=(K, N), dtype=np.int8)
        schedule = plan(M, K, N)
        C, stats = execute(schedule, A, W, backend)
        expected = A.astype(np.int32) @ W.astype(np.int32)
        passed = np.array_equal(C, expected)
        ok &= passed
        status = "PASS" if passed else "FAIL"
        print(f"{status} shape=({M},{K},{N}) tiles={stats['tiles']} "
              f"cycles={stats['cycles']} macs_per_cycle={stats['macs_per_cycle']:.2f}")
    backend.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
