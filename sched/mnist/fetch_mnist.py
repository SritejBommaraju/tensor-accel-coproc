#!/usr/bin/env python3
"""Download and parse MNIST IDX files, caching under sched/mnist/data/."""
import gzip
import os
import sys
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

FILES = {
    "train-images": "train-images-idx3-ubyte.gz",
    "train-labels": "train-labels-idx1-ubyte.gz",
    "test-images": "t10k-images-idx3-ubyte.gz",
    "test-labels": "t10k-labels-idx1-ubyte.gz",
}

MIRRORS = [
    "https://yann.lecun.com/exdb/mnist/{name}",
    "https://storage.googleapis.com/cvdf-datasets/mnist/{name}",
    "https://ossci-datasets.s3.amazonaws.com/mnist/{name}",
]


def _download(name):
    dest = os.path.join(DATA_DIR, name)
    if os.path.exists(dest):
        return dest
    os.makedirs(DATA_DIR, exist_ok=True)
    last_err = None
    for mirror in MIRRORS:
        url = mirror.format(name=name)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
                f.write(resp.read())
            return dest
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(
        f"could not download {name} from any mirror ({MIRRORS}); last error: {last_err}"
    )


def _read_idx_images(path):
    with gzip.open(path, "rb") as f:
        magic = int.from_bytes(f.read(4), "big")
        assert magic == 2051, f"bad magic {magic} in {path}"
        n = int.from_bytes(f.read(4), "big")
        rows = int.from_bytes(f.read(4), "big")
        cols = int.from_bytes(f.read(4), "big")
        buf = f.read(n * rows * cols)
        return np.frombuffer(buf, dtype=np.uint8).reshape(n, rows * cols)


def _read_idx_labels(path):
    with gzip.open(path, "rb") as f:
        magic = int.from_bytes(f.read(4), "big")
        assert magic == 2049, f"bad magic {magic} in {path}"
        n = int.from_bytes(f.read(4), "big")
        buf = f.read(n)
        return np.frombuffer(buf, dtype=np.uint8)


def load_mnist():
    """Returns (train_images, train_labels, test_images, test_labels) as uint8 arrays."""
    paths = {k: _download(v) for k, v in FILES.items()}
    train_images = _read_idx_images(paths["train-images"])
    train_labels = _read_idx_labels(paths["train-labels"])
    test_images = _read_idx_images(paths["test-images"])
    test_labels = _read_idx_labels(paths["test-labels"])
    return train_images, train_labels, test_images, test_labels


if __name__ == "__main__":
    try:
        tr_x, tr_y, te_x, te_y = load_mnist()
    except Exception as e:
        print(f"FETCH FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"train images {tr_x.shape} labels {tr_y.shape}")
    print(f"test images {te_x.shape} labels {te_y.shape}")
