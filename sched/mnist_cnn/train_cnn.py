#!/usr/bin/env python3
"""Train Conv2d(1->8,3x3) -> ReLU -> MaxPool2x2 -> Flatten -> Dense(1352->10) on MNIST.
Hand-written backprop via im2col, Adam. Weight layout matches nn.layers.Conv2d/Dense."""
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCHED_DIR = os.path.dirname(HERE)
sys.path.insert(0, SCHED_DIR)
sys.path.insert(0, os.path.join(SCHED_DIR, "mnist"))
sys.path.insert(0, os.path.join(SCHED_DIR, "nn"))

from fetch_mnist import load_mnist  # noqa: E402
from layers import im2col  # noqa: E402

OUT = os.path.join(HERE, "weights_fp32.npz")

C_OUT = 8
EPOCHS = 4
BATCH = 128
LR = 1e-3
TRAIN_N = 10000  # subset, keeps training well under the time budget
FLAT_DIM = 8 * 13 * 13


def softmax_xent_grad(logits, labels):
    z = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(z)
    probs = exp / exp.sum(axis=1, keepdims=True)
    n = logits.shape[0]
    loss = -np.log(probs[np.arange(n), labels] + 1e-12).mean()
    dlogits = probs.copy()
    dlogits[np.arange(n), labels] -= 1
    dlogits /= n
    return loss, dlogits


class Adam:
    def __init__(self, params, lr=LR, b1=0.9, b2=0.999, eps=1e-8):
        self.lr, self.b1, self.b2, self.eps = lr, b1, b2, eps
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}
        self.t = 0

    def step(self, params, grads):
        self.t += 1
        for k in params:
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * grads[k]
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * grads[k] ** 2
            mhat = self.m[k] / (1 - self.b1 ** self.t)
            vhat = self.v[k] / (1 - self.b2 ** self.t)
            params[k] -= self.lr * mhat / (np.sqrt(vhat) + self.eps)


def forward(params, x):
    """x: (N,1,28,28). Returns intermediates needed for backward."""
    cols, (N, OH, OW) = im2col(x, 3, 3)  # (N*26*26, 9)
    Wmat = params["Wc"].reshape(C_OUT, -1).T  # (9, 8)
    conv_pre = cols @ Wmat + params["bc"]  # (N*26*26, 8)
    conv_relu = np.maximum(conv_pre, 0)
    conv_map = conv_relu.reshape(N, OH, OW, C_OUT).transpose(0, 3, 1, 2)  # (N,8,26,26)

    N_, C, H, W = conv_map.shape
    pool_in = conv_map.reshape(N_, C, H // 2, 2, W // 2, 2)
    pooled = pool_in.max(axis=(3, 5))  # (N,8,13,13)
    flat = pooled.reshape(N_, -1)  # (N, 1352)

    logits = flat @ params["Wd"] + params["bd"]
    return dict(cols=cols, conv_pre=conv_pre, conv_relu=conv_relu, conv_map=conv_map,
                pool_in=pool_in, pooled=pooled, flat=flat, logits=logits, N=N, OH=OH, OW=OW)


def backward(params, x, cache, dlogits):
    grads = {}
    flat = cache["flat"]
    grads["Wd"] = flat.T @ dlogits
    grads["bd"] = dlogits.sum(axis=0)
    dflat = dlogits @ params["Wd"].T
    N, C, H13, W13 = cache["pooled"].shape
    dpooled = dflat.reshape(N, C, H13, W13)

    # maxpool backward: route grad to the argmax position in each 2x2 window
    pool_in = cache["pool_in"]
    N_, C_, H2, _, W2, _ = pool_in.shape
    dpool_in = np.zeros_like(pool_in)
    win = pool_in.reshape(N_, C_, H2, W2, 4)
    idx = win.argmax(axis=4)
    dpool_in_flat = dpool_in.reshape(N_, C_, H2, W2, 4)
    np.put_along_axis(dpool_in_flat, idx[..., None], dpooled[..., None], axis=4)
    dconv_map = dpool_in.reshape(N_, C_, H2 * 2, W2 * 2)

    dconv_relu = dconv_map.transpose(0, 2, 3, 1).reshape(-1, C_OUT)
    dconv_pre = dconv_relu * (cache["conv_pre"] > 0)
    grads["Wc"] = (cache["cols"].T @ dconv_pre).T.reshape(C_OUT, 1, 3, 3)
    grads["bc"] = dconv_pre.sum(axis=0)
    return grads


def accuracy(params, x, y, batch=1000):
    correct = 0
    for i in range(0, len(x), batch):
        logits = forward(params, x[i:i + batch])["logits"]
        correct += (logits.argmax(axis=1) == y[i:i + batch]).sum()
    return correct / len(x)


def main():
    t0 = time.time()
    tr_x, tr_y, te_x, te_y = load_mnist()
    tr_x = (tr_x[:TRAIN_N].astype(np.float32) / 255.0).reshape(-1, 1, 28, 28)
    tr_y = tr_y[:TRAIN_N].astype(np.int64)
    te_x = (te_x.astype(np.float32) / 255.0).reshape(-1, 1, 28, 28)
    te_y = te_y.astype(np.int64)

    rng = np.random.default_rng(0)
    params = {
        "Wc": (rng.standard_normal((C_OUT, 1, 3, 3)) * np.sqrt(2.0 / 9)).astype(np.float32),
        "bc": np.zeros(C_OUT, dtype=np.float32),
        "Wd": (rng.standard_normal((FLAT_DIM, 10)) * np.sqrt(2.0 / FLAT_DIM)).astype(np.float32),
        "bd": np.zeros(10, dtype=np.float32),
    }
    opt = Adam(params)

    n = tr_x.shape[0]
    for epoch in range(EPOCHS):
        perm = rng.permutation(n)
        tot_loss = 0.0
        for i in range(0, n, BATCH):
            idx = perm[i:i + BATCH]
            xb, yb = tr_x[idx], tr_y[idx]
            cache = forward(params, xb)
            loss, dlogits = softmax_xent_grad(cache["logits"], yb)
            grads = backward(params, xb, cache, dlogits)
            opt.step(params, grads)
            tot_loss += loss * len(idx)
        acc = accuracy(params, te_x, te_y)
        print(f"epoch {epoch + 1}/{EPOCHS} loss={tot_loss / n:.4f} test_acc={acc * 100:.2f}%")

    final_acc = accuracy(params, te_x, te_y)
    print(f"fp32 CNN test accuracy: {final_acc * 100:.2f}% ({time.time() - t0:.1f}s)")
    np.savez(OUT, W=params["Wc"], b=params["bc"], Wd=params["Wd"], bd=params["bd"])
    print(f"saved weights to {OUT}")


if __name__ == "__main__":
    main()
