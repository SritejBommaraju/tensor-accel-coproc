# pd/ tool install log (IHP sg13g2 open-source synth+STA flow)

All commands below were run in WSL Ubuntu (`wsl -d Ubuntu`). Windows PowerShell/Git-Bash was
only used to invoke `wsl`. Nothing outside `~` (the WSL home) or `pd/` was touched.

## 1. Synthesis: yosys, via OSS CAD Suite nightly

The OSS CAD Suite nightly tarball worked on the first try (no apt fallback needed):

```bash
curl -sSL 'https://api.github.com/repos/YosysHQ/oss-cad-suite-build/releases/latest' \
  | grep -o 'browser_download_url.*linux-x64[^"]*'
# -> oss-cad-suite-linux-x64-20260913.tgz  (tag 2026-09-13)
cd /tmp
curl -sSL -o oss-cad-suite.tgz \
  'https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-09-13/oss-cad-suite-linux-x64-20260913.tgz'
cd ~ && tar xzf /tmp/oss-cad-suite.tgz     # -> ~/oss-cad-suite (742 MB download, ~9s to extract)
```

Verified version:
```
$ ~/oss-cad-suite/bin/yosys -V
Yosys 0.69+24 (git sha1 d0e71cfb7-dirty, Release, Clang /usr/bin/clang++ 21.1.8)
```

Use it via `PATH="$HOME/oss-cad-suite/bin:$PATH"`.

**Important caveat found during use**: yosys's native `read_verilog -sv` (Verilog-2005-based
frontend) cannot parse this repo's unpacked-array module ports (e.g.
`input logic signed [7:0] weight_in [0:N-1][0:N-1]` in `systolic_array.sv`) --
`ERROR: syntax error, unexpected '['`. The OSS CAD Suite bundles a `slang`-based frontend
(`plugin -i slang; read_slang ...`) that elaborates full SystemVerilog correctly, including
parameter overrides via `-G N=<value>`. `pd/synth/synth.tcl` uses `read_slang`, not
`read_verilog -sv`.

## 2. Static timing analysis: OpenSTA, built from source

OSS CAD Suite's nightly build does **not** ship `sta`/`openroad` binaries (only yosys and
FPGA-oriented tools -- `ls ~/oss-cad-suite/bin` has no `sta` or `openroad`). OpenSTA was built
from source instead.

Build deps (all via apt, passwordless sudo available in this session):
```bash
sudo apt-get install -y tcl-dev tcl8.6-dev swig bison flex libeigen3-dev libreadline-dev \
  zlib1g-dev automake autoconf libtool
```

OpenSTA (as of the `parallaxsw/OpenSTA` HEAD used here, STA version 3.1.0) requires the CUDD
BDD package, which CMake fails on if not given explicitly (`CMake Error: ... CUDD_LIB ... set
to NOTFOUND`). CUDD isn't packaged in apt for this Ubuntu release, so it was also built from
source:

```bash
git clone --depth 1 https://github.com/The-OpenROAD-Project/cudd.git ~/cudd-src
cd ~/cudd-src
autoreconf -fi   # the tarball's shipped configure/aclocal.m4 predate the installed
                 # automake/autoconf and fail with "aclocal-1.14: command not found"
./configure --prefix=$HOME/cudd --enable-shared=no --enable-static=yes \
  CFLAGS="-fPIC -O3" CXXFLAGS="-fPIC -O3"
make -j16 && make install       # -> ~/cudd/lib/libcudd.a, ~/cudd/include/cudd.h
```

Then OpenSTA itself:
```bash
git clone --depth 1 https://github.com/parallaxsw/OpenSTA.git ~/opensta-src
cd ~/opensta-src && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=RELEASE -DCUDD_DIR=$HOME/cudd
make -j16                        # -> ~/opensta-src/build/sta (8.0 MB)
mkdir -p ~/opensta/bin && cp ~/opensta-src/build/sta ~/opensta/bin/sta
```

Verified version:
```
$ ~/opensta/bin/sta -version
3.1.0
```

## 3. IHP-Open-PDK

```bash
git clone --depth 1 https://github.com/IHP-GmbH/IHP-Open-PDK.git ~/pdk/IHP-Open-PDK
```
(1.2 GB checkout.) Paths used by this flow:

| artifact | path |
|---|---|
| liberty (typ, 1.20V, 25C) | `~/pdk/IHP-Open-PDK/ihp-sg13g2/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib` |
| standard-cell LEF | `~/pdk/IHP-Open-PDK/ihp-sg13g2/libs.ref/sg13g2_stdcell/lef/sg13g2_stdcell.lef` |
| tech LEF | `~/pdk/IHP-Open-PDK/ihp-sg13g2/libs.ref/sg13g2_stdcell/lef/sg13g2_tech.lef` |
| cell Verilog models | `~/pdk/IHP-Open-PDK/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v` |
| cell UDP primitives (DFF/latch/mux) | `~/pdk/IHP-Open-PDK/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_udp.v` |

The liberty file has real NLDM timing tables (33.8k lines, e.g. `sg13g2_and2_1` area 9.072 um^2,
leakage 137.61 pW; `time_unit : "1ns"`), not a stub.

## 4. Gate-level Verilog model gap (Verilator can't run sg13g2_udp.v)

`sg13g2_udp.v` implements the library's `ihp_dff*`/`ihp_latch*`/`ihp_mux*` cells as
Verilog-1995 `primitive`/`table` UDPs. Verilator 5.032 does not support UDP tables:
```
%Error-UNSUPPORTED: sg13g2_udp.v:407:2: Unsupported: Verilog 1995 UDP Tables.
Use --bbox-unsup to ignore tables.
```
`--bbox-unsup` would blackbox every flop/latch/mux in the design (no functional behavior) --
useless for a regression that has to actually pass/fail. `pd/gls/sg13g2_functional.v` is a
hand-written behavioral replacement (plain `always`-block modules, same names/port order,
functional-only, no timing) that reads off the truth tables in `sg13g2_udp.v`; see its header
comment and `pd/gls/Makefile` for the two additional fixups this required (unnamed UDP
instantiations need instance names once they're plain modules, and each sequential cell's
`delayed_*`-named ports are never actually driven except by a real timing-checking simulator's
`$setuphold`/`$recrem` optional output args, so `pd/gls/Makefile` auto-generates
`assign delayed_X = X;` pass-throughs). This is functional-verification-only; real timing comes
from the liberty file via OpenSTA in `pd/sta`, not from GLS.

## 5. LibreLane / full place-and-route to GDS: attempted, blocked on OpenROAD CLI

```bash
python3 -m venv /tmp/lltest && source /tmp/lltest/bin/activate
pip install librelane          # succeeded: LibreLane v3.0.14
sudo apt-get install -y python3-tk   # needed: LibreLane's Tcl-env eval imports tkinter
                                       # (ModuleNotFoundError: No module named 'tkinter')
pip install ciel                      # (LibreLane dependency, PDK manager)
ciel enable --pdk-family ihp-sg13g2 <hash>   # -> ~/.ciel/ihp-sg13g2, ~26s, works fine,
                                               # includes libs.tech/librelane/config.tcl
                                               # (official LibreLane variable mapping for sg13g2)
```
Running `librelane --pdk-root ~/.ciel --pdk ihp-sg13g2 pd/librelane/config.json` with OSS CAD
Suite's `yosys` on PATH fails at the first synthesis step:
```
Error parsing options: Option 'y' does not exist
```
LibreLane's Python-driven synthesis steps invoke `yosys -y <script>.py` (pyosys mode), which
requires yosys built with `ENABLE_PYOSYS`; the OSS CAD Suite build isn't. Installing
`pip install yowasp-yosys` (a WASM yosys build with pyosys support) fixes that step -- lint and
JSON-header generation then run.

The flow then reaches the OpenROAD floorplan step, which needs an `openroad` executable on
PATH. There is no `yowasp-openroad` on PyPI (`pip install yowasp-openroad` ->
`ERROR: Could not find a version that satisfies the requirement`). There IS a PyPI package
named `openroad` (v0.0.1), but it is a SWIG binding only:
```
$ cat site-packages/openroad/__init__.py
from openroadpy import *
```
`_openroadpy.so` (113 MB) is a real compiled OpenROAD core, but the package ships no CLI
entry point / console script -- LibreLane's OpenROAD steps `subprocess`-invoke a Tcl-driven
`openroad <script.tcl>` binary (see `librelane/steps/openroad.py`, `get_command()` returns
`"openroad"`), which this package does not provide. OpenROAD does not publish prebuilt CLI
binaries or GitHub Releases (only a Docker image), and this session has neither `docker` nor
`nix` installed, so `librelane --dockerized` and OpenROAD's own from-source build (which
assumes one of those two toolchains, on top of Qt/Boost/LEMON/or-tools/spdlog dependencies well
beyond what was needed for OpenSTA+CUDD above) were not attempted.

**Unblocking requirement for full PnR-to-GDS**: either (a) Docker or Nix in this WSL
environment (neither present, and installing Docker Desktop / a Nix daemon is outside what a
non-interactive session can do unattended), or (b) building OpenROAD's CLI from source, which
additionally needs Qt5/6, Boost, LEMON, spdlog, or-tools, and (typically) several more hours of
build time beyond the CUDD/OpenSTA build already done here. `pd/librelane/config.json` is
provided and is believed correct (it matches the PDK's own shipped
`libs.tech/librelane/config.tcl` variable names); it has not been run to completion, so its
area/utilization numbers are not in `pd/RESULTS.md`.

### Retry (2026-09-13): (a) prebuilt .deb, (b) pip/openroadpy shim, (c) librelane upgrade

Re-attempted unblocking, in the order specified, ~20 min cap:

**(a) Precision-Innovations prebuilt `.deb`.** GitHub Releases for
`Precision-Innovations/OpenROAD` have been retired:
```
$ curl -sSL https://api.github.com/repos/Precision-Innovations/OpenROAD/releases/latest
{"tag_name": "26Q1", "name": "Releases have been moved", "assets": [],
 "body": "All further releases will be available at: https://vaultlink.precisioninno.com/"}
```
`vaultlink.precisioninno.com` returns HTTP 200 but is a separate distribution portal (not a
plain GitHub-releases `.deb` mirror covered by the task's assumption); not pursued further as
"the Precision-Innovations GitHub releases .deb" this task named no longer exist.

**(b) `pip install -U openroad` + shim.** Still v0.0.1 (`pip index versions openroad` ->
`Available versions: 0.0.1`), still the bare `openroadpy` SWIG core with no console script
(same as before). Its `openroad.Design`/`openroad.Tech` Python API does work standalone,
though:
```python
import openroad
tech = openroad.Tech(); design = openroad.Design(tech)
design.evalTclString("puts hi")   # -> prints "hi", no crash
```
Wrote the ~50-line shim at `pd/librelane/bin/openroad` (Python): parses LibreLane's
`-exit -no_init [-threads N] <script.tcl>` argv, constructs `openroad.Tech()`/`openroad.Design()`,
sets `argv`/`argc` Tcl globals, `evalTclString()`s the script file's contents, and on `-exit`
calls `os._exit(0)` rather than `sys.exit(0)`.  Two real bugs found and fixed while making this
work standalone (both reproduced in isolation with minimal repro scripts):
1. `openroad.set_thread_count(N)` **segfaults** if called before `Tech()`/`Design()` are
   constructed (harmless once called after) -- openroadpy 0.0.1's global thread pool isn't
   initialized until a `Design` exists.
2. Normal CPython interpreter teardown after `sys.exit()` **segfaults** while destructing the
   SWIG-wrapped `Tech`/`Design` C++ objects (destructor ordering issue in the 0.0.1 binding);
   `os._exit(0)` (skip teardown, like real `openroad`'s own process-exit path) avoids it.
With both fixes the shim correctly runs a Tcl script and exits 0 (verified directly, both via
`python3 pd/librelane/bin/openroad -exit -no_init -threads 4 script.tcl` and via `openroad` on
`PATH`). **However**, `openroad.Tech()`/`Design()` only expose the subset of the real OpenROAD
Tcl command set that openroadpy's SWIG wrapper registers -- it does not `source` OpenROAD's own
`.tcl` command library (`read_lef`, `initialize_floorplan`, etc. as LibreLane's floorplan/place/
route step scripts call them are not necessarily present as bare Tcl procs the way the real
`openroad` binary provides), so LibreLane's actual floorplan-step script was not run to
completion against this shim within the time cap -- the shim is a real, working `openroad`-argv-
compatible Tcl driver as far as Tcl execution and Design/Tech construction go, but is unverified
end-to-end against LibreLane's OpenROAD step scripts specifically (a genuinely different, harder
integration question than "is there a CLI binary at all").

**(c) `pip install -U librelane`.** Already at the latest release (3.0.14, first installed at
the start of this task); no newer version bundles/locates OpenROAD differently.

**Net effect of this retry**: went from "no `openroad` executable exists at all, hard stop" to
"an `openroad`-argv-compatible executable exists and correctly runs arbitrary Tcl", which is a
real, working piece of infrastructure (kept at `pd/librelane/bin/openroad`) -- but the deeper gap
(openroadpy 0.0.1 not exposing OpenROAD's full builtin Tcl command surface the way the real
compiled-from-source `openroad` binary does) was not fully closed within the cap, so a completed
LibreLane PnR-to-GDS run for `top` N=4/N=8 is still not demonstrated. Given that, the fallback
interface-block synth+STA targets below (`pd/Makefile`: `synth-axi-bridge`, `sta-axi-bridge`,
`sweep-axi-bridge`, `synth-cmdq`, `sta-cmdq`, `sweep-cmdq`) were run instead; see
`pd/RESULTS.md`'s "Interface blocks" table.

## Reproducing

```
wsl -d Ubuntu -- bash -lc "cd /mnt/c/Users/bomma/projects/tensor-accel-coproc/pd && make all"
```
assumes `~/oss-cad-suite`, `~/opensta/bin/sta`, and `~/pdk/IHP-Open-PDK` exist as built above
(override with `OSS_CAD_SUITE=`, `OPENSTA=`, `PDK_ROOT=` make variables if installed elsewhere).
