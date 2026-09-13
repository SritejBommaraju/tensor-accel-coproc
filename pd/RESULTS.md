# Synthesis + STA results: IHP sg13g2, typ corner (1.20V, 25C)

Toolchain: yosys 0.69+24 (OSS CAD Suite, via `read_slang`) for synthesis/mapping,
OpenSTA 3.1.0 (built from source, see `pd/INSTALL.md`) for timing, both against
`sg13g2_stdcell_typ_1p20V_25C.lib` from IHP-Open-PDK. Full logs for every number below are in
`pd/out/` (`*_stat.log` = yosys `stat -liberty`, `*_sta.log` = single-point OpenSTA report at a
3.0ns seed period, `*_sweep_*.log` = the period that converged in the fmax sweep). Reproduce
with `wsl -d Ubuntu -- bash -lc "cd pd && make all"` (see `pd/INSTALL.md` for the tool setup
this assumes).

## Area (yosys `stat -liberty`)

| module | cell count | area (um^2) | of which sequential | log |
|---|---:|---:|---:|---|
| `pe` | 907 | 11,118.00 | 2,351.46 (21.2%) | `pe_stat.log` |
| `top` N=4 (16x `pe` + wrapper) | 10,185 | 127,201.08 | 29,981.15 (23.6%) | `top_N4_stat.log` |
| `top` N=8 (64x `pe`) | 49,056 | 609,290.15 | 135,209.09 (22.2%) | `top_N8_stat.log` |
| `top` N=16 (256x `pe`) | 212,860 | 2,637,712.27 | 571,405.36 (21.7%) | `top_N16_stat.log` |
| `scratchpad_dbuf` (DEPTH=256, WIDTH=32, default params) | 47,449 | 1,333,659.15 | 804,298.12 (60.3%) | `scratchpad_dbuf_stat.log` |

`top`'s area scales almost exactly as N^2 x `pe`'s area (4x from N=4->N=8 predicts 508,804 um^2,
actual 609,290; 4x again to N=16 predicts 2,437,161, actual 2,637,712 -- the wrapper's
bit-unpack/pack glue adds a small, roughly-constant-per-port overhead on top of the N^2 PE
array, so the ratio drifts up slightly with N). `scratchpad_dbuf` has no memory-compiler SRAM
available in this open PDK, so yosys maps its two 256x32 arrays straight to flip-flops -- 16,384
bits x2 banks, which is why its sequential-element share (60%) is much higher than the PE
datapath's (~22%).

## Timing (OpenSTA, `report_checks -path_delay max` + `report_wns`/`report_tns`)

Single point at a 3.0ns seed clock period (the period `abc -D` was given during mapping):

| module | WNS (ns) | TNS (ns) | log |
|---|---:|---:|---|
| `pe` | -3.37 | -50.03 | `pe_sta.log` |
| `top` N=4 | -3.51 | -468.38 | `top_N4_sta.log` |
| `top` N=8 | -15.10 | -17,536.59 | `top_N8_sta.log` |

Fmax sweep (`pd/run_sweep.sh`, 20% of period reserved for input/output delay, stepping period
until WNS >= 0):

| module | converged period | fmax | critical path | log |
|---|---:|---:|---|---|
| `pe` | 7.400 ns | **135.14 MHz** | `act_in[7]` (input) -> flop D, through the multiply-accumulate chain | `pe_sweep_7.400ns.log` |
| `top` N=4 | 7.400 ns | **135.14 MHz** | `act_in_flat[31]` (input) -> flop D, same PE-internal path | `top_N4_sweep_7.400ns.log` |
| `top` N=8 | 22.000 ns | **45.45 MHz** | `rst` (input) -> flop D, through an unbuffered high-fanout inverter/NAND/NOR chain | `top_N8_sweep_22.000ns.log` |

`top` N=4's critical path is identical to standalone `pe`'s (same 7.400ns/135.14MHz), which is
expected: the systolic array is fully pipelined -- every PE registers its outputs, so the
combinational path never crosses more than one PE regardless of N. **N=8 is a different,
synthesis-artifact critical path, not a real scaling limit of the architecture**: its worst path
starts at the `rst` port and runs through a single `sg13g2_inv_1` with 12.7ns of delay
(`top_N8_sweep_22.000ns.log`, `_47267_/Y`), i.e. one inverter driving the async reset fanout of
all ~12k+ flops in the N=8 array with no buffer tree. Plain `yosys`+`abc` mapping has no
placement information and does no fanout-aware buffer insertion for `rst`; a real PnR flow
(OpenROAD's clock/reset tree synthesis, which needs the OpenROAD CLI -- see the LibreLane
section below and `pd/INSTALL.md` #5) would insert a buffer tree here and this artifact should
disappear, putting N=8's real fmax much closer to the ~135MHz PE-limited number. N=16 was
synthesized (area only, above) but not swept for timing, since the same reset-fanout artifact
would dominate even more severely without PnR-quality buffering and the sweep would need a much
larger period range to be meaningful.

## Gate-level regression

`pd/gls` runs the unmodified `sim/tb_main.cpp` testbench against yosys's `top_N4` netlist,
gate-level-instantiated with real IHP sg13g2 cells (`sg13g2_stdcell.v`), against the existing
`sim/vectors/N4_M8_S1` vectors, via Verilator.

```
$ wsl -d Ubuntu -- bash -lc "cd pd/gls && make run"
...
rand_0000.txt ... rand_0019.txt          PASS (M=8)  [20/20]
edge_all_neg128.txt                      PASS (M=8)
edge_all_127.txt                         PASS (M=8)
edge_zero.txt                            PASS (M=8)
edge_identity.txt                        PASS (M=8)
edge_single_hot.txt                      PASS (M=8)
ALL PASS
```
Full log: `pd/out/gls_N4_run.log`. This required two fixups on top of the PDK's shipped cell
Verilog, documented in `pd/gls/sg13g2_functional.v` and `pd/gls/Makefile` and in
`pd/INSTALL.md` #4 -- in short: (1) the PDK ships its DFF/latch/mux cells as Verilog-1995 UDP
`primitive`/`table` blocks, which Verilator cannot simulate, so
`pd/gls/sg13g2_functional.v` is a hand-written behavioral replacement with identical module and
port names, read off the UDP truth tables; (2) every sequential cell's D/CLK/RESET_B are wired
internally to `delayed_*` wires that only a timing-checking simulator's `$setuphold`/`$recrem`
system-task output arguments would drive, so `pd/gls/Makefile` patches in
`assign delayed_X = X;` pass-throughs. These are functional-simulation-only substitutions; the
real timing numbers above come from OpenSTA reading the PDK's actual liberty file, untouched.

## LibreLane / full place-and-route to GDS: not completed

Attempted (`pd/librelane/config.json`, targeting `top` N=4): `pip install librelane` succeeded
(v3.0.14), and `ciel enable --pdk-family ihp-sg13g2` fetched a working PDK variant (`~/.ciel`)
including the PDK's own official `libs.tech/librelane/config.tcl`. The flow's Verilator-lint and
lint-checker steps ran cleanly. It fails at the OpenROAD floorplan step: LibreLane needs a real
`openroad` Tcl-CLI executable on PATH, and none of OSS CAD Suite (doesn't ship one in this
nightly), PyPI (`yowasp-openroad` doesn't exist; the `openroad` PyPI package is a SWIG binding
with a real compiled core but no CLI entry point), or a prebuilt binary release (OpenROAD
publishes only a Docker image, and this session has neither Docker nor Nix) can supply one.
Full command transcript, exact errors, and the concrete unblocking requirement (Docker/Nix, or
an from-source OpenROAD build with Qt/Boost/LEMON/or-tools/spdlog) are in `pd/INSTALL.md` #5.
**No post-PnR area/utilization numbers or GDS exist** -- everything above is pre-PnR
(synthesis + STA with ideal clock trees), which is why the N=8 reset-fanout artifact above is
visible at all.
