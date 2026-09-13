# PE clock-gating toggle-count proxy

**This is an activity-based toggle-count proxy derived from Verilator VCD traces, NOT signoff power.** It counts raw bit transitions on act_out, psum_out (both models) and the `prod` multiplier-output net (gated model only -- pe.sv has no equivalent net, so the ungated baseline's proxy is act_out+psum_out alone) inside every PE in the grid, over a fixed stimulus. It is a relative comparison between the two RTL variants, not an estimate of watts.

## N=4

act_out+psum_out toggles, the flops both RTL variants actually have (apples-to-apples):

| scenario | ungated toggles | gated toggles | ungated/MAC | gated/MAC | reduction |
|---|---:|---:|---:|---:|---:|
| dense | 17276 | 17276 | 1079.8 | 1079.8 | 0.0% |
| idle50 | 16351 | 14196 | 1021.9 | 887.2 | 13.2% |
| idle90 | 16776 | 13959 | 1048.5 | 872.4 | 16.8% |
| tailpad_m5 | 17404 | 14191 | 1087.8 | 886.9 | 18.5% |

Gated-only `prod` net (multiplier output; pe.sv has no equivalent exposed net) -- shows the operand-isolation effect directly:

| scenario | prod toggles | prod toggles/MAC |
|---|---:|---:|
| dense | 14024 | 876.5 |
| idle50 | 6062 | 378.9 |
| idle90 | 3441 | 215.1 |
| tailpad_m5 | 3472 | 217.0 |

`dense` (N=4) per-signal toggles -- ungated: {'act_out': 3551, 'psum_out': 13725}, gated: {'prod': 14024, 'act_out': 3551, 'psum_out': 13725}

`idle50` (N=4) per-signal toggles -- ungated: {'act_out': 3438, 'psum_out': 12913}, gated: {'prod': 6062, 'act_out': 1645, 'psum_out': 12551}

`idle90` (N=4) per-signal toggles -- ungated: {'act_out': 3371, 'psum_out': 13405}, gated: {'prod': 3441, 'act_out': 851, 'psum_out': 13108}

`tailpad_m5` (N=4) per-signal toggles -- ungated: {'act_out': 3507, 'psum_out': 13897}, gated: {'prod': 3472, 'act_out': 854, 'psum_out': 13337}

## N=8

act_out+psum_out toggles, the flops both RTL variants actually have (apples-to-apples):

| scenario | ungated toggles | gated toggles | ungated/MAC | gated/MAC | reduction |
|---|---:|---:|---:|---:|---:|
| dense | 88510 | 88510 | 1383.0 | 1383.0 | 0.0% |
| idle50 | 86973 | 76797 | 1359.0 | 1200.0 | 11.7% |
| idle90 | 86304 | 63728 | 1348.5 | 995.8 | 26.2% |
| tailpad_m5 | 86012 | 78062 | 1343.9 | 1219.7 | 9.2% |

Gated-only `prod` net (multiplier output; pe.sv has no equivalent exposed net) -- shows the operand-isolation effect directly:

| scenario | prod toggles | prod toggles/MAC |
|---|---:|---:|
| dense | 69395 | 1084.3 |
| idle50 | 34951 | 546.1 |
| idle90 | 8089 | 126.4 |
| tailpad_m5 | 41975 | 655.9 |

`dense` (N=8) per-signal toggles -- ungated: {'psum_out': 70697, 'act_out': 17813}, gated: {'psum_out': 70697, 'act_out': 17813, 'prod': 69395}

`idle50` (N=8) per-signal toggles -- ungated: {'psum_out': 69522, 'act_out': 17451}, gated: {'psum_out': 68059, 'act_out': 8738, 'prod': 34951}

`idle90` (N=8) per-signal toggles -- ungated: {'psum_out': 68645, 'act_out': 17659}, gated: {'psum_out': 61476, 'act_out': 2252, 'prod': 8089}

`tailpad_m5` (N=8) per-signal toggles -- ungated: {'psum_out': 68098, 'act_out': 17914}, gated: {'psum_out': 66961, 'act_out': 11101, 'prod': 41975}

