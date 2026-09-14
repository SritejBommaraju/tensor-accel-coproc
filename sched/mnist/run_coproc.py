#!/usr/bin/env python3
"""Run the INT8 MNIST MLP end-to-end through the tiling scheduler over the MMIO+AXI path
(CoprocBackend): register writes/reads plus host-memory bursts, exactly what a real driver
against sw/coproc_mmio.h would see. Same flow and output lines as run_rtl.py, plus MMIO/AXI
telemetry (command count, beat counts, DMA-inclusive cycles, end-to-end MACs/cycle).
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED_DIR = os.path.dirname(HERE)
sys.path.insert(0, SCHED_DIR)
sys.path.insert(0, HERE)

from tiler import plan, execute  # noqa: E402
from coproc_backend import CoprocBackend  # noqa: E402
from fetch_mnist import load_mnist  # noqa: E402
from quantize import sym_quantize, apply_requant  # noqa: E402

WEIGHTS = os.path.join(HERE, "weights_int8.npz")
RESULTS = os.path.join(HERE, "results_coproc.txt")


def fp32_accuracy(x_u8, y, n):
    fp = np.load(os.path.join(HERE, "weights_fp32.npz"))
    x = (x_u8[:n].astype(np.float32)) / 255.0
    z1 = x @ fp["W1"] + fp["b1"]
    a1 = np.maximum(z1, 0)
    logits = a1 @ fp["W2"] + fp["b2"]
    return (logits.argmax(axis=1) == y[:n]).mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--stall", action="store_true", help="enable random AXI backpressure")
    args = ap.parse_args()

    q = np.load(WEIGHTS)
    _, _, te_x, te_y = load_mnist()
    n = min(args.count, te_x.shape[0])
    x = te_x[:n]
    y = te_y[:n]

    x_i8 = sym_quantize(x.astype(np.float32) / 255.0, float(q["scale_in"]))
    W1 = q["W1_i8"]
    b1 = q["b1_i32"]
    W2 = q["W2_i8"]
    b2 = q["b2_i32"]
    M0_1, shift_1 = int(q["M0_1"]), int(q["shift_1"])

    t0 = time.time()
    backend = CoprocBackend(stall=args.stall)

    # layer 1: (n, 784) @ (784, 64) through MMIO+AXI
    schedule1 = plan(M=n, K=784, N=64)
    acc1_rtl, stats1 = execute(schedule1, x_i8, W1, backend)

    # bit-exactness check vs numpy int8 matmul (pre-bias, raw accumulator from the coproc == numpy int8 matmul)
    acc1_numpy_raw = x_i8.astype(np.int32) @ W1.astype(np.int32)
    exact1 = np.array_equal(acc1_rtl, acc1_numpy_raw)

    acc1 = acc1_rtl + b1
    h = apply_requant(acc1, M0_1, shift_1)
    h = np.clip(h, 0, 127).astype(np.int8)

    # layer 2: (n, 64) @ (64, 10) through MMIO+AXI
    schedule2 = plan(M=n, K=64, N=10)
    acc2_rtl, stats2 = execute(schedule2, h, W2, backend)

    n_commands = backend.n_commands
    rd_beats, wr_beats = backend.beats()
    dma_cycles = backend.total_cycles
    backend.close()
    wall = time.time() - t0

    acc2_numpy_raw = h.astype(np.int32) @ W2.astype(np.int32)
    exact2 = np.array_equal(acc2_rtl, acc2_numpy_raw)
    bit_exact = exact1 and exact2
    n_exact = int(np.sum(acc1_rtl == acc1_numpy_raw)) + int(np.sum(acc2_rtl == acc2_numpy_raw))
    n_total = acc1_rtl.size + acc2_rtl.size
    exact_pct = 100.0 * n_exact / n_total

    logits_rtl = acc2_rtl + b2
    pred_rtl = logits_rtl.argmax(axis=1)
    rtl_acc = (pred_rtl == y).mean()

    # numpy int8 reference (identical arithmetic, no RTL)
    acc1_np = x_i8.astype(np.int32) @ W1.astype(np.int32) + b1
    h_np = np.clip(apply_requant(acc1_np, M0_1, shift_1), 0, 127).astype(np.int8)
    logits_np = h_np.astype(np.int32) @ W2.astype(np.int32) + b2
    numpy_acc = (logits_np.argmax(axis=1) == y).mean()

    fp32_acc = fp32_accuracy(te_x, te_y, n)

    tiles = stats1["tiles"] + stats2["tiles"]
    cycles = stats1["cycles"] + stats2["cycles"]  # per-tile cycles reported by the coproc itself
    macs = stats1["macs"] + stats2["macs"]
    macs_per_cycle = macs / cycles if cycles else float("inf")
    macs_per_cycle_e2e = macs / dma_cycles if dma_cycles else float("inf")

    lines = [
        f"N images: {n}",
        f"RTL int8 accuracy:   {rtl_acc * 100:.2f}%",
        f"numpy int8 accuracy: {numpy_acc * 100:.2f}%",
        f"fp32 accuracy:       {fp32_acc * 100:.2f}%",
        f"bit-exact vs numpy int8 matmul: {bit_exact} ({exact_pct:.4f}% of {n_total} accumulators)",
        f"tiles={tiles} cycles={cycles} MACs={macs} MACs/cycle={macs_per_cycle:.3f}",
        f"MMIO commands issued: {n_commands}",
        f"AXI beats: rd={rd_beats} wr={wr_beats} total={rd_beats + wr_beats}",
        f"total cycles including DMA: {dma_cycles}",
        f"MACs/cycle end-to-end (incl. DMA): {macs_per_cycle_e2e:.3f}",
        f"wall-clock: {wall:.2f}s",
    ]
    for line in lines:
        print(line)

    with open(RESULTS, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
