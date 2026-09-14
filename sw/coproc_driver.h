// Header-only C99 (also valid C++) driver library for cmd_queue_regs.sv / coproc_axi_sim_top.sv.
// Compiles unchanged on a bare-metal rv64 core (define COPROC_BAREMETAL for the default ops)
// or against a Verilator TB that supplies its own coproc_ops (dmem-port stores/loads + backdoor
// scratch memory access). No floating point, no OS calls, no dynamic allocation.
#ifndef COPROC_DRIVER_H
#define COPROC_DRIVER_H

#include <stdint.h>
#include <stddef.h>
#include "coproc_mmio.h"

#define COPROC_TILE      4      // systolic array tile size (matches N=4 lanes)
#define COPROC_QDEPTH    4      // cmd_queue_regs FIFO depth
#define COPROC_MAX_ROWS  1024   // MAX_ROWS parameter of coproc_axi_sim_top

// Every access the driver makes to the coprocessor goes through this vtable so the same
// C code runs against real MMIO (bare-metal) or a Verilator TB's backdoor/tick-based model.
typedef struct {
    void     (*reg_write)(uint64_t reg_addr, uint64_t val);
    uint64_t (*reg_read)(uint64_t reg_addr);
    void     (*mem_write)(uint64_t byte_addr, const void *src, uint64_t n);
    void     (*mem_read)(uint64_t byte_addr, void *dst, uint64_t n);
    void     (*wait_irq)(void); // blocks until the coprocessor's irq line has fired at least once
} coproc_ops;

// One scratch region per in-flight queue slot, so up to COPROC_QDEPTH commands can be enqueued
// before any result needs to be read back. Byte addresses into the shared read/write memories.
// w_base slot must hold TILE*TILE int8 (16B); a_base slot must hold COPROC_MAX_ROWS*TILE int8;
// c_base slot must hold COPROC_MAX_ROWS*TILE int32.
typedef struct {
    uint64_t w_base[COPROC_QDEPTH];
    uint64_t a_base[COPROC_QDEPTH];
    uint64_t c_base[COPROC_QDEPTH];
} coproc_buffers;

#ifdef COPROC_BAREMETAL
static inline void coproc_bm_reg_write(uint64_t addr, uint64_t val) {
    *(volatile uint64_t *)(uintptr_t)addr = val;
}
static inline uint64_t coproc_bm_reg_read(uint64_t addr) {
    return *(volatile uint64_t *)(uintptr_t)addr;
}
static inline void coproc_bm_mem_write(uint64_t addr, const void *src, uint64_t n) {
    volatile uint8_t *d = (volatile uint8_t *)(uintptr_t)addr;
    const uint8_t *s = (const uint8_t *)src;
    for (uint64_t i = 0; i < n; i++) d[i] = s[i];
}
static inline void coproc_bm_mem_read(uint64_t addr, void *dst, uint64_t n) {
    const volatile uint8_t *s = (const volatile uint8_t *)(uintptr_t)addr;
    uint8_t *d = (uint8_t *)dst;
    for (uint64_t i = 0; i < n; i++) d[i] = s[i];
}
// no interrupt controller modeled here: fall back to polling IRQ_PENDING, which is functionally
// equivalent to "block until irq fires" and is the only portable option in a header this small.
static inline void coproc_bm_wait_irq(void) {
    while (!(coproc_bm_reg_read(COPROC_REG_IRQ) & 0x2ULL)) { }
}
static const coproc_ops COPROC_BAREMETAL_OPS = {
    coproc_bm_reg_write, coproc_bm_reg_read, coproc_bm_mem_write, coproc_bm_mem_read, coproc_bm_wait_irq
};
#endif // COPROC_BAREMETAL

// zero-padded tile extraction, matching sched/tiler.py's _pad_tile_2d exactly
static inline void coproc_pack_wtile(const int8_t *W, int K, int N, int kt, int nt, int8_t out[COPROC_TILE][COPROC_TILE]) {
    for (int i = 0; i < COPROC_TILE; i++)
        for (int j = 0; j < COPROC_TILE; j++) {
            int r = kt * COPROC_TILE + i, c = nt * COPROC_TILE + j;
            out[i][j] = (r < K && c < N) ? W[(size_t)r * N + c] : 0;
        }
}
static inline void coproc_pack_atile(const int8_t *A, int M, int K, int m0, int mc, int kt, int8_t *out /* mc*4 */) {
    for (int m = 0; m < mc; m++)
        for (int j = 0; j < COPROC_TILE; j++) {
            int r = m0 + m, c = kt * COPROC_TILE + j;
            out[m * COPROC_TILE + j] = (r < M && c < K) ? A[(size_t)r * K + c] : 0;
        }
}

// enqueues one matmul-tile command in the given queue slot and packs its operands in first
static inline void coproc_issue_tile(const coproc_ops *ops, const coproc_buffers *bufs, int slot,
                                      const int8_t Wt[COPROC_TILE][COPROC_TILE], const int8_t *At, int mc) {
    ops->mem_write(bufs->w_base[slot], Wt, COPROC_TILE * COPROC_TILE);
    ops->mem_write(bufs->a_base[slot], At, (uint64_t)mc * COPROC_TILE);
    ops->reg_write(COPROC_REG_W_BASE, bufs->w_base[slot]);
    ops->reg_write(COPROC_REG_A_BASE, bufs->a_base[slot]);
    ops->reg_write(COPROC_REG_C_BASE, bufs->c_base[slot]);
    ops->reg_write(COPROC_REG_M_ROWS, (uint64_t)mc);
    ops->reg_write(COPROC_REG_CMD, 1);
}

// waits (via IRQ) until at least `want` commands have retired since `base`, RW1C-clearing
// IRQ_PENDING on every wakeup; returns the total done_count read on the last wakeup
// always takes at least one IRQ per call (even if STATUS already shows the completion, since
// the interrupt may simply already be pending) so callers get an exact 1:1 IRQ-per-retirement
// count -- never skips straight to polling STATUS without going through wait_irq/RW1C first.
static inline uint32_t coproc_wait_retired(const coproc_ops *ops, uint32_t base, uint32_t want) {
    uint32_t dc;
    do {
        ops->wait_irq();
        ops->reg_write(COPROC_REG_IRQ, 0x3); // keep IRQ_EN=1, RW1C clear IRQ_PENDING
        uint64_t status = ops->reg_read(COPROC_REG_STATUS);
        dc = (uint32_t)((status >> COPROC_STATUS_DONE_COUNT_SHIFT) & COPROC_STATUS_DONE_COUNT_MASK);
    } while ((uint32_t)(dc - base) < want);
    return dc;
}

// C[M][N] = A[M][K] @ W[K][N], weight-stationary 4x4 tiling identical to sched/tiler.py's
// (kt,nt) order and zero-padding, chunked into <=COPROC_MAX_ROWS row blocks, driven through
// the 4-deep command queue with IRQ-driven completion (never busy-polls STATUS for a result).
static inline void coproc_matmul_tiled(const coproc_ops *ops, const int8_t *A, int M, int K,
                                        const int8_t *W, int N, int32_t *C, const coproc_buffers *bufs) {
    int n_kt = (K + COPROC_TILE - 1) / COPROC_TILE;
    int n_nt = (N + COPROC_TILE - 1) / COPROC_TILE;

    ops->reg_write(COPROC_REG_IRQ, 0x3); // IRQ_EN=1, clear any stale pending

    for (int m0 = 0; m0 < M; m0 += COPROC_MAX_ROWS) {
        int mc = M - m0;
        if (mc > COPROC_MAX_ROWS) mc = COPROC_MAX_ROWS;

        for (int c = 0; c < N; c++)
            for (int m = 0; m < mc; m++)
                C[(size_t)(m0 + m) * N + c] = 0;

        int total = n_nt * n_kt; // schedule order matches sched/tiler.py::plan: nt outer, kt inner
        uint64_t status0 = ops->reg_read(COPROC_REG_STATUS);
        uint32_t base = (uint32_t)((status0 >> COPROC_STATUS_DONE_COUNT_SHIFT) & COPROC_STATUS_DONE_COUNT_MASK);
        int issued = 0, collected = 0;
        int8_t at_buf[COPROC_MAX_ROWS * COPROC_TILE];
        int32_t ct_buf[COPROC_MAX_ROWS * COPROC_TILE];

        while (collected < total) {
            // keep at most COPROC_QDEPTH commands outstanding; issue whenever there's room
            while (issued < total && issued - collected < COPROC_QDEPTH) {
                int nt = issued / n_kt, kt = issued % n_kt;
                int8_t Wt[COPROC_TILE][COPROC_TILE];
                coproc_pack_wtile(W, K, N, kt, nt, Wt);
                coproc_pack_atile(A, M, K, m0, mc, kt, at_buf);
                coproc_issue_tile(ops, bufs, issued % COPROC_QDEPTH, Wt, at_buf, mc);
                issued++;
            }
            // IRQ-driven wait for the oldest outstanding command, then read its result back
            coproc_wait_retired(ops, base, (uint32_t)(collected + 1));
            {
                int nt = collected / n_kt;
                ops->mem_read(bufs->c_base[collected % COPROC_QDEPTH], ct_buf, (uint64_t)mc * COPROC_TILE * 4);
                for (int m = 0; m < mc; m++)
                    for (int j = 0; j < COPROC_TILE; j++) {
                        int col = nt * COPROC_TILE + j;
                        if (col < N) C[(size_t)(m0 + m) * N + col] += ct_buf[m * COPROC_TILE + j];
                    }
                collected++;
            }
        }
    }
}

#endif // COPROC_DRIVER_H
