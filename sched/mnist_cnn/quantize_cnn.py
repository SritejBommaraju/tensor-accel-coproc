#!/usr/bin/env python3
"""Quantize the Conv2d->ReLU->MaxPool2x2->Flatten->Dense CNN via nn.quant's generalized PTQ."""
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED_DIR = os.path.dirname(HERE)
sys.path.insert(0, SCHED_DIR)
sys.path.insert(0, os.path.join(SCHED_DIR, "mnist"))
sys.path.insert(0, os.path.join(SCHED_DIR, "nn"))

from fetch_mnist import load_mnist  # noqa: E402
from layers import Conv2d, ReLU, MaxPool2x2, Flatten, Dense  # noqa: E402
from quant import quantize_graph, pure_numpy_int8_forward, SCALE_IN_PIXELS, CALIB_N  # noqa: E402
from quantize import sym_quantize  # noqa: E402

FP32_PATH = os.path.join(HERE, "weights_fp32.npz")
OUT = os.path.join(HERE, "weights_int8.npz")
GRAPH_PATH = os.path.join(HERE, "weights_int8.graph.pkl")


def build_graph(fp):
    conv = Conv2d(1, 8)
    conv.W, conv.b = fp["W"], fp["b"]
    relu = ReLU()
    pool = MaxPool2x2()
    flat = Flatten()
    dense = Dense(fp["Wd"].shape[0], 10, output=True)
    dense.W, dense.b = fp["Wd"], fp["bd"]
    return [conv, relu, pool, flat, dense]


def main():
    fp = np.load(FP32_PATH)
    layers = build_graph(fp)

    tr_x, _, te_x, te_y = load_mnist()
    calib_x = (tr_x[:CALIB_N].astype(np.float32) / 255.0).reshape(-1, 1, 28, 28)
    quantize_graph(layers, calib_x, scale_in=SCALE_IN_PIXELS)

    conv, _, _, _, dense = layers
    np.savez(
        OUT,
        Wc_i8=conv.W_i8, bc_i32=conv.b_i32, scale_wc=conv.scale_w, scale_out_c=conv.scale_out,
        M0_c=conv.M0, shift_c=conv.shift,
        Wd_i8=dense.W_i8, bd_i32=dense.b_i32, scale_wd=dense.scale_w,
        scale_in=SCALE_IN_PIXELS,
    )
    with open(GRAPH_PATH, "wb") as f:
        pickle.dump(layers, f)

    x_i8 = sym_quantize(te_x.astype(np.float32) / 255.0, SCALE_IN_PIXELS).reshape(-1, 1, 28, 28)
    logits = pure_numpy_int8_forward(layers, x_i8)
    acc = (logits.argmax(axis=1) == te_y).mean()
    print(f"scale_in={SCALE_IN_PIXELS:.6f} scale_wc={conv.scale_w:.6f} scale_out_c={conv.scale_out:.6f} "
          f"scale_wd={dense.scale_w:.6f}")
    print(f"requant conv: M0={conv.M0} shift={conv.shift}")
    print(f"int8 (numpy) test accuracy: {acc * 100:.2f}%")
    print(f"saved quantized weights to {OUT}")


if __name__ == "__main__":
    main()
