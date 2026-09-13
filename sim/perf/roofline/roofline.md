# Energy / Roofline model
Cycles, MACs/cycle, utilization%, and TOPS-at-freq below come straight from `sim/perf/results.csv` (measured via Verilator). **All pJ/MAC, effective pJ/MAC, and TOPS/W figures are MODEL ESTIMATES**, computed from the per-node energy constants in `tech_params.json` (which are themselves literature estimates, not silicon measurements or PDK characterization) applied to the byte counts implied by `stream_ctrl.sv`'s memory layout. They are not measured quantities.

## sg13g2_130nm (IHP sg13g2 open-source 130nm BiCMOS PDK, digital logic corner (estimate))
Estimate basis: Horowitz ISSCC'14 45nm baseline (8b MAC = 8b add 0.03pJ + 8b mult 0.20pJ = 0.23pJ; 32b SRAM read from an 8KB array = 5pJ -> 1.25pJ/byte; register bit-flip is not in Horowitz's table, estimated here as ~0.65x the SRAM-byte-read energy per bit as a rough clocked-flop lower bound) scaled to 130nm by the (130/45)^2 rule above. SRAM write assumed equal to read absent a per-op breakdown -- a real 130nm SRAM macro (e.g. IHP's sg13g2 SRAM compiler output) would need to be characterized to replace this.

- energy/INT8 MAC: 1.9210 pJ
- energy/8b register bit-flip: 1.2530 pJ
- energy/SRAM byte read: 10.4400 pJ
- energy/SRAM byte write: 10.4400 pJ
- target clock: 500 MHz (500 MHz matches the freq_mhz used by sim/perf/tb_perf.cpp to fill the tops_at_freq column in results.csv (its default, never overridden by `make sweep`), so TOPS figures here are directly comparable to the CSV. This is NOT a claim that either node can close timing at 500MHz in real silicon -- 130nm sg13g2 in particular would typically target well under 200MHz for a design like this.)

| N | M | scenario | cycles | MACs/cycle | util% | TOPS@freq | AI (MACs/B) | pJ/MAC | eff pJ/MAC | TOPS/W |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 4 | single_load | 10 | 6.400 | 40.00 | 0.0064 | 2.000 | 1.9210 | 17.5810 | 0.114 |
| 4 | 4 | per_tile_reload | 11 | 5.818 | 36.36 | 0.0058 | 2.000 | 1.9210 | 17.5810 | 0.114 |
| 4 | 16 | single_load | 22 | 11.636 | 72.73 | 0.0116 | 3.200 | 1.9210 | 15.6235 | 0.128 |
| 4 | 16 | per_tile_reload | 23 | 11.130 | 69.57 | 0.0111 | 3.200 | 1.9210 | 15.6235 | 0.128 |
| 4 | 64 | single_load | 70 | 14.629 | 91.43 | 0.0146 | 3.765 | 1.9210 | 15.1341 | 0.132 |
| 4 | 64 | per_tile_reload | 71 | 14.423 | 90.14 | 0.0144 | 3.765 | 1.9210 | 15.1341 | 0.132 |
| 4 | 256 | single_load | 262 | 15.634 | 97.71 | 0.0156 | 3.938 | 1.9210 | 15.0118 | 0.133 |
| 4 | 256 | per_tile_reload | 263 | 15.574 | 97.34 | 0.0156 | 3.938 | 1.9210 | 15.0118 | 0.133 |
| 4 | 256 | single_load | 262 | 15.634 | 97.71 | 0.0156 | 3.938 | 1.9210 | 15.0118 | 0.133 |
| 4 | 256 | per_tile_reload | 263 | 15.574 | 97.34 | 0.0156 | 3.938 | 1.9210 | 15.0118 | 0.133 |
| 8 | 8 | single_load | 22 | 23.273 | 36.36 | 0.0233 | 4.000 | 1.9210 | 9.7510 | 0.205 |
| 8 | 8 | per_tile_reload | 23 | 22.261 | 34.78 | 0.0223 | 4.000 | 1.9210 | 9.7510 | 0.205 |
| 8 | 32 | single_load | 46 | 44.522 | 69.57 | 0.0445 | 6.400 | 1.9210 | 8.7722 | 0.228 |
| 8 | 32 | per_tile_reload | 47 | 43.574 | 68.09 | 0.0436 | 6.400 | 1.9210 | 8.7722 | 0.228 |
| 8 | 128 | single_load | 142 | 57.690 | 90.14 | 0.0577 | 7.529 | 1.9210 | 8.5276 | 0.235 |
| 8 | 128 | per_tile_reload | 143 | 57.287 | 89.51 | 0.0573 | 7.529 | 1.9210 | 8.5276 | 0.235 |
| 8 | 512 | single_load | 526 | 62.297 | 97.34 | 0.0623 | 7.877 | 1.9210 | 8.4664 | 0.236 |
| 8 | 512 | per_tile_reload | 527 | 62.178 | 97.15 | 0.0622 | 7.877 | 1.9210 | 8.4664 | 0.236 |
| 8 | 256 | single_load | 270 | 60.681 | 94.81 | 0.0607 | 7.758 | 1.9210 | 8.4868 | 0.236 |
| 8 | 256 | per_tile_reload | 271 | 60.458 | 94.46 | 0.0605 | 7.758 | 1.9210 | 8.4868 | 0.236 |
| 16 | 16 | single_load | 46 | 89.043 | 34.78 | 0.0890 | 8.000 | 1.9210 | 5.8360 | 0.343 |
| 16 | 16 | per_tile_reload | 47 | 87.149 | 34.04 | 0.0871 | 8.000 | 1.9210 | 5.8360 | 0.343 |
| 16 | 64 | single_load | 94 | 174.298 | 68.09 | 0.1743 | 12.800 | 1.9210 | 5.3466 | 0.374 |
| 16 | 64 | per_tile_reload | 95 | 172.463 | 67.37 | 0.1725 | 12.800 | 1.9210 | 5.3466 | 0.374 |
| 16 | 256 | single_load | 286 | 229.147 | 89.51 | 0.2291 | 15.059 | 1.9210 | 5.2243 | 0.383 |
| 16 | 256 | per_tile_reload | 287 | 228.348 | 89.20 | 0.2283 | 15.059 | 1.9210 | 5.2243 | 0.383 |
| 16 | 1024 | single_load | 1054 | 248.713 | 97.15 | 0.2487 | 15.754 | 1.9210 | 5.1937 | 0.385 |
| 16 | 1024 | per_tile_reload | 1055 | 248.478 | 97.06 | 0.2485 | 15.754 | 1.9210 | 5.1937 | 0.385 |
| 16 | 256 | single_load | 286 | 229.147 | 89.51 | 0.2291 | 15.059 | 1.9210 | 5.2243 | 0.383 |
| 16 | 256 | per_tile_reload | 287 | 228.348 | 89.20 | 0.2283 | 15.059 | 1.9210 | 5.2243 | 0.383 |

## generic_28nm (Generic bulk 28nm reference point (estimate), for comparison only -- not IHP sg13g2)
Estimate basis: Same Horowitz ISSCC'14 45nm baseline as sg13g2_130nm above, scaled down by the 0.45x factor stated in scaling_assumption. Included purely as an aged-but-common 'modern-ish' reference point to show the energy gap vs. the 130nm target node; not a claim about any specific 28nm PDK.

- energy/INT8 MAC: 0.1035 pJ
- energy/8b register bit-flip: 0.0675 pJ
- energy/SRAM byte read: 0.5625 pJ
- energy/SRAM byte write: 0.5625 pJ
- target clock: 500 MHz (500 MHz matches the freq_mhz used by sim/perf/tb_perf.cpp to fill the tops_at_freq column in results.csv (its default, never overridden by `make sweep`), so TOPS figures here are directly comparable to the CSV. This is NOT a claim that either node can close timing at 500MHz in real silicon -- 130nm sg13g2 in particular would typically target well under 200MHz for a design like this.)

| N | M | scenario | cycles | MACs/cycle | util% | TOPS@freq | AI (MACs/B) | pJ/MAC | eff pJ/MAC | TOPS/W |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 4 | single_load | 10 | 6.400 | 40.00 | 0.0064 | 2.000 | 0.1035 | 0.9472 | 2.111 |
| 4 | 4 | per_tile_reload | 11 | 5.818 | 36.36 | 0.0058 | 2.000 | 0.1035 | 0.9472 | 2.111 |
| 4 | 16 | single_load | 22 | 11.636 | 72.73 | 0.0116 | 3.200 | 0.1035 | 0.8418 | 2.376 |
| 4 | 16 | per_tile_reload | 23 | 11.130 | 69.57 | 0.0111 | 3.200 | 0.1035 | 0.8418 | 2.376 |
| 4 | 64 | single_load | 70 | 14.629 | 91.43 | 0.0146 | 3.765 | 0.1035 | 0.8154 | 2.453 |
| 4 | 64 | per_tile_reload | 71 | 14.423 | 90.14 | 0.0144 | 3.765 | 0.1035 | 0.8154 | 2.453 |
| 4 | 256 | single_load | 262 | 15.634 | 97.71 | 0.0156 | 3.938 | 0.1035 | 0.8088 | 2.473 |
| 4 | 256 | per_tile_reload | 263 | 15.574 | 97.34 | 0.0156 | 3.938 | 0.1035 | 0.8088 | 2.473 |
| 4 | 256 | single_load | 262 | 15.634 | 97.71 | 0.0156 | 3.938 | 0.1035 | 0.8088 | 2.473 |
| 4 | 256 | per_tile_reload | 263 | 15.574 | 97.34 | 0.0156 | 3.938 | 0.1035 | 0.8088 | 2.473 |
| 8 | 8 | single_load | 22 | 23.273 | 36.36 | 0.0233 | 4.000 | 0.1035 | 0.5254 | 3.807 |
| 8 | 8 | per_tile_reload | 23 | 22.261 | 34.78 | 0.0223 | 4.000 | 0.1035 | 0.5254 | 3.807 |
| 8 | 32 | single_load | 46 | 44.522 | 69.57 | 0.0445 | 6.400 | 0.1035 | 0.4726 | 4.232 |
| 8 | 32 | per_tile_reload | 47 | 43.574 | 68.09 | 0.0436 | 6.400 | 0.1035 | 0.4726 | 4.232 |
| 8 | 128 | single_load | 142 | 57.690 | 90.14 | 0.0577 | 7.529 | 0.1035 | 0.4595 | 4.353 |
| 8 | 128 | per_tile_reload | 143 | 57.287 | 89.51 | 0.0573 | 7.529 | 0.1035 | 0.4595 | 4.353 |
| 8 | 512 | single_load | 526 | 62.297 | 97.34 | 0.0623 | 7.877 | 0.1035 | 0.4562 | 4.384 |
| 8 | 512 | per_tile_reload | 527 | 62.178 | 97.15 | 0.0622 | 7.877 | 0.1035 | 0.4562 | 4.384 |
| 8 | 256 | single_load | 270 | 60.681 | 94.81 | 0.0607 | 7.758 | 0.1035 | 0.4573 | 4.374 |
| 8 | 256 | per_tile_reload | 271 | 60.458 | 94.46 | 0.0605 | 7.758 | 0.1035 | 0.4573 | 4.374 |
| 16 | 16 | single_load | 46 | 89.043 | 34.78 | 0.0890 | 8.000 | 0.1035 | 0.3144 | 6.361 |
| 16 | 16 | per_tile_reload | 47 | 87.149 | 34.04 | 0.0871 | 8.000 | 0.1035 | 0.3144 | 6.361 |
| 16 | 64 | single_load | 94 | 174.298 | 68.09 | 0.1743 | 12.800 | 0.1035 | 0.2881 | 6.943 |
| 16 | 64 | per_tile_reload | 95 | 172.463 | 67.37 | 0.1725 | 12.800 | 0.1035 | 0.2881 | 6.943 |
| 16 | 256 | single_load | 286 | 229.147 | 89.51 | 0.2291 | 15.059 | 0.1035 | 0.2815 | 7.105 |
| 16 | 256 | per_tile_reload | 287 | 228.348 | 89.20 | 0.2283 | 15.059 | 0.1035 | 0.2815 | 7.105 |
| 16 | 1024 | single_load | 1054 | 248.713 | 97.15 | 0.2487 | 15.754 | 0.1035 | 0.2798 | 7.147 |
| 16 | 1024 | per_tile_reload | 1055 | 248.478 | 97.06 | 0.2485 | 15.754 | 0.1035 | 0.2798 | 7.147 |
| 16 | 256 | single_load | 286 | 229.147 | 89.51 | 0.2291 | 15.059 | 0.1035 | 0.2815 | 7.105 |
| 16 | 256 | per_tile_reload | 287 | 228.348 | 89.20 | 0.2283 | 15.059 | 0.1035 | 0.2815 | 7.105 |

## Roofline ridge points

| N | peak MACs/cycle | read-port bytes/cycle | ridge AI (MACs/byte) |
|---|---|---|---|
| 4 | 16 | 4 | 4.00 |
| 8 | 64 | 8 | 8.00 |
| 16 | 256 | 16 | 16.00 |

See `roofline.svg` for the per-N log-log roofline plots (measured points vs. compute/memory roofs).
