# tensor-accel-coproc

Weight-stationary systolic array tensor accelerator, coprocessor to rv64-ooo-core.

## Status
Seed: 4x4 INT8 systolic array PE grid + Verilator TB computing a matmul, checked against a
Python golden model. Everything below is roadmap.

## Roadmap
1. 4x4 systolic array seed (this), INT8 MAC, INT32 accumulate
2. Parameterize to 8x8 then 16x16
3. Double-buffered SRAM scratchpads, DMA over AXI
4. MMIO command queue driven by rv64-ooo-core (or custom instruction)
5. C++/Python tiling/scheduling layer mapping a quantized network (MNIST/tiny CNN) onto it
6. Metrics: MACs/cycle, utilization %, TOPS at signoff freq, energy/MAC, roofline
7. UVM env with C++ golden model, SVA, coverage, formal on scratchpad arbitration/DMA
8. Clock gating + measured dynamic power reduction
9. LibreLane/IHP sg13g2 PD flow: synth, STA, gate-level regression, GDS

## Build
```
cd sim
make run
```
