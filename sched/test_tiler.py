import math
import unittest
import numpy as np

from tiler import plan, execute, NumpyBackend

SHAPES = [(4, 4, 4), (16, 12, 8), (5, 7, 3), (1, 4, 4), (64, 64, 64), (33, 17, 9)]


class TestTiler(unittest.TestCase):
    def test_shapes_match_numpy(self):
        rng = np.random.default_rng(0)
        for M, K, N in SHAPES:
            A = rng.integers(-128, 128, size=(M, K), dtype=np.int8)
            W = rng.integers(-128, 128, size=(K, N), dtype=np.int8)
            schedule = plan(M, K, N)
            C, stats = execute(schedule, A, W, NumpyBackend())

            expected = A.astype(np.int32) @ W.astype(np.int32)
            with self.subTest(shape=(M, K, N)):
                np.testing.assert_array_equal(C, expected)
                self.assertEqual(C.shape, (M, N))
                expected_loads = math.ceil(K / 4) * math.ceil(N / 4)
                self.assertEqual(stats["weight_loads"], expected_loads)
                self.assertEqual(stats["tiles"], expected_loads)


if __name__ == "__main__":
    unittest.main()
