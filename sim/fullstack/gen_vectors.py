#!/usr/bin/env python3
"""Exports sched/mnist/weights_int8.npz plus 32 test images to little-endian binaries for
tb_fullstack.cpp, using the numpy int8 reference (sched/mnist/quantize.py) so tb_fullstack has
a bit-exact golden logits file to check the RTL+driver path against. No RTL/Python coupling
at run time: this only produces static input files."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MNIST_DIR = os.path.join(HERE, "..", "..", "sched", "mnist")
OUT_DIR = os.path.join(HERE, "vectors")
sys.path.insert(0, MNIST_DIR)

from fetch_mnist import load_mnist  # noqa: E402
from quantize import sym_quantize, apply_requant  # noqa: E402

N_IMAGES = 32


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    q = dict(np.load(os.path.join(MNIST_DIR, "weights_int8.npz")))
    _, _, te_x, te_y = load_mnist()

    x_u8 = te_x[:N_IMAGES]              # (32, 784) uint8 pixels
    labels = te_y[:N_IMAGES].astype(np.int32)

    x_i8 = sym_quantize(x_u8.astype(np.float32) / 255.0, float(q["scale_in"]))  # (32,784) int8

    W1_i8 = q["W1_i8"].astype(np.int8)          # (784,64)
    b1_i32 = q["b1_i32"].astype(np.int32)       # (64,)
    W2_i8 = q["W2_i8"].astype(np.int8)          # (64,10)
    b2_i32 = q["b2_i32"].astype(np.int32)       # (10,)
    M0_1 = int(q["M0_1"])
    shift_1 = int(q["shift_1"])

    # golden logits computed on the exact same x_i8 bytes the driver will feed the hardware,
    # bit-for-bit the same integer pipeline as quantize.py::int8_forward
    acc1 = x_i8.astype(np.int32) @ W1_i8.astype(np.int32) + b1_i32
    h = apply_requant(acc1, M0_1, shift_1)
    h = np.clip(h, 0, 127).astype(np.int8)
    logits = h.astype(np.int32) @ W2_i8.astype(np.int32) + b2_i32  # (32,10) int32

    with open(os.path.join(OUT_DIR, "weights.bin"), "wb") as f:
        f.write(W1_i8.tobytes())
        f.write(b1_i32.astype("<i4").tobytes())
        f.write(W2_i8.tobytes())
        f.write(b2_i32.astype("<i4").tobytes())

    x_i8.astype(np.int8).tofile(os.path.join(OUT_DIR, "images.bin"))
    labels.astype("<i4").tofile(os.path.join(OUT_DIR, "labels.bin"))
    logits.astype("<i4").tofile(os.path.join(OUT_DIR, "expected_logits.bin"))

    with open(os.path.join(OUT_DIR, "manifest.txt"), "w") as f:
        f.write(f"n_images={N_IMAGES}\n")
        f.write("in=784 hidden=64 out=10\n")
        f.write(f"M0_1={M0_1} shift_1={shift_1}\n")
        f.write("weights.bin = W1_i8[784][64] + b1_i32[64] + W2_i8[64][10] + b2_i32[10]\n")
        f.write("images.bin = x_i8[n_images][784] int8\n")
        f.write("labels.bin = label[n_images] int32 LE\n")
        f.write("expected_logits.bin = logits[n_images][10] int32 LE\n")

    acc = (logits.argmax(axis=1) == labels).mean()
    print(f"wrote vectors to {OUT_DIR}, {N_IMAGES} images, numpy int8 accuracy on this batch: {acc*100:.1f}%")


if __name__ == "__main__":
    main()
