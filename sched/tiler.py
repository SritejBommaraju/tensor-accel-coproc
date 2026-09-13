"""Weight-stationary tiling scheduler: partitions MxK @ KxN into 4x4 weight tiles."""
import subprocess
import numpy as np

TILE = 4


class Job:
    """One weight-tile load streaming all M rows of A[:, kt*4:(kt+1)*4]."""
    def __init__(self, kt, nt, Wt, At):
        self.kt = kt
        self.nt = nt
        self.Wt = Wt  # (tile, tile) int8
        self.At = At  # (M, tile) int8


def plan(M, K, N, tile=TILE):
    """Weight-stationary schedule: for each (kt, nt) weight tile, one job streaming all M rows."""
    n_kt = -(-K // tile)
    n_nt = -(-N // tile)
    schedule = []
    for nt in range(n_nt):
        for kt in range(n_kt):
            schedule.append((kt, nt))
    return schedule


def _pad_tile_2d(mat, r0, r1, c0, c1, dtype=np.int8):
    """Slice mat[r0:r1, c0:c1] zero-padded to (r1-r0, c1-c0)."""
    out = np.zeros((r1 - r0, c1 - c0), dtype=dtype)
    r_hi = min(r1, mat.shape[0])
    c_hi = min(c1, mat.shape[1])
    if r0 < r_hi and c0 < c_hi:
        out[:r_hi - r0, :c_hi - c0] = mat[r0:r_hi, c0:c_hi]
    return out


class NumpyBackend:
    def run_tile(self, Wt, At):
        return At.astype(np.int32) @ Wt.astype(np.int32)


class VerilatorBackend:
    """Drives sched/obj_dir/Vtop as a single persistent subprocess for the whole run."""
    def __init__(self, binary=None):
        if binary is None:
            import os
            binary = os.path.join(os.path.dirname(os.path.abspath(__file__)), "obj_dir", "Vtop")
        self.proc = subprocess.Popen(
            [binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def run_tile(self, Wt, At):
        M = At.shape[0]
        p = self.proc
        p.stdin.write(f"TILE {M}\n")
        for i in range(TILE):
            for j in range(TILE):
                p.stdin.write(f"{int(Wt[i, j])}\n")
        for m in range(M):
            p.stdin.write(" ".join(str(int(x)) for x in At[m]) + "\n")
        p.stdin.flush()

        Ct = np.zeros((M, TILE), dtype=np.int32)
        for m in range(M):
            vals = p.stdout.readline().split()
            Ct[m] = [int(v) for v in vals]
        end_line = p.stdout.readline().split()
        cycles = int(end_line[1])
        self.last_cycles = cycles
        return Ct

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()


def execute(schedule, A, W, backend, tile=TILE):
    M, K = A.shape
    K2, N = W.shape
    assert K == K2
    n_kt = -(-K // tile)
    n_nt = -(-N // tile)

    C = np.zeros((M, n_nt * tile), dtype=np.int32)
    weight_loads = 0
    total_cycles = 0
    for kt, nt in schedule:
        Wt = _pad_tile_2d(W, kt * tile, (kt + 1) * tile, nt * tile, (nt + 1) * tile)
        At = _pad_tile_2d(A, 0, M, kt * tile, (kt + 1) * tile)
        Ct = backend.run_tile(Wt, At)
        C[:, nt * tile:(nt + 1) * tile] += Ct
        weight_loads += 1
        total_cycles += getattr(backend, "last_cycles", 0)

    C = C[:, :N]
    macs = M * K * N
    stats = {
        "tiles": len(schedule),
        "weight_loads": weight_loads,
        "macs": macs,
        "cycles": total_cycles,
        "macs_per_cycle": (macs / total_cycles) if total_cycles else float("inf"),
    }
    return C, stats
