# Yosys synthesis script (Tcl mode) targeting IHP sg13g2. Env-var driven so one script
# covers pe, systolic_array/top at any N, and scratchpad_dbuf.
#
# Required env vars:
#   SRCS       space-separated list of RTL files to read (order matters: deps before users)
#   TOP        top module name to synthesize
#   LIBERTY    path to sg13g2_stdcell liberty file
#   PERIOD_NS  target clock period in ns, passed to abc for delay-aware mapping
#   OUTV       output gate-level netlist path
#   OUTLOG     stat -liberty report path
# Optional:
#   NVAL       if set, -G N=$NVAL on read_slang (parameterized modules)
#   PARAMS     if set, extra space-separated NAME=VAL pairs passed as -G NAME=VAL each

yosys -import

set srcs    [split $::env(SRCS) " "]
set top     $::env(TOP)
set liberty $::env(LIBERTY)
set period  $::env(PERIOD_NS)
set outv    $::env(OUTV)
set outlog  $::env(OUTLOG)

# read_slang gives full SystemVerilog elaboration (unpacked array ports, etc.) that yosys's
# native Verilog-2005-based -sv frontend chokes on.
yosys "plugin -i slang"
set gparam ""
if {[info exists ::env(NVAL)]} { append gparam " -G N=$::env(NVAL)" }
if {[info exists ::env(PARAMS)]} {
    foreach kv [split $::env(PARAMS) " "] { append gparam " -G $kv" }
}
yosys "read_slang $srcs --top $top $gparam"

yosys "synth -top $top"
yosys "dfflibmap -liberty $liberty"
# abc -D takes delay target in ps
set period_ps [expr {int($period * 1000)}]
yosys "abc -liberty $liberty -D $period_ps"
yosys "clean"
yosys "tee -o $outlog stat -liberty $liberty"
yosys "write_verilog -noattr $outv"
