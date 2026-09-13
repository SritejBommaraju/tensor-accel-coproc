import numpy as np

# Golden reference matmul for the 4x4 systolic array RTL, INT8 in / INT32 accumulate out.
def golden_matmul(weights: np.ndarray, acts: np.ndarray) -> np.ndarray:
    return acts.astype(np.int32) @ weights.astype(np.int32)

if __name__ == "__main__":
    w = np.array([[1, 2, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=np.int8)
    a = np.array([[1, 1, 1, 1]], dtype=np.int8)
    print(golden_matmul(w, a))
