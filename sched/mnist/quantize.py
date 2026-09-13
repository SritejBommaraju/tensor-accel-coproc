#!/usr/bin/env python3
"""Symmetric per-tensor INT8 post-training quantization of the fp32 MNIST MLP."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_mnist import load_mnist

HERE = os.path.dirname(os.path.abspath(__file__))
FP32_PATH = os.path.join(HERE, "weights_fp32.npz")
OUT = os.path.join(HERE, "weights_int8.npz")

CALIB_N = 1000


def quantize_multiplier(m):
    """Decompose real multiplier m>0 into (M0 int32, shift) s.t. m == M0/2**31 * 2**shift."""
    if m <= 0:
        return 0, 0
    shift = 0
    while m >= 1.0:
        m /= 2.0
        shift += 1
    while m < 0.5:
        m *= 2.0
        shift -= 1
    q = int(round(m * (1 << 31)))
    if q == (1 << 31):
        q //= 2
        shift += 1
    return q, shift


def apply_requant(acc, M0, shift):
    """Integer-only fixed-point rescale: round(acc * M0 / 2**31 * 2**shift), no float ops."""
    acc64 = acc.astype(np.int64)
    prod = acc64 * np.int64(M0)
    rs = 31 - shift
    if rs >= 0:
        round_val = (1 << (rs - 1)) if rs > 0 else 0
        out = (prod + round_val) >> rs
    else:
        out = prod << (-rs)
    return out


def sym_quantize(x, scale):
    q = np.round(x / scale)
    return np.clip(q, -127, 127).astype(np.int8)


def quantize_weights():
    fp = np.load(FP32_PATH)
    W1, b1, W2, b2 = fp["W1"], fp["b1"], fp["W2"], fp["b2"]

    tr_x, _, te_x, te_y = load_mnist()
    calib_x = (tr_x[:CALIB_N].astype(np.float32)) / 255.0

    scale_in = 1.0 / 127.0  # pixels normalized to [0,1], symmetric range covers max abs 1.0
    scale_w1 = np.abs(W1).max() / 127.0
    scale_w2 = np.abs(W2).max() / 127.0

    # calibrate hidden activation scale on the calibration set, fp32 forward pass
    z1 = calib_x @ W1 + b1
    a1 = np.maximum(z1, 0)
    scale_h = max(a1.max(), 1e-8) / 127.0

    W1_i8 = sym_quantize(W1, scale_w1)
    W2_i8 = sym_quantize(W2, scale_w2)
    b1_i32 = np.round(b1 / (scale_in * scale_w1)).astype(np.int32)
    b2_i32 = np.round(b2 / (scale_h * scale_w2)).astype(np.int32)

    m1 = (scale_in * scale_w1) / scale_h
    M0_1, shift_1 = quantize_multiplier(m1)

    np.savez(
        OUT,
        W1_i8=W1_i8, b1_i32=b1_i32, W2_i8=W2_i8, b2_i32=b2_i32,
        scale_in=scale_in, scale_w1=scale_w1, scale_h=scale_h, scale_w2=scale_w2,
        M0_1=M0_1, shift_1=shift_1,
    )
    return dict(
        W1_i8=W1_i8, b1_i32=b1_i32, W2_i8=W2_i8, b2_i32=b2_i32,
        scale_in=scale_in, scale_w1=scale_w1, scale_h=scale_h, scale_w2=scale_w2,
        M0_1=M0_1, shift_1=shift_1,
    )


def int8_forward(q, x_u8):
    """Full int8 inference matching the RTL pipeline: layer1 -> requant/ReLU -> layer2 -> argmax.
    x_u8: (N, 784) uint8 pixels. Returns int32 logits (N, 10)."""
    x_i8 = sym_quantize(x_u8.astype(np.float32) / 255.0, q["scale_in"])
    acc1 = x_i8.astype(np.int32) @ q["W1_i8"].astype(np.int32) + q["b1_i32"]
    h = apply_requant(acc1, int(q["M0_1"]), int(q["shift_1"]))
    h = np.clip(h, 0, 127).astype(np.int8)  # ReLU + saturate to int8
    logits = h.astype(np.int32) @ q["W2_i8"].astype(np.int32) + q["b2_i32"]
    return logits


def main():
    q = quantize_weights()
    _, _, te_x, te_y = load_mnist()
    logits = int8_forward(q, te_x)
    acc = (logits.argmax(axis=1) == te_y).mean()
    print(f"scale_in={q['scale_in']:.6f} scale_w1={q['scale_w1']:.6f} "
          f"scale_h={q['scale_h']:.6f} scale_w2={q['scale_w2']:.6f}")
    print(f"requant layer1: M0={q['M0_1']} shift={q['shift_1']}")
    print(f"int8 (numpy) test accuracy: {acc * 100:.2f}%")
    print(f"saved quantized weights to {OUT}")


if __name__ == "__main__":
    main()
