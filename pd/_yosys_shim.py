#!/usr/bin/env python3
# Minimal stand-in for `yosys -y <script.py> [-Q] [-q|-qq] -- <args...>` (ENABLE_PYOSYS mode),
# for use where no ENABLE_PYOSYS yosys binary is available but the `pyosys` PyPI package is.
# LibreLane's pyosys steps only ever call: yosys -y <script> [-Q] [-q|-qq] -- --config-in ... etc.
import sys
import runpy

argv = sys.argv[1:]
if not argv or argv[0] != "-y":
    print("yosys-shim: expected '-y <script.py> ...'", file=sys.stderr)
    sys.exit(1)

script = argv[1]
rest = argv[2:]
# drop yosys-level flags (-Q, -q, -qq) that precede the '--' separator; keep everything from '--' on
if "--" in rest:
    idx = rest.index("--")
    passthrough = rest[idx + 1 :]  # real yosys -y strips the '--' before invoking the script
else:
    passthrough = []

sys.argv = [script] + passthrough
runpy.run_path(script, run_name="__main__")
