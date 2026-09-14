import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED_DIR = os.path.dirname(HERE)
sys.path.insert(0, SCHED_DIR)
sys.path.insert(0, HERE)

from tiler import NumpyBackend  # noqa: E402
from layers import Conv2d, ReLU, MaxPool2x2, Flatten, Dense  # noqa: E402
from quant import quantize_graph, graph_forward_int8, pure_numpy_int8_forward, SCALE_IN_PIXELS  # noqa: E402


def direct_conv(x, W, b):
    """Reference conv: nested loops, no im2col. x:(N,Cin,H,W) W:(Cout,Cin,3,3) b:(Cout,)."""
    N, Cin, H, Wd = x.shape
    Cout = W.shape[0]
    OH, OW = H - 2, Wd - 2
    out = np.zeros((N, Cout, OH, OW), dtype=np.float32)
    for n in range(N):
        for co in range(Cout):
            for i in range(OH):
                for j in range(OW):
                    acc = b[co]
                    for ci in range(Cin):
                        for dy in range(3):
                            for dx in range(3):
                                acc += x[n, ci, i + dy, j + dx] * W[co, ci, dy, dx]
                    out[n, co, i, j] = acc
    return out


class TestConv(unittest.TestCase):
    def test_im2col_conv_matches_direct(self):
        rng = np.random.default_rng(0)
        x = rng.standard_normal((2, 3, 7, 7)).astype(np.float32)
        conv = Conv2d(3, 4)
        conv.W = rng.standard_normal((4, 3, 3, 3)).astype(np.float32)
        conv.b = rng.standard_normal(4).astype(np.float32)

        got = conv.forward_fp32(x)
        want = direct_conv(x, conv.W, conv.b)
        np.testing.assert_allclose(got, want, rtol=1e-4, atol=1e-4)


class TestInt8Graph(unittest.TestCase):
    def test_tiled_backend_matches_pure_numpy_reference(self):
        rng = np.random.default_rng(1)
        n, cin, h, w = 5, 2, 10, 10
        x_fp32 = rng.uniform(0, 1, size=(n, cin, h, w)).astype(np.float32)

        conv = Conv2d(cin, 4)
        conv.W = (rng.standard_normal((4, cin, 3, 3)) * 0.2).astype(np.float32)
        conv.b = (rng.standard_normal(4) * 0.1).astype(np.float32)
        relu = ReLU()
        pool = MaxPool2x2()
        flat = Flatten()
        flat_dim = 4 * ((h - 2) // 2) * ((w - 2) // 2)
        dense = Dense(flat_dim, 5, output=True)
        dense.W = (rng.standard_normal((flat_dim, 5)) * 0.2).astype(np.float32)
        dense.b = (rng.standard_normal(5) * 0.1).astype(np.float32)

        layers = [conv, relu, pool, flat, dense]
        quantize_graph(layers, x_fp32, scale_in=SCALE_IN_PIXELS)

        from quantize import sym_quantize
        x_i8 = sym_quantize(x_fp32, SCALE_IN_PIXELS)

        got, _ = graph_forward_int8(layers, x_i8, NumpyBackend())
        want = pure_numpy_int8_forward(layers, x_i8)
        np.testing.assert_array_equal(got, want)


class TestMLPShapes(unittest.TestCase):
    def test_three_layer_mlp_through_tiler(self):
        rng = np.random.default_rng(2)
        n = 6
        d1 = Dense(784, 128)
        d1.W = (rng.standard_normal((784, 128)) * 0.05).astype(np.float32)
        d1.b = np.zeros(128, dtype=np.float32)
        r1 = ReLU()
        d2 = Dense(128, 64)
        d2.W = (rng.standard_normal((128, 64)) * 0.1).astype(np.float32)
        d2.b = np.zeros(64, dtype=np.float32)
        r2 = ReLU()
        d3 = Dense(64, 10, output=True)
        d3.W = (rng.standard_normal((64, 10)) * 0.1).astype(np.float32)
        d3.b = np.zeros(10, dtype=np.float32)
        layers = [d1, r1, d2, r2, d3]

        x_fp32 = rng.uniform(0, 1, size=(n, 784)).astype(np.float32)
        fp32_out = x_fp32
        for layer in layers:
            fp32_out = layer.forward_fp32(fp32_out)
        self.assertEqual(fp32_out.shape, (n, 10))

        quantize_graph(layers, x_fp32, scale_in=SCALE_IN_PIXELS)
        from quantize import sym_quantize
        x_i8 = sym_quantize(x_fp32, SCALE_IN_PIXELS)
        out_i8, stats = graph_forward_int8(layers, x_i8, NumpyBackend())
        self.assertEqual(out_i8.shape, (n, 10))
        self.assertEqual(len(stats), 3)  # 3 Dense layers each ran through tiler


if __name__ == "__main__":
    unittest.main()
