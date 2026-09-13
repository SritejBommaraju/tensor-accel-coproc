#!/usr/bin/env bash
# Sweeps clock period for a given synthesized netlist until WNS >= 0, reporting max frequency.
# Usage: run_sweep.sh <top> <netlist_sta.v> <start_ns> <step_ns> <max_tries> <tag>
# <tag> disambiguates log filenames when the same module name is swept at different
# parameterizations (e.g. top at N=4 vs N=8) - pass e.g. "top_N4".
set -euo pipefail
cd "$(dirname "$0")"

TOP=$1
NETLIST=$2
PERIOD=${3:-2.0}
STEP=${4:-0.2}
MAX_TRIES=${5:-40}
TAG=${6:-$TOP}

LIBERTY="${LIBERTY:-$HOME/pdk/IHP-Open-PDK/ihp-sg13g2/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib}"
STA="${STA:-$HOME/opensta/bin/sta}"

for i in $(seq 1 "$MAX_TRIES"); do
    LOG="out/${TAG}_sweep_${PERIOD}ns.log"
    LIBERTY="$LIBERTY" NETLIST="$NETLIST" TOP="$TOP" PERIOD_NS="$PERIOD" "$STA" sta/sta.tcl > "$LOG" 2>&1
    WNS=$(grep -m1 '^wns max' "$LOG" | awk '{print $3}')
    echo "period=${PERIOD}ns  wns=${WNS}"
    if awk -v w="$WNS" 'BEGIN{exit !(w >= 0)}'; then
        FREQ=$(awk -v p="$PERIOD" 'BEGIN{printf "%.2f", 1000.0/p}')
        echo "CONVERGED: period=${PERIOD}ns -> fmax=${FREQ}MHz (log: $LOG)"
        exit 0
    fi
    PERIOD=$(awk -v p="$PERIOD" -v s="$STEP" 'BEGIN{printf "%.3f", p+s}')
done
echo "did not converge within $MAX_TRIES tries (last period=${PERIOD}ns)"
exit 1
