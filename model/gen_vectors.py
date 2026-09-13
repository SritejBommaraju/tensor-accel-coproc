#!/usr/bin/env python3
"""Generate random + edge-case (A, W, C) matmul vectors as plain-text case files for the Verilator TB."""
import argparse
import os
import numpy as np
from golden import golden_matmul


def write_case(path, a, w, c):
    n = w.shape[0]
    m = a.shape[0]
    with open(path, "w") as f:
        f.write(f"{n} {m}\n")
        for row in a:
            f.write(" ".join(str(int(x)) for x in row) + "\n")
        for row in w:
            f.write(" ".join(str(int(x)) for x in row) + "\n")
        for row in c:
            f.write(" ".join(str(int(x)) for x in row) + "\n")


def edge_cases(n, m):
    cases = {}
    cases["all_neg128"] = (np.full((m, n), -128, dtype=np.int8), np.full((n, n), -128, dtype=np.int8))
    cases["all_127"] = (np.full((m, n), 127, dtype=np.int8), np.full((n, n), 127, dtype=np.int8))
    cases["zero"] = (np.zeros((m, n), dtype=np.int8), np.zeros((n, n), dtype=np.int8))
    rng = np.random.default_rng(12345)
    cases["identity"] = (rng.integers(-128, 128, size=(m, n), dtype=np.int8), np.eye(n, dtype=np.int8))
    a_hot = np.zeros((m, n), dtype=np.int8)
    a_hot[0, 0] = 1
    w_hot = np.zeros((n, n), dtype=np.int8)
    w_hot[0, 0] = 1
    cases["single_hot"] = (a_hot, w_hot)
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--m", type=int, required=True)
    ap.add_argument("--out", type=str, required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    for f in os.listdir(args.out):
        if f.endswith(".txt"):
            os.remove(os.path.join(args.out, f))

    rng = np.random.default_rng(args.seed)
    names = []
    for i in range(args.count):
        a = rng.integers(-128, 128, size=(args.m, args.n), dtype=np.int8)
        w = rng.integers(-128, 128, size=(args.n, args.n), dtype=np.int8)
        c = golden_matmul(w, a)
        name = f"rand_{i:04d}"
        write_case(os.path.join(args.out, name + ".txt"), a, w, c)
        names.append(name)

    for name, (a, w) in edge_cases(args.n, args.m).items():
        c = golden_matmul(w, a)
        write_case(os.path.join(args.out, "edge_" + name + ".txt"), a, w, c)
        names.append("edge_" + name)

    with open(os.path.join(args.out, "manifest.txt"), "w") as f:
        for name in names:
            f.write(name + ".txt\n")


if __name__ == "__main__":
    main()
