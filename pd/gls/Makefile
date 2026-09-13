# Gate-level regression: runs the existing sim/tb_main.cpp testbench (unmodified) against
# the yosys-synthesized top_N4 netlist plus the IHP sg13g2 cell Verilog models.

PDK_ROOT ?= $(HOME)/pdk/IHP-Open-PDK
# sg13g2_udp.v ships its DFF/latch/mux cells as Verilog-1995 `primitive`/`table` UDPs, unsupported
# by our simulator (UNSUPPORTED: "Verilog 1995 UDP Tables"); sg13g2_functional.v is a hand-written
# behavioral replacement with identical module/port names (see its header comment). Two fixups are
# needed on top of that to make sg13g2_stdcell.v simulate under Verilator (patched_stdcell.v, via
# awk): (1) unnamed instantiations are legal for UDP primitives but not for plain modules, so give
# each one a unique instance name; (2) every sequential cell wires its D/CLK/RESET_B/etc. ports to
# "delayed_*" wires that only a $setuphold/$recrem/$width system-task's optional delayed-output
# arguments would normally drive (SDF pulse-filtered clock/data, for timing-accurate simulators) --
# Verilator never drives them, so the functional flops would see a permanently unknown clock and
# never toggle; add `assign delayed_X = X;` for each so they simply pass through combinationally.
VERILOG_DIR := $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog
CELL_V   := patched_stdcell.v sg13g2_functional.v

patched_stdcell.v: $(VERILOG_DIR)/sg13g2_stdcell.v
	awk '{ \
	  if ($$0 ~ /^[ \t]*ihp_(dff|latch|mux)[a-z0-9_]*[ \t]*\(/) { sub(/\(/, " u_prim_" NR " ("); } \
	  print; \
	  if ($$0 ~ /^\twire delayed_/) { \
	    line = $$0; sub(/^\twire /, "", line); sub(/;$$/, "", line); \
	    n = split(line, names, ", "); \
	    for (i = 1; i <= n; i++) { plain = names[i]; sub(/^delayed_/, "", plain); \
	      print "\tassign " names[i] " = " plain ";"; } \
	  } \
	}' $< > $@

TOP     = top
N       = 4
NETLIST = ../out/top_N$(N)_netlist.v
TB      = ../../sim/tb_main.cpp
VEC_DIR = ../../sim/vectors/N$(N)_M8_S1
OBJ_DIR = obj_dir_N$(N)

.PHONY: run lint clean

run: $(OBJ_DIR)/V$(TOP)
	./$(OBJ_DIR)/V$(TOP) $(VEC_DIR)

$(OBJ_DIR)/V$(TOP): $(NETLIST) $(CELL_V) $(TB)
	verilator --cc --exe --build -Wno-fatal --top-module $(TOP) \
		-CFLAGS "-DTB_N=$(N) -std=c++17" \
		--Mdir $(OBJ_DIR) $(NETLIST) $(CELL_V) $(TB)

lint:
	verilator --lint-only -Wno-fatal --top-module $(TOP) $(NETLIST) $(CELL_V)

clean:
	rm -rf obj_dir_N* patched_stdcell.v
