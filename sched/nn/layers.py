"""Layer graph: fp32 + int8 forward for Conv2d/MaxPool2x2/ReLU/Flatten/Dense.
Every matmul (conv-as-im2col, dense) runs its int8 path through tiler.plan/execute on any backend.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED_DIR = os.path.dirname(HERE)
sys.path.insert(0, SCHED_DIR)
sys.path.insert(0, os.path.join(SCHED_DIR, "mnist"))

from tiler import plan, execute  # noqa: E402
from quantize import sym_quantize, apply_requant, quantize_multiplier  # noqa: E402


def im2col(x, kh=3, kw=3):
    """x: (N, C, H, W) -> patches (N*OH*OW, C*kh*kw) in (c, dy, dx) row-major order, and (N, OH, OW)."""
    N, C, H, W = x.shape
    OH, OW = H - kh + 1, W - kw + 1
    cols = np.zeros((N, OH, OW, C, kh, kw), dtype=x.dtype)
    for dy in range(kh):
        for dx in range(kw):
            cols[:, :, :, :, dy, dx] = x[:, :, dy:dy + OH, dx:dx + OW].transpose(0, 2, 3, 1)
    return cols.reshape(N * OH * OW, C * kh * kw), (N, OH, OW)


class Layer:
    """Base: quantize(scale_in, calib_x_fp32) -> (scale_out, calib_out_fp32), sets int8 params on self."""

    def quantize(self, scale_in, calib_x):
        raise NotImplementedError


class Conv2d(Layer):
    """3x3 stride-1 valid conv, im2col -> one (rows, 9*Cin) @ (9*Cin, Cout) matmul."""

    def __init__(self, in_ch, out_ch, kh=3, kw=3):
        self.in_ch, self.out_ch, self.kh, self.kw = in_ch, out_ch, kh, kw
        self.W = None  # (out_ch, in_ch, kh, kw) fp32
        self.b = None  # (out_ch,) fp32

    def forward_fp32(self, x):
        cols, (N, OH, OW) = im2col(x, self.kh, self.kw)
        Wmat = self.W.reshape(self.out_ch, -1).T  # (Cin*kh*kw, out_ch)
        out = cols @ Wmat + self.b
        return out.reshape(N, OH, OW, self.out_ch).transpose(0, 3, 1, 2)

    def quantize(self, scale_in, calib_x):
        self.scale_in = scale_in
        self.scale_w = max(np.abs(self.W).max(), 1e-8) / 127.0
        self.W_i8 = sym_quantize(self.W, self.scale_w).reshape(self.out_ch, -1).T.copy()  # (K, out_ch)
        self.b_i32 = np.round(self.b / (scale_in * self.scale_w)).astype(np.int32)

        calib_out = self.forward_fp32(calib_x)
        self.scale_out = max(np.abs(calib_out).max(), 1e-8) / 127.0
        m = (scale_in * self.scale_w) / self.scale_out
        self.M0, self.shift = quantize_multiplier(m)
        return self.scale_out, calib_out

    def forward_int8(self, x_i8, backend):
        cols, (N, OH, OW) = im2col(x_i8, self.kh, self.kw)
        cols = cols.astype(np.int8)
        M, K = cols.shape
        schedule = plan(M=M, K=K, N=self.out_ch)
        acc, stats = execute(schedule, cols, self.W_i8, backend)
        acc = acc + self.b_i32
        out = apply_requant(acc, int(self.M0), int(self.shift))
        out = np.clip(out, -127, 127).astype(np.int8)
        out = out.reshape(N, OH, OW, self.out_ch).transpose(0, 3, 1, 2)
        return out, stats


class MaxPool2x2(Layer):
    def forward_fp32(self, x):
        N, C, H, W = x.shape
        x = x.reshape(N, C, H // 2, 2, W // 2, 2)
        return x.max(axis=(3, 5))

    def quantize(self, scale_in, calib_x):
        return scale_in, self.forward_fp32(calib_x)

    def forward_int8(self, x_i8, backend=None):
        return self.forward_fp32(x_i8).astype(np.int8), None


class ReLU(Layer):
    def forward_fp32(self, x):
        return np.maximum(x, 0)

    def quantize(self, scale_in, calib_x):
        return scale_in, self.forward_fp32(calib_x)

    def forward_int8(self, x_i8, backend=None):
        return np.clip(x_i8, 0, 127).astype(np.int8), None


class Flatten(Layer):
    def forward_fp32(self, x):
        return x.reshape(x.shape[0], -1)

    def quantize(self, scale_in, calib_x):
        return scale_in, self.forward_fp32(calib_x)

    def forward_int8(self, x_i8, backend=None):
        return self.forward_fp32(x_i8).astype(np.int8), None


class Dense(Layer):
    """output=True marks the final graph layer: raw int32 acc+bias is returned (no requant/clip),
    matching sched/mnist's logits layer -- argmax is invariant to the shared positive rescale anyway."""

    def __init__(self, in_f, out_f, output=False):
        self.in_f, self.out_f, self.output = in_f, out_f, output
        self.W = None  # (in_f, out_f) fp32
        self.b = None  # (out_f,) fp32

    def forward_fp32(self, x):
        return x @ self.W + self.b

    def quantize(self, scale_in, calib_x):
        self.scale_in = scale_in
        self.scale_w = max(np.abs(self.W).max(), 1e-8) / 127.0
        self.W_i8 = sym_quantize(self.W, self.scale_w)
        self.b_i32 = np.round(self.b / (scale_in * self.scale_w)).astype(np.int32)

        calib_out = self.forward_fp32(calib_x)
        self.scale_out = max(np.abs(calib_out).max(), 1e-8) / 127.0
        m = (scale_in * self.scale_w) / self.scale_out
        self.M0, self.shift = quantize_multiplier(m)
        return self.scale_out, calib_out

    def forward_int8(self, x_i8, backend):
        M, K = x_i8.shape
        schedule = plan(M=M, K=K, N=self.out_f)
        acc, stats = execute(schedule, x_i8, self.W_i8, backend)
        acc = acc + self.b_i32
        if self.output:
            return acc, stats
        out = apply_requant(acc, int(self.M0), int(self.shift))
        out = np.clip(out, -127, 127).astype(np.int8)
        return out, stats
