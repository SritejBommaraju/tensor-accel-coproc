// Register map for cmd_queue_regs.sv (rtl/mmio/cmd_queue_regs.sv), matching a plain
// SW/SD/LW/LD load-store data port. Meant to compile unchanged for rv64-ooo-core.
#ifndef COPROC_MMIO_H
#define COPROC_MMIO_H

#include <stdint.h>

#ifndef COPROC_BASE
#define COPROC_BASE 0x10000000UL
#endif

#define COPROC_REG_W_BASE   (COPROC_BASE + 0x00)
#define COPROC_REG_A_BASE   (COPROC_BASE + 0x08)
#define COPROC_REG_C_BASE   (COPROC_BASE + 0x10)
#define COPROC_REG_M_ROWS   (COPROC_BASE + 0x18)
#define COPROC_REG_CMD      (COPROC_BASE + 0x20)
#define COPROC_REG_STATUS   (COPROC_BASE + 0x28)
#define COPROC_REG_IRQ      (COPROC_BASE + 0x30)
#define COPROC_REG_ID       (COPROC_BASE + 0x38)

#define COPROC_STATUS_BUSY_MASK        0x1UL
#define COPROC_STATUS_QFULL_MASK       0x2UL
#define COPROC_STATUS_QEMPTY_MASK      0x4UL
#define COPROC_STATUS_QCOUNT_SHIFT     4
#define COPROC_STATUS_QCOUNT_MASK      0xFUL
#define COPROC_STATUS_DONE_COUNT_SHIFT 16
#define COPROC_STATUS_DONE_COUNT_MASK  0xFFFFUL

static inline void coproc_reg_write(uintptr_t addr, uint64_t val) {
    *(volatile uint64_t*)addr = val;
}

static inline uint64_t coproc_reg_read(uintptr_t addr) {
    return *(volatile uint64_t*)addr;
}

// enqueues one matmul command (w/a/c are word addresses into the shared scratchpad, m is row count)
static inline void coproc_matmul(uint64_t w, uint64_t a, uint64_t c, uint64_t m) {
    coproc_reg_write(COPROC_REG_W_BASE, w);
    coproc_reg_write(COPROC_REG_A_BASE, a);
    coproc_reg_write(COPROC_REG_C_BASE, c);
    coproc_reg_write(COPROC_REG_M_ROWS, m);
    coproc_reg_write(COPROC_REG_CMD, 1);
}

// spins until the command queue has drained and the datapath is idle
static inline void coproc_wait(void) {
    uint64_t status;
    do {
        status = coproc_reg_read(COPROC_REG_STATUS);
    } while (!(status & COPROC_STATUS_QEMPTY_MASK) || (status & COPROC_STATUS_BUSY_MASK));
}

#endif // COPROC_MMIO_H
