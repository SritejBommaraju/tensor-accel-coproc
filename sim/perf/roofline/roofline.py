#!/usr/bin/env python3
# Energy-per-MAC model and roofline table/plot built on top of results.csv (measured, from
# `make -C sim/perf sweep`) and tech_params.json (estimated energy/frequency constants).
# numpy only for the math; matplotlib is optional (falls back to a hand-rolled SVG writer).
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_CSV = os.path.join(HERE, "..", "results.csv")
TECH_PARAMS = os.path.join(HERE, "tech_params.json")
OUT_MD = os.path.join(HERE, "roofline.md")
OUT_SVG = os.path.join(HERE, "roofline.svg")

import numpy as np


def load_tech_params(path=TECH_PARAMS):
    with open(path) as f:
        return json.load(f)


def parse_results_csv(path=RESULTS_CSV):
    """Parse results.csv into a list of dicts with numeric fields converted."""
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "N": int(r["N"]),
                "M": int(r["M"]),
                "scenario": r["scenario"],
                "cycles": int(r["cycles"]),
                "ideal_macs": int(r["ideal_macs"]),
                "macs_per_cycle": float(r["macs_per_cycle"]),
                "utilization_pct": float(r["utilization_pct"]),
                "tops_at_freq": float(r["tops_at_freq"]),
            })
    return rows


def memory_bytes(N, M):
    """Bytes moved through the shared read port (weights + activations) and the write
    port (results), per stream_ctrl.sv's memory layout: W is N words of N int8, A is M
    words of N int8, C is M words of N int32."""
    weight_bytes = N * N          # N words, N int8 lanes each
    act_bytes = M * N             # M words, N int8 lanes each
    result_bytes = M * N * 4      # M words, N int32 lanes each
    return weight_bytes, act_bytes, result_bytes


def compute_energy(row, tech):
    """Energy breakdown for one CSV row under one tech-node dict from tech_params.json.
    E_total = ideal_macs*E_mac + (weight+act bytes)*E_sram_rd + result_bytes*E_sram_wr."""
    N, M, ideal_macs = row["N"], row["M"], row["ideal_macs"]
    weight_bytes, act_bytes, result_bytes = memory_bytes(N, M)

    e_mac_pj = tech["energy_mac_int8_pJ"]
    e_rd_pj = tech["energy_sram_byte_read_pJ"]
    e_wr_pj = tech["energy_sram_byte_write_pJ"]

    e_compute = ideal_macs * e_mac_pj
    e_mem_rd = (weight_bytes + act_bytes) * e_rd_pj
    e_mem_wr = result_bytes * e_wr_pj
    e_total = e_compute + e_mem_rd + e_mem_wr

    pj_per_mac = e_mac_pj  # intrinsic compute energy only, independent of M/N
    eff_pj_per_mac = e_total / ideal_macs  # amortizes data movement over the same MACs

    return {
        "weight_bytes": weight_bytes,
        "act_bytes": act_bytes,
        "result_bytes": result_bytes,
        "e_compute_pJ": e_compute,
        "e_mem_rd_pJ": e_mem_rd,
        "e_mem_wr_pJ": e_mem_wr,
        "e_total_pJ": e_total,
        "pj_per_mac": pj_per_mac,
        "eff_pj_per_mac": eff_pj_per_mac,
    }


def tops_per_watt(row, energy, freq_mhz):
    """TOPS/W at freq_mhz: energy-per-op / time-per-op gives average power, and TOPS at
    that same frequency comes from macs_per_cycle (2 flops/MAC convention, matching
    metrics.h's macs_per_cycle_to_tops)."""
    freq_hz = freq_mhz * 1e6
    time_s = row["cycles"] / freq_hz
    power_w = (energy["e_total_pJ"] * 1e-12) / time_s
    tops = row["macs_per_cycle"] * 2.0 * freq_hz / 1e12
    return tops / power_w if power_w > 0 else float("nan")


def arithmetic_intensity(row):
    """MACs per byte read through the shared read port (weights + activations only --
    the write port to results is separate hardware, per stream_ctrl.sv)."""
    weight_bytes, act_bytes, _ = memory_bytes(row["N"], row["M"])
    read_bytes = weight_bytes + act_bytes
    return row["ideal_macs"] / read_bytes


def ridge_point(N):
    """Roofline for one array size N: compute roof = N*N MACs/cycle (peak PE utilization).
    Memory roof = AI * bytes/cycle, where the shared read port delivers N*8 bits = N bytes/
    cycle. The two roofs meet where AI*N = N*N, i.e. at AI = N MACs/byte."""
    peak_macs_per_cycle = N * N
    bytes_per_cycle = N
    ridge_ai = peak_macs_per_cycle / bytes_per_cycle  # = N
    return peak_macs_per_cycle, bytes_per_cycle, ridge_ai


# ---------------------------------------------------------------------------
# SVG plotting (hand-rolled; matplotlib used instead when available)
# ---------------------------------------------------------------------------

def _svg_header(w, h):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="monospace" font-size="11">\n<rect width="{w}" height="{h}" fill="white"/>\n'


def _log_map(v, lo, hi, px0, px1):
    lv, llo, lhi = np.log10(v), np.log10(lo), np.log10(hi)
    return px0 + (lv - llo) / (lhi - llo) * (px1 - px0)


def _panel_svg(N, rows_for_n, x0, y0, w, h):
    """One log-log roofline panel for array size N, drawn inside [x0,y0,x0+w,y0+h]."""
    peak, bpc, ridge_ai = ridge_point(N)
    ais = [arithmetic_intensity(r) for r in rows_for_n]
    ai_lo = min(min(ais), ridge_ai) * 0.5
    ai_hi = max(max(ais), ridge_ai) * 2.0
    y_lo = peak * 0.05
    y_hi = peak * 1.5

    def X(ai):
        return _log_map(ai, ai_lo, ai_hi, x0, x0 + w)

    def Y(mpc):
        return y0 + h - _log_map(mpc, y_lo, y_hi, 0, h)

    svg = [f'<g stroke="black" stroke-width="1" fill="none"><rect x="{x0}" y="{y0}" width="{w}" height="{h}"/></g>\n']
    svg.append(f'<text x="{x0+4}" y="{y0+14}" font-weight="bold">N={N}</text>\n')

    # memory-bound roof: macs/cycle = AI * bytes_per_cycle, from ai_lo up to the ridge
    mem_x0, mem_y0 = X(ai_lo), Y(min(ai_lo * bpc, y_hi))
    mem_x1, mem_y1 = X(ridge_ai), Y(peak)
    svg.append(f'<line x1="{mem_x0:.1f}" y1="{mem_y0:.1f}" x2="{mem_x1:.1f}" y2="{mem_y1:.1f}" stroke="steelblue" stroke-width="2"/>\n')
    # compute-bound roof: horizontal line at peak, from the ridge to ai_hi
    comp_x1, comp_y = X(ai_hi), Y(peak)
    svg.append(f'<line x1="{mem_x1:.1f}" y1="{mem_y1:.1f}" x2="{comp_x1:.1f}" y2="{comp_y:.1f}" stroke="firebrick" stroke-width="2"/>\n')
    # ridge marker
    svg.append(f'<circle cx="{mem_x1:.1f}" cy="{mem_y1:.1f}" r="3" fill="black"/>\n')
    svg.append(f'<text x="{mem_x1+4:.1f}" y="{mem_y1-4:.1f}">ridge AI={ridge_ai:.1f}</text>\n')

    # measured points
    colors = {"single_load": "seagreen", "per_tile_reload": "darkorange"}
    seen = set()
    for r, ai in zip(rows_for_n, ais):
        px, py = X(ai), Y(r["macs_per_cycle"])
        c = colors.get(r["scenario"], "gray")
        svg.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{c}" fill-opacity="0.85"/>\n')
        seen.add(r["scenario"])

    svg.append(f'<text x="{x0+4}" y="{y0+h-4}" font-size="9">AI (MACs/byte, log) &#8594;</text>\n')
    return "".join(svg)


def write_svg_matplotlib(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    Ns = sorted(set(r["N"] for r in rows))
    fig, axes = plt.subplots(1, len(Ns), figsize=(5 * len(Ns), 4.2))
    if len(Ns) == 1:
        axes = [axes]
    colors = {"single_load": "seagreen", "per_tile_reload": "darkorange"}
    for ax, N in zip(axes, Ns):
        rows_n = [r for r in rows if r["N"] == N]
        peak, bpc, ridge_ai = ridge_point(N)
        ais = [arithmetic_intensity(r) for r in rows_n]
        ai_lo, ai_hi = min(min(ais), ridge_ai) * 0.5, max(max(ais), ridge_ai) * 2.0
        x_mem = np.array([ai_lo, ridge_ai])
        ax.loglog(x_mem, x_mem * bpc, color="steelblue", lw=2, label="memory roof")
        x_comp = np.array([ridge_ai, ai_hi])
        ax.loglog(x_comp, [peak, peak], color="firebrick", lw=2, label="compute roof")
        ax.plot(ridge_ai, peak, "ko", ms=5)
        for scen in ("single_load", "per_tile_reload"):
            pts = [(arithmetic_intensity(r), r["macs_per_cycle"]) for r in rows_n if r["scenario"] == scen]
            if pts:
                xs, ys = zip(*pts)
                ax.scatter(xs, ys, color=colors[scen], label=scen, zorder=5)
        ax.set_title(f"N={N}")
        ax.set_xlabel("Arithmetic intensity (MACs/byte)")
        ax.set_ylabel("MACs/cycle")
        ax.legend(fontsize=8)
        ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path)


def write_svg_manual(rows, path):
    Ns = sorted(set(r["N"] for r in rows))
    panel_w, panel_h, margin = 340, 260, 20
    total_w = len(Ns) * (panel_w + margin) + margin
    total_h = panel_h + 2 * margin
    parts = [_svg_header(total_w, total_h)]
    for i, N in enumerate(Ns):
        x0 = margin + i * (panel_w + margin)
        rows_n = [r for r in rows if r["N"] == N]
        parts.append(_panel_svg(N, rows_n, x0, margin, panel_w, panel_h))
    legend_y = total_h - 6
    parts.append(f'<circle cx="{margin+6}" cy="{legend_y-4}" r="3.5" fill="seagreen"/><text x="{margin+14}" y="{legend_y}">single_load</text>')
    parts.append(f'<circle cx="{margin+120}" cy="{legend_y-4}" r="3.5" fill="darkorange"/><text x="{margin+128}" y="{legend_y}">per_tile_reload</text>')
    parts.append("</svg>\n")
    with open(path, "w") as f:
        f.write("".join(parts))


def write_svg(rows, path):
    try:
        write_svg_matplotlib(rows, path)
    except ImportError:
        write_svg_manual(rows, path)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def write_markdown(rows, tech_params, path):
    lines = []
    lines.append("# Energy / Roofline model\n")
    lines.append(
        "Cycles, MACs/cycle, utilization%, and TOPS-at-freq below come straight from "
        "`sim/perf/results.csv` (measured via Verilator). **All pJ/MAC, effective pJ/MAC, "
        "and TOPS/W figures are MODEL ESTIMATES**, computed from the per-node energy "
        "constants in `tech_params.json` (which are themselves literature estimates, not "
        "silicon measurements or PDK characterization) applied to the byte counts implied "
        "by `stream_ctrl.sv`'s memory layout. They are not measured quantities.\n"
    )

    for node_name, tech in tech_params["nodes"].items():
        lines.append(f"\n## {node_name} ({tech['description']})\n")
        lines.append(
            f"Estimate basis: {tech['source']}\n\n"
            f"- energy/INT8 MAC: {tech['energy_mac_int8_pJ']:.4f} pJ\n"
            f"- energy/8b register bit-flip: {tech['energy_reg_bitflip_pJ']:.4f} pJ\n"
            f"- energy/SRAM byte read: {tech['energy_sram_byte_read_pJ']:.4f} pJ\n"
            f"- energy/SRAM byte write: {tech['energy_sram_byte_write_pJ']:.4f} pJ\n"
            f"- target clock: {tech_params['target_freq_mhz']} MHz "
            f"({tech_params['target_freq_note']})\n"
        )
        lines.append(
            "\n| N | M | scenario | cycles | MACs/cycle | util% | TOPS@freq | AI (MACs/B) "
            "| pJ/MAC | eff pJ/MAC | TOPS/W |\n"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            e = compute_energy(r, tech)
            ai = arithmetic_intensity(r)
            tpw = tops_per_watt(r, e, tech_params["target_freq_mhz"])
            lines.append(
                f"| {r['N']} | {r['M']} | {r['scenario']} | {r['cycles']} | "
                f"{r['macs_per_cycle']:.3f} | {r['utilization_pct']:.2f} | "
                f"{r['tops_at_freq']:.4f} | {ai:.3f} | {e['pj_per_mac']:.4f} | "
                f"{e['eff_pj_per_mac']:.4f} | {tpw:.3f} |\n"
            )

    lines.append("\n## Roofline ridge points\n\n| N | peak MACs/cycle | read-port bytes/cycle | ridge AI (MACs/byte) |\n|---|---|---|---|\n")
    for N in sorted(set(r["N"] for r in rows)):
        peak, bpc, ridge_ai = ridge_point(N)
        lines.append(f"| {N} | {peak} | {bpc} | {ridge_ai:.2f} |\n")

    lines.append("\nSee `roofline.svg` for the per-N log-log roofline plots (measured points vs. compute/memory roofs).\n")

    with open(path, "w") as f:
        f.writelines(lines)


def main():
    if not os.path.exists(RESULTS_CSV):
        print(f"missing {RESULTS_CSV}; run `make -C .. sweep` first", file=sys.stderr)
        return 1
    rows = parse_results_csv()
    tech_params = load_tech_params()
    write_markdown(rows, tech_params, OUT_MD)
    write_svg(rows, OUT_SVG)
    print(f"wrote {OUT_MD} and {OUT_SVG} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
