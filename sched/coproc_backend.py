"""CoprocBackend: drives the tiling scheduler through the MMIO+AXI path only -- register
writes/reads and host-memory writes/reads, exactly what a real driver against
sw/coproc_mmio.h would do. No peeking at internal RTL signals beyond that contract.
"""
import os
import subprocess
import numpy as np

TILE = 4
MAX_ROWS = 1024

COPROC_BASE = 0x10000000
REG_W_BASE = COPROC_BASE + 0x00
REG_A_BASE = COPROC_BASE + 0x08
REG_C_BASE = COPROC_BASE + 0x10
REG_M_ROWS = COPROC_BASE + 0x18
REG_CMD = COPROC_BASE + 0x20
REG_STATUS = COPROC_BASE + 0x28

STATUS_BUSY_MASK = 0x1
STATUS_QEMPTY_MASK = 0x4

QUEUE_DEPTH = 4

# host-memory layout (matches sim/axi/tb_axi.cpp's convention): word = N int8 lanes for the
# read RAM (byte addr = word*N), word = N int32 lanes for the write RAM (byte addr = word*4N).
RD_WORD_BYTES = TILE
WR_WORD_BYTES = TILE * 4

# disjoint per-slot regions of host memory so up to QUEUE_DEPTH chunk commands can be enqueued
# before any of them is waited on. Sized for one full tile (TILE weight rows) + MAX_ROWS
# activation/result rows per slot, generously spaced in the (very large) sim address spaces.
RD_SLOT_WORDS = TILE + MAX_ROWS
WR_SLOT_WORDS = MAX_ROWS


class CoprocBackend:
    """Drives sched/obj_dir_coproc/Vcoproc_axi_sim_top as a single persistent subprocess."""

    def __init__(self, binary=None, stall=False):
        if binary is None:
            binary = os.path.join(os.path.dirname(os.path.abspath(__file__)), "obj_dir_coproc", "Vcoproc_axi_sim_top")
        self.proc = subprocess.Popen(
            [binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self.n_commands = 0
        self.rd_beats = 0
        self.wr_beats = 0
        self.total_cycles = 0
        self.last_cycles = 0
        if stall:
            self._send(f"STALL f f")

    def _send(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        return self.proc.stdout.readline().strip()

    def _regw(self, addr, val):
        self._send(f"REGW {addr:x} {val:x}")

    def _regr(self, addr):
        return int(self._send(f"REGR {addr:x}"), 16)

    def _memw(self, region, addr, data):
        self._send(f"MEMW {region} {addr:x} {len(data)} {data.hex()}")

    def _memr(self, region, addr, n):
        return bytes.fromhex(self._send(f"MEMR {region} {addr:x} {n}"))

    def _tick(self, n):
        self._send(f"TICK {n}")

    def _cyc(self):
        return int(self._send("CYC"))

    def beats(self):
        """Total (rd_beats, wr_beats) AXI beats retired so far, for throughput reporting."""
        rd, wr = self._send("BEATS").split()
        return int(rd), int(wr)

    def run_tile(self, Wt, At):
        M = At.shape[0]
        Wt = np.asarray(Wt, dtype=np.int8)
        At = np.asarray(At, dtype=np.int8)

        # chunk M into <= MAX_ROWS-row commands, one host-memory slot per queue position so up
        # to QUEUE_DEPTH chunks can be in flight (enqueued) at once, as the 4-deep FIFO allows
        chunks = []
        m0 = 0
        while m0 < M:
            chunks.append((m0, min(MAX_ROWS, M - m0)))
            m0 += MAX_ROWS
        if not chunks:
            chunks = [(0, 0)]  # M == 0: nothing to stream, but still issue one no-op-ish chunk

        cyc_start = self._cyc()
        Ct = np.zeros((M, TILE), dtype=np.int32)

        i = 0
        while i < len(chunks):
            batch = chunks[i:i + QUEUE_DEPTH]
            for slot, (row0, rows) in enumerate(batch):
                w_base = slot * RD_SLOT_WORDS * RD_WORD_BYTES
                a_base = w_base + TILE * RD_WORD_BYTES
                c_base = slot * WR_SLOT_WORDS * WR_WORD_BYTES

                w_bytes = Wt.tobytes()  # row-major, TILE rows x TILE int8 lanes -> matches word layout
                self._memw("RD", w_base, w_bytes)
                a_bytes = At[row0:row0 + rows].tobytes()
                self._memw("RD", a_base, a_bytes)

                self._regw(REG_W_BASE, w_base)
                self._regw(REG_A_BASE, a_base)
                self._regw(REG_C_BASE, c_base)
                self._regw(REG_M_ROWS, rows)
                self._regw(REG_CMD, 1)
                self.n_commands += 1

            # coproc_wait(): poll STATUS until queue_empty & !busy, exactly like sw/coproc_mmio.h.
            # Advance in coarse batches between polls (still driver-visible: a real poll loop
            # over a real bus also doesn't resample every single clock) to keep subprocess
            # round-trips from dominating wall-clock time.
            poll_batch = 65536
            while True:
                self._tick(poll_batch)
                status = self._regr(REG_STATUS)
                if (status & STATUS_QEMPTY_MASK) and not (status & STATUS_BUSY_MASK):
                    break

            for slot, (row0, rows) in enumerate(batch):
                if rows == 0:
                    continue
                c_base = slot * WR_SLOT_WORDS * WR_WORD_BYTES
                raw = self._memr("WR", c_base, rows * WR_WORD_BYTES)
                Ct[row0:row0 + rows] = np.frombuffer(raw, dtype=np.int32).reshape(rows, TILE)

            i += len(batch)

        cyc_end = self._cyc()
        self.last_cycles = cyc_end - cyc_start
        self.total_cycles += self.last_cycles
        return Ct

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()
