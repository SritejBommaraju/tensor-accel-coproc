#!/usr/bin/env python3
"""Parses sim/power VCDs and reports a bit-toggle-count switching-activity proxy for the PE grid.

Stdlib only. Counts toggles on act_out and psum_out inside every u_pe instance (both models),
plus the `prod` net (gated model only -- pe.sv has no equivalent wire, so the ungated side's
proxy is act_out+psum_out alone, as instructed). Writes/append a scenario's rows into results.md.
"""
import sys
import re
import os

TARGET_UNGATED = {"act_out", "psum_out"}
TARGET_GATED = {"act_out", "psum_out", "prod"}

VAR_RE = re.compile(r"^\$var\s+\w+\s+(\d+)\s+(\S+)\s+(\S+)")


def parse_vcd(path, targets):
    """Returns (toggle_total, num_pe, per_signal_toggles) counting only vars under a u_pe scope."""
    scope = []
    id_info = {}     # id -> (width, path_tuple, name)
    tracked = {}      # id -> (width, prev_bits or None)
    total_toggles = 0
    pe_paths = set()
    per_signal = {name: 0 for name in targets}

    with open(path, "r", errors="replace") as f:
        in_defs = True
        for line in f:
            line = line.strip()
            if not line:
                continue
            if in_defs:
                if line.startswith("$scope"):
                    parts = line.split()
                    scope.append(parts[2])
                    continue
                if line.startswith("$upscope"):
                    scope.pop()
                    continue
                if line.startswith("$var"):
                    m = VAR_RE.match(line)
                    if m:
                        width, vid, name = int(m.group(1)), m.group(2), m.group(3)
                        path = tuple(scope)
                        if path and path[-1] == "u_pe" and name in targets:
                            id_info[vid] = (width, path, name)
                            tracked[vid] = (width, None)
                            pe_paths.add(path)
                    continue
                if line.startswith("$enddefinitions"):
                    in_defs = False
                    continue
                continue
            # value-change section
            if line[0] == "#":
                continue
            if line[0] in "01xXzZ":
                vid = line[1:]
                if vid in tracked:
                    width, prev = tracked[vid]
                    bit = 1 if line[0] == "1" else 0
                    if prev is not None:
                        diff = bit ^ (prev & 1)
                        total_toggles += diff
                        per_signal[id_info[vid][2]] += diff
                    tracked[vid] = (width, bit)
                continue
            if line[0] in "bB":
                sp = line.find(" ")
                if sp == -1:
                    continue
                bits_str, vid = line[1:sp], line[sp + 1:]
                if vid in tracked:
                    width, prev = tracked[vid]
                    bits_str = bits_str.replace("x", "0").replace("X", "0").replace("z", "0").replace("Z", "0")
                    val = int(bits_str, 2) if bits_str else 0
                    if prev is not None:
                        diff = bin(val ^ prev).count("1")
                        total_toggles += diff
                        per_signal[id_info[vid][2]] += diff
                    tracked[vid] = (width, val)
                continue
            # 'r'/'R' real values not used by this design; ignore

    return total_toggles, len(pe_paths), per_signal


def main():
    if len(sys.argv) < 2:
        print("usage: toggle_count.py <N>", file=sys.stderr)
        sys.exit(1)
    n = int(sys.argv[1])
    vcd_dir = os.path.join(os.path.dirname(__file__), "vcd")
    scenarios = []
    for fn in sorted(os.listdir(vcd_dir)):
        m = re.match(rf"^top_N{n}_(.+)\.vcd$", fn)
        if m:
            scenarios.append(m.group(1))

    rows = []
    for sc in scenarios:
        base_path = os.path.join(vcd_dir, f"top_N{n}_{sc}.vcd")
        cg_path = os.path.join(vcd_dir, f"topcg_N{n}_{sc}.vcd")
        bt, bn, bsig = parse_vcd(base_path, TARGET_UNGATED)
        gall, gn, gsig = parse_vcd(cg_path, TARGET_GATED)
        assert bn == n * n and gn == n * n, f"expected {n*n} PEs, got base={bn} gated={gn}"
        # main (apples-to-apples) comparison uses the flops both designs actually have;
        # `prod` is gated-only (pe.sv has no such net) and reported separately below.
        gt = gsig["act_out"] + gsig["psum_out"]
        reduction_pct = 100.0 * (bt - gt) / bt if bt else 0.0
        rows.append({
            "scenario": sc, "n": n,
            "base_total": bt, "gated_total": gt, "gated_prod": gsig["prod"],
            "base_per_mac": bt / bn, "gated_per_mac": gt / gn,
            "reduction_pct": reduction_pct,
            "bsig": bsig, "gsig": gsig,
        })

    results_path = os.path.join(os.path.dirname(__file__), "results.md")
    header_needed = not os.path.exists(results_path) or os.path.getsize(results_path) == 0
    with open(results_path, "a") as f:
        if header_needed:
            f.write("# PE clock-gating toggle-count proxy\n\n")
            f.write(
                "**This is an activity-based toggle-count proxy derived from Verilator VCD "
                "traces, NOT signoff power.** It counts raw bit transitions on act_out, "
                "psum_out (both models) and the `prod` multiplier-output net (gated model only "
                "-- pe.sv has no equivalent net, so the ungated baseline's proxy is act_out+"
                "psum_out alone) inside every PE in the grid, over a fixed stimulus. It is a "
                "relative comparison between the two RTL variants, not an estimate of watts.\n\n"
            )
        f.write(f"## N={n}\n\n")
        f.write("act_out+psum_out toggles, the flops both RTL variants actually have (apples-to-apples):\n\n")
        f.write("| scenario | ungated toggles | gated toggles | ungated/MAC | gated/MAC | reduction |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for r in rows:
            f.write(
                f"| {r['scenario']} | {r['base_total']} | {r['gated_total']} | "
                f"{r['base_per_mac']:.1f} | {r['gated_per_mac']:.1f} | {r['reduction_pct']:.1f}% |\n"
            )
        f.write("\nGated-only `prod` net (multiplier output; pe.sv has no equivalent exposed net) -- "
                 "shows the operand-isolation effect directly:\n\n")
        f.write("| scenario | prod toggles | prod toggles/MAC |\n")
        f.write("|---|---:|---:|\n")
        for r in rows:
            f.write(f"| {r['scenario']} | {r['gated_prod']} | {r['gated_prod'] / (n * n):.1f} |\n")
        f.write("\n")
        for r in rows:
            f.write(f"`{r['scenario']}` (N={n}) per-signal toggles -- ungated: {r['bsig']}, gated: {r['gsig']}\n\n")

    for r in rows:
        print(f"N={n} {r['scenario']:12s} ungated={r['base_total']:7d} gated={r['gated_total']:7d} "
              f"reduction={r['reduction_pct']:5.1f}%")


if __name__ == "__main__":
    main()
