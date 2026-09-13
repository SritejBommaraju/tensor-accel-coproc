import numpy as np

# Golden reference matmul for the 4x4 systolic array RTL, INT8 in / INT32 accumulate out.
def golden_matmul(weights: np.ndarray, acts: np.ndarray) -> np.ndarray:
    return acts.astype(np.int32) @ weights.astype(np.int32)

if __name__ == "__main__":
    # self-test: golden_matmul must match plain numpy int32 matmul, including int8 overflow wraparound
    rng = np.random.default_rng(0)
    w = rng.integers(-128, 128, size=(4, 4), dtype=np.int8)
    a = rng.integers(-128, 128, size=(6, 4), dtype=np.int8)
    expect = a.astype(np.int32) @ w.astype(np.int32)
    got = golden_matmul(w, a)
    assert np.array_equal(got, expect), "golden_matmul mismatch"
    print("golden.py self-test PASS")
