"""Generalized per-layer symmetric post-training quantization for a layer-graph (list of nn.layers)."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED_DIR = os.path.dirname(HERE)
sys.path.insert(0, SCHED_DIR)
sys.path.insert(0, os.path.join(SCHED_DIR, "mnist"))

from quantize import apply_requant  # noqa: E402
from layers import Conv2d, Dense, ReLU, MaxPool2x2, Flatten, im2col  # noqa: E402

CALIB_N = 1000
SCALE_IN_PIXELS = 1.0 / 127.0  # pixels normalized to [0,1], symmetric range covers max abs 1.0


def quantize_graph(layers, calib_x_fp32, scale_in=SCALE_IN_PIXELS):
    """Quantize each layer in sequence on a chain of calibration activations. Mutates layers in place."""
    x, s = calib_x_fp32, scale_in
    for layer in layers:
        s, x = layer.quantize(s, x)
    return s


def graph_forward_int8(layers, x_i8, backend):
    """Run the quantized graph's int8 forward through a tiler backend (NumpyBackend or VerilatorBackend)."""
    x = x_i8
    stats = []
    for layer in layers:
        out = layer.forward_int8(x, backend)
        if isinstance(out, tuple):
            x, st = out
            if st is not None:
                stats.append(st)
        else:
            x = out
    return x, stats


def pure_numpy_int8_forward(layers, x_i8):
    """Ground-truth int8 forward reimplemented directly with numpy (no tiler) -- what the tiled/backend
    path in layers.py must match bit-exactly."""
    x = x_i8
    for layer in layers:
        if isinstance(layer, Conv2d):
            cols, (N, OH, OW) = im2col(x, layer.kh, layer.kw)
            acc = cols.astype(np.int32) @ layer.W_i8.astype(np.int32) + layer.b_i32
            out = apply_requant(acc, int(layer.M0), int(layer.shift))
            out = np.clip(out, -127, 127).astype(np.int8)
            x = out.reshape(N, OH, OW, layer.out_ch).transpose(0, 3, 1, 2)
        elif isinstance(layer, Dense):
            acc = x.astype(np.int32) @ layer.W_i8.astype(np.int32) + layer.b_i32
            if layer.output:
                x = acc
            else:
                out = apply_requant(acc, int(layer.M0), int(layer.shift))
                x = np.clip(out, -127, 127).astype(np.int8)
        elif isinstance(layer, ReLU):
            x = np.clip(x, 0, 127).astype(np.int8)
        elif isinstance(layer, MaxPool2x2):
            N, C, H, W = x.shape
            x = x.reshape(N, C, H // 2, 2, W // 2, 2).max(axis=(3, 5))
        elif isinstance(layer, Flatten):
            x = x.reshape(x.shape[0], -1)
        else:
            raise TypeError(f"unknown layer type {type(layer)}")
    return x
