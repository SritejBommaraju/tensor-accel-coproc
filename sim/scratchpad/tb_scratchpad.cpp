#include <cstdio>
#include <cstdint>
#include <vector>
#include <random>
#include "Vscratchpad_dbuf.h"
#include "verilated.h"

static const int DEPTH = 256;

static void tick(Vscratchpad_dbuf* dut) {
    dut->clk = 0; dut->eval();
    dut->clk = 1; dut->eval();
}

// C++ shadow model of both banks, mirroring the RTL's exact per-cycle sequencing:
// writes hit the fill bank (the bank consume_bank is not pointing at), reads
// sample the consume bank as of this cycle and register the result next cycle,
// and a same-cycle swap cannot affect a read already in flight.
struct Shadow {
    std::vector<uint32_t> mem[2];
    int consume_bank = 0;
    bool rd_valid = false;
    uint32_t rd_data = 0;

    Shadow() : mem{std::vector<uint32_t>(DEPTH, 0), std::vector<uint32_t>(DEPTH, 0)} {}

    void tick(bool rst, bool wr_en, int wr_addr, uint32_t wr_data,
              bool rd_en, int rd_addr, bool swap) {
        int fill_bank = 1 - consume_bank;
        uint32_t sampled = rd_en ? mem[consume_bank][rd_addr] : rd_data;
        if (wr_en) mem[fill_bank][wr_addr] = wr_data;
        if (rst) {
            consume_bank = 1;
            rd_valid = false;
            rd_data = 0;
        } else {
            if (swap) consume_bank = 1 - consume_bank;
            rd_valid = rd_en;
            if (rd_en) rd_data = sampled;
        }
    }
};

static bool check(Vscratchpad_dbuf* dut, Shadow& sh, int cycle) {
    if (dut->rd_valid != (sh.rd_valid ? 1 : 0)) {
        printf("FAIL cycle %d: rd_valid=%d expected %d\n", cycle, dut->rd_valid, sh.rd_valid);
        return false;
    }
    if (sh.rd_valid && dut->rd_data != sh.rd_data) {
        printf("FAIL cycle %d: rd_data=%u expected %u\n", cycle, dut->rd_data, sh.rd_data);
        return false;
    }
    return true;
}

static void reset(Vscratchpad_dbuf* dut, Shadow& sh) {
    dut->rst = 1; dut->wr_en = 0; dut->rd_en = 0; dut->swap = 0;
    sh.tick(true, false, 0, 0, false, 0, false);
    tick(dut);
    dut->rst = 0;
}

// (a) fill bank 0, swap, read back while filling bank 1, swap, read bank 1, confirm bank 0 unchanged.
static bool test_directed_a() {
    Vscratchpad_dbuf* dut = new Vscratchpad_dbuf;
    Shadow sh;
    reset(dut, sh);

    if (dut->fill_bank != 0 || dut->consume_bank != 1) {
        printf("FAIL a: post-reset fill=%d consume=%d, expected 0/1\n", dut->fill_bank, dut->consume_bank);
        delete dut; return false;
    }

    // fill bank 0 with pattern addr*3+1
    for (int a = 0; a < DEPTH; a++) {
        dut->wr_en = 1; dut->wr_addr = a; dut->wr_data = a * 3 + 1;
        dut->rd_en = 0; dut->swap = 0;
        sh.tick(false, true, a, a * 3 + 1, false, 0, false);
        tick(dut);
        if (!check(dut, sh, a)) { delete dut; return false; }
    }
    dut->wr_en = 0;

    // swap: bank0 becomes consume, bank1 becomes fill
    dut->swap = 1;
    sh.tick(false, false, 0, 0, false, 0, true);
    tick(dut);
    check(dut, sh, -1);
    dut->swap = 0;
    if (dut->fill_bank != 1 || dut->consume_bank != 0) {
        printf("FAIL a: post-swap1 fill=%d consume=%d\n", dut->fill_bank, dut->consume_bank);
        delete dut; return false;
    }

    // read bank0 back while filling bank1 with pattern addr*5+2
    for (int a = 0; a < DEPTH; a++) {
        dut->rd_en = 1; dut->rd_addr = a;
        dut->wr_en = 1; dut->wr_addr = a; dut->wr_data = a * 5 + 2;
        sh.tick(false, true, a, a * 5 + 2, true, a, false);
        tick(dut);
        if (!check(dut, sh, 1000 + a)) { delete dut; return false; }
        uint32_t expect = a * 3 + 1;
        if (dut->rd_data != expect) {
            printf("FAIL a: bank0 readback[%d]=%u expected %u\n", a, dut->rd_data, expect);
            delete dut; return false;
        }
    }
    dut->wr_en = 0; dut->rd_en = 0;

    // swap back: bank1 becomes consume
    dut->swap = 1;
    sh.tick(false, false, 0, 0, false, 0, true);
    tick(dut);
    dut->swap = 0;
    if (dut->fill_bank != 0 || dut->consume_bank != 1) {
        printf("FAIL a: post-swap2 fill=%d consume=%d\n", dut->fill_bank, dut->consume_bank);
        delete dut; return false;
    }

    // read bank1 back, confirm pattern from the fill step above
    for (int a = 0; a < DEPTH; a++) {
        dut->rd_en = 1; dut->rd_addr = a;
        sh.tick(false, false, 0, 0, true, a, false);
        tick(dut);
        if (!check(dut, sh, 2000 + a)) { delete dut; return false; }
        uint32_t expect = a * 5 + 2;
        if (dut->rd_data != expect) {
            printf("FAIL a: bank1 readback[%d]=%u expected %u\n", a, dut->rd_data, expect);
            delete dut; return false;
        }
    }
    dut->rd_en = 0;

    // confirm bank0 (now fill, untouched since first fill) still holds original pattern:
    // swap once more to make bank0 consume again and spot-check a few addresses.
    dut->swap = 1; sh.tick(false, false, 0, 0, false, 0, true); tick(dut); dut->swap = 0;
    for (int a = 0; a < DEPTH; a += 37) {
        dut->rd_en = 1; dut->rd_addr = a;
        sh.tick(false, false, 0, 0, true, a, false);
        tick(dut);
        if (!check(dut, sh, 3000 + a)) { delete dut; return false; }
        uint32_t expect = a * 3 + 1;
        if (dut->rd_data != expect) {
            printf("FAIL a: bank0 unchanged check[%d]=%u expected %u\n", a, dut->rd_data, expect);
            delete dut; return false;
        }
    }

    delete dut;
    printf("PASS directed (a)\n");
    return true;
}

// (b) read and swap issued on the same cycle returns data from the pre-swap consume bank.
static bool test_directed_b() {
    Vscratchpad_dbuf* dut = new Vscratchpad_dbuf;
    Shadow sh;
    reset(dut, sh);

    // post-reset: fill=bank0, consume=bank1. Write 0xAAAA into fill (bank0) at addr5.
    dut->wr_en = 1; dut->wr_addr = 5; dut->wr_data = 0xAAAA;
    sh.tick(false, true, 5, 0xAAAA, false, 0, false);
    tick(dut);

    // swap: now fill=bank1, consume=bank0 (holds 0xAAAA). Write 0xBBBB into fill (bank1) at addr5.
    dut->swap = 1;
    sh.tick(false, false, 0, 0, false, 0, true);
    tick(dut);
    dut->swap = 0;
    dut->wr_addr = 5; dut->wr_data = 0xBBBB;
    sh.tick(false, true, 5, 0xBBBB, false, 0, false);
    tick(dut);
    dut->wr_en = 0;

    // now: consume=bank0 holds 0xAAAA at addr5, fill=bank1 holds 0xBBBB at addr5.
    // issue rd_en and swap on the same cycle: expect data from bank0 (pre-swap consume).
    dut->rd_en = 1; dut->rd_addr = 5; dut->swap = 1;
    sh.tick(false, false, 0, 0, true, 5, true);
    tick(dut);
    dut->rd_en = 0; dut->swap = 0;
    if (!check(dut, sh, -2)) { delete dut; return false; }
    if (dut->rd_data != 0xAAAA) {
        printf("FAIL b: rd_data=%x expected 0xAAAA (pre-swap consume bank)\n", (unsigned)dut->rd_data);
        delete dut; return false;
    }
    if (dut->consume_bank != 1) {
        printf("FAIL b: swap did not take effect, consume_bank=%d\n", dut->consume_bank);
        delete dut; return false;
    }

    delete dut;
    printf("PASS directed (b)\n");
    return true;
}

// (c) reset clears fill/consume assignment to bank 0/1 regardless of prior state.
static bool test_directed_c() {
    Vscratchpad_dbuf* dut = new Vscratchpad_dbuf;
    Shadow sh;
    reset(dut, sh);

    // flip state away from the post-reset default via a swap.
    dut->swap = 1;
    sh.tick(false, false, 0, 0, false, 0, true);
    tick(dut);
    dut->swap = 0;
    if (dut->fill_bank != 1 || dut->consume_bank != 0) {
        printf("FAIL c: setup swap didn't flip state\n");
        delete dut; return false;
    }

    // reset again; must land back on fill=0, consume=1 regardless of memory contents.
    reset(dut, sh);
    if (dut->fill_bank != 0 || dut->consume_bank != 1) {
        printf("FAIL c: post-reset fill=%d consume=%d, expected 0/1\n", dut->fill_bank, dut->consume_bank);
        delete dut; return false;
    }

    delete dut;
    printf("PASS directed (c)\n");
    return true;
}

static bool test_random(uint32_t seed) {
    Vscratchpad_dbuf* dut = new Vscratchpad_dbuf;
    Shadow sh;
    reset(dut, sh);

    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> addr_dist(0, DEPTH - 1);
    std::uniform_int_distribution<uint32_t> data_dist;
    std::uniform_int_distribution<int> pct(0, 99);

    for (int cyc = 0; cyc < 20000; cyc++) {
        bool wr_en = pct(rng) < 70;
        int wr_addr = addr_dist(rng);
        uint32_t wr_data = data_dist(rng);
        bool rd_en = pct(rng) < 70;
        int rd_addr = addr_dist(rng);
        bool swap = pct(rng) < 2;

        dut->wr_en = wr_en; dut->wr_addr = wr_addr; dut->wr_data = wr_data;
        dut->rd_en = rd_en; dut->rd_addr = rd_addr; dut->swap = swap;

        sh.tick(false, wr_en, wr_addr, wr_data, rd_en, rd_addr, swap);
        tick(dut);

        if (!check(dut, sh, cyc)) { delete dut; return false; }
    }

    delete dut;
    printf("PASS random (20000 cycles)\n");
    return true;
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);

    bool pass = true;
    pass &= test_directed_a();
    pass &= test_directed_b();
    pass &= test_directed_c();
    pass &= test_random(0xC0FFEE);

    if (pass) { printf("PASS\n"); return 0; }
    printf("FAIL\n");
    return 1;
}
