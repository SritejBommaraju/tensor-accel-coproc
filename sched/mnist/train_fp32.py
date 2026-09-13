#!/usr/bin/env python3
"""Train a 784->64->10 ReLU MLP on MNIST with hand-written numpy backprop + Adam."""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_mnist import load_mnist

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "weights_fp32.npz")

HIDDEN = 64
EPOCHS = 5
BATCH = 128
LR = 1e-3


def softmax_xent_grad(logits, labels):
    """Returns (loss, dlogits) for softmax cross-entropy, mean over batch."""
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
    z1 = x @ params["W1"] + params["b1"]
    a1 = np.maximum(z1, 0)
    z2 = a1 @ params["W2"] + params["b2"]
    return z1, a1, z2


def backward(params, x, z1, a1, dlogits):
    grads = {}
    grads["W2"] = a1.T @ dlogits
    grads["b2"] = dlogits.sum(axis=0)
    da1 = dlogits @ params["W2"].T
    dz1 = da1 * (z1 > 0)
    grads["W1"] = x.T @ dz1
    grads["b1"] = dz1.sum(axis=0)
    return grads


def accuracy(params, x, y):
    _, _, logits = forward(params, x)
    return (logits.argmax(axis=1) == y).mean()


def main():
    t0 = time.time()
    tr_x, tr_y, te_x, te_y = load_mnist()
    tr_x = tr_x.astype(np.float32) / 255.0
    te_x = te_x.astype(np.float32) / 255.0
    tr_y = tr_y.astype(np.int64)
    te_y = te_y.astype(np.int64)

    rng = np.random.default_rng(0)
    params = {
        "W1": (rng.standard_normal((784, HIDDEN)) * np.sqrt(2.0 / 784)).astype(np.float32),
        "b1": np.zeros(HIDDEN, dtype=np.float32),
        "W2": (rng.standard_normal((HIDDEN, 10)) * np.sqrt(2.0 / HIDDEN)).astype(np.float32),
        "b2": np.zeros(10, dtype=np.float32),
    }
    opt = Adam(params)

    n = tr_x.shape[0]
    for epoch in range(EPOCHS):
        perm = rng.permutation(n)
        tot_loss = 0.0
        for i in range(0, n, BATCH):
            idx = perm[i:i + BATCH]
            xb, yb = tr_x[idx], tr_y[idx]
            z1, a1, logits = forward(params, xb)
            loss, dlogits = softmax_xent_grad(logits, yb)
            grads = backward(params, xb, z1, a1, dlogits)
            opt.step(params, grads)
            tot_loss += loss * len(idx)
        acc = accuracy(params, te_x, te_y)
        print(f"epoch {epoch + 1}/{EPOCHS} loss={tot_loss / n:.4f} test_acc={acc * 100:.2f}%")

    final_acc = accuracy(params, te_x, te_y)
    print(f"fp32 test accuracy: {final_acc * 100:.2f}% ({time.time() - t0:.1f}s)")
    np.savez(OUT, **params)
    print(f"saved weights to {OUT}")


if __name__ == "__main__":
    main()
