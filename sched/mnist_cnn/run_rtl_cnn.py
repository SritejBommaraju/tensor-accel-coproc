#!/usr/bin/env python3
"""Run the INT8 Conv-MaxPool-Dense CNN end-to-end through the tiling scheduler on Verilated RTL."""
import argparse
import os
import pickle
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED_DIR = os.path.dirname(HERE)
sys.path.insert(0, SCHED_DIR)
sys.path.insert(0, os.path.join(SCHED_DIR, "mnist"))
sys.path.insert(0, os.path.join(SCHED_DIR, "nn"))

from tiler import plan, execute, VerilatorBackend  # noqa: E402
from fetch_mnist import load_mnist  # noqa: E402
from quantize import sym_quantize, apply_requant  # noqa: E402
from layers import im2col  # noqa: E402

WEIGHTS = os.path.join(HERE, "weights_int8.npz")
GRAPH_PATH = os.path.join(HERE, "weights_int8.graph.pkl")
RESULTS = os.path.join(HERE, "results.txt")

BATCH = 40  # im2col batch size, keeps peak memory/RTL traffic bounded at large --count


def fp32_cnn_accuracy(te_x, te_y, n):
    from quantize_cnn import build_graph
    fp = np.load(os.path.join(HERE, "weights_fp32.npz"))
    layers = build_graph(fp)
    x = (te_x[:n].astype(np.float32) / 255.0).reshape(-1, 1, 28, 28)
    out = x
    for layer in layers:
        out = layer.forward_fp32(out)
    return (out.argmax(axis=1) == te_y[:n]).mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=200)
    args = ap.parse_args()

    with open(GRAPH_PATH, "rb") as f:
        conv, relu, pool, flat, dense = pickle.load(f)
    q = np.load(WEIGHTS)
    scale_in = float(q["scale_in"])

    _, _, te_x, te_y = load_mnist()
    n = min(args.count, te_x.shape[0])
    x = te_x[:n]
    y = te_y[:n]

    x_i8_full = sym_quantize(x.astype(np.float32) / 255.0, scale_in).reshape(-1, 1, 28, 28)

    t0 = time.time()
    backend = VerilatorBackend()

    conv_exact = True
    dense_exact = True
    conv_exact_n = conv_total_n = 0
    dense_exact_n = dense_total_n = 0
    tiles_c = loads_c = cycles_c = macs_c = 0
    tiles_d = loads_d = cycles_d = macs_d = 0
    logits_all = []

    for i in range(0, n, BATCH):
        xb = x_i8_full[i:i + BATCH]

        # conv layer: im2col -> (rows, 9) @ (9, 8) on RTL
        cols, (nb, OH, OW) = im2col(xb, 3, 3)
        cols = cols.astype(np.int8)
        schedule_c = plan(M=cols.shape[0], K=cols.shape[1], N=conv.out_ch)
        acc_c_rtl, stats_c = execute(schedule_c, cols, conv.W_i8, backend)
        acc_c_np = cols.astype(np.int32) @ conv.W_i8.astype(np.int32)
        conv_exact &= np.array_equal(acc_c_rtl, acc_c_np)
        conv_exact_n += int(np.sum(acc_c_rtl == acc_c_np))
        conv_total_n += acc_c_np.size
        tiles_c += stats_c["tiles"]; loads_c += stats_c["weight_loads"]
        cycles_c += stats_c["cycles"]; macs_c += stats_c["macs"]

        conv_out = apply_requant(acc_c_rtl + conv.b_i32, int(conv.M0), int(conv.shift))
        conv_out = np.clip(conv_out, -127, 127).astype(np.int8)
        conv_out = conv_out.reshape(nb, OH, OW, conv.out_ch).transpose(0, 3, 1, 2)

        h = relu.forward_int8(conv_out)[0]
        h = pool.forward_int8(h)[0]
        h = flat.forward_int8(h)[0]

        # dense layer: (rows, 1352) @ (1352, 10) on RTL
        schedule_d = plan(M=h.shape[0], K=h.shape[1], N=dense.out_f)
        acc_d_rtl, stats_d = execute(schedule_d, h, dense.W_i8, backend)
        acc_d_np = h.astype(np.int32) @ dense.W_i8.astype(np.int32)
        dense_exact &= np.array_equal(acc_d_rtl, acc_d_np)
        dense_exact_n += int(np.sum(acc_d_rtl == acc_d_np))
        dense_total_n += acc_d_np.size
        tiles_d += stats_d["tiles"]; loads_d += stats_d["weight_loads"]
        cycles_d += stats_d["cycles"]; macs_d += stats_d["macs"]

        logits_all.append(acc_d_rtl + dense.b_i32)

    backend.close()
    wall = time.time() - t0

    logits_rtl = np.concatenate(logits_all, axis=0)
    pred_rtl = logits_rtl.argmax(axis=1)
    rtl_acc = (pred_rtl == y).mean()

    # numpy int8 reference (identical arithmetic, no RTL)
    from quant import pure_numpy_int8_forward
    logits_np = pure_numpy_int8_forward([conv, relu, pool, flat, dense], x_i8_full)
    numpy_acc = (logits_np.argmax(axis=1) == y).mean()

    fp32_acc = fp32_cnn_accuracy(te_x, te_y, n)

    bit_exact = conv_exact and dense_exact
    macs_per_cycle_c = macs_c / cycles_c if cycles_c else float("inf")
    macs_per_cycle_d = macs_d / cycles_d if cycles_d else float("inf")
    tiles = tiles_c + tiles_d
    cycles = cycles_c + cycles_d
    macs = macs_c + macs_d
    macs_per_cycle = macs / cycles if cycles else float("inf")

    lines = [
        f"N images: {n}",
        f"RTL int8 accuracy:   {rtl_acc * 100:.2f}%",
        f"numpy int8 accuracy: {numpy_acc * 100:.2f}%",
        f"fp32 CNN accuracy:   {fp32_acc * 100:.2f}%",
        "",
        "per-layer bit-exactness vs numpy int8 matmul (raw accumulator, pre-bias):",
        f"  conv (K=9, 4x4 tile, {conv_exact_n}/{conv_total_n} exact): {conv_exact}",
        f"  dense (K=1352, {dense_exact_n}/{dense_total_n} exact): {dense_exact}",
        f"bit-exact vs numpy int8: {bit_exact}",
        "",
        "per-layer scheduler stats:",
        f"  conv:  tiles={tiles_c} weight_loads={loads_c} cycles={cycles_c} MACs={macs_c} "
        f"MACs/cycle={macs_per_cycle_c:.3f}  (K=9 padded to ceil(9/4)*4=12: only 9/12=75% of the "
        f"K-dim MAC lanes do real work, the rest multiply zero padding)",
        f"  dense: tiles={tiles_d} weight_loads={loads_d} cycles={cycles_d} MACs={macs_d} "
        f"MACs/cycle={macs_per_cycle_d:.3f}",
        f"total: tiles={tiles} cycles={cycles} MACs={macs} MACs/cycle={macs_per_cycle:.3f}",
        f"wall-clock: {wall:.2f}s",
    ]
    for line in lines:
        print(line)

    with open(RESULTS, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
