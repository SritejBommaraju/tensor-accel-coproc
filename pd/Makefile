# Open-source synth+STA flow for pe/systolic_array/scratchpad on IHP sg13g2.
# All tools run under WSL; see INSTALL.md for how these were built/installed.
# Invoke as: wsl -d Ubuntu -- bash -lc "cd /mnt/c/.../pd && make all"

SHELL := /bin/bash

OSS_CAD_SUITE ?= $(HOME)/oss-cad-suite
OPENSTA       ?= $(HOME)/opensta/bin/sta
PDK_ROOT      ?= $(HOME)/pdk/IHP-Open-PDK
LIBERTY       := $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib
CELL_V        := $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v
YOSYS         := PATH="$(OSS_CAD_SUITE)/bin:$$PATH" yosys

RTL := ../rtl
OUT := out

# target periods (ns) used for the abc -D delay target during synthesis; STA sweep finds the
# real fmax independently, this just biases ABC's mapping toward faster cells.
SEED_PERIOD_NS := 3.0

.PHONY: all synth-pe synth-top4 synth-top8 synth-top16 synth-scratchpad \
        sta-pe sta-top4 sta-top8 sweep-pe sweep-top4 sweep-top8 gls results clean \
        synth-axi-bridge sta-axi-bridge sweep-axi-bridge synth-cmdq sta-cmdq sweep-cmdq

all: synth-pe synth-top4 synth-top8 synth-top16 synth-scratchpad \
     sta-pe sta-top4 sta-top8 sweep-pe sweep-top4 sweep-top8 gls \
     synth-axi-bridge sta-axi-bridge sweep-axi-bridge synth-cmdq sta-cmdq sweep-cmdq

$(OUT):
	mkdir -p $(OUT)

# ---- synthesis ----

synth-pe: $(OUT)
	SRCS="$(RTL)/pe.sv" TOP=pe LIBERTY="$(LIBERTY)" PERIOD_NS=$(SEED_PERIOD_NS) \
	  OUTV=$(OUT)/pe_netlist.v OUTLOG=$(OUT)/pe_stat.log \
	  $(YOSYS) -c synth/synth.tcl > $(OUT)/pe_synth.log 2>&1
	sed 's/ signed//g' $(OUT)/pe_netlist.v > $(OUT)/pe_netlist.sta.v

synth-top4: $(OUT)
	SRCS="$(RTL)/pe.sv $(RTL)/systolic_array.sv $(RTL)/top.sv" TOP=top NVAL=4 \
	  LIBERTY="$(LIBERTY)" PERIOD_NS=$(SEED_PERIOD_NS) \
	  OUTV=$(OUT)/top_N4_netlist.v OUTLOG=$(OUT)/top_N4_stat.log \
	  $(YOSYS) -c synth/synth.tcl > $(OUT)/top_N4_synth.log 2>&1
	sed 's/ signed//g' $(OUT)/top_N4_netlist.v > $(OUT)/top_N4_netlist.sta.v

synth-top8: $(OUT)
	SRCS="$(RTL)/pe.sv $(RTL)/systolic_array.sv $(RTL)/top.sv" TOP=top NVAL=8 \
	  LIBERTY="$(LIBERTY)" PERIOD_NS=$(SEED_PERIOD_NS) \
	  OUTV=$(OUT)/top_N8_netlist.v OUTLOG=$(OUT)/top_N8_stat.log \
	  $(YOSYS) -c synth/synth.tcl > $(OUT)/top_N8_synth.log 2>&1
	sed 's/ signed//g' $(OUT)/top_N8_netlist.v > $(OUT)/top_N8_netlist.sta.v

synth-top16: $(OUT)
	SRCS="$(RTL)/pe.sv $(RTL)/systolic_array.sv $(RTL)/top.sv" TOP=top NVAL=16 \
	  LIBERTY="$(LIBERTY)" PERIOD_NS=$(SEED_PERIOD_NS) \
	  OUTV=$(OUT)/top_N16_netlist.v OUTLOG=$(OUT)/top_N16_stat.log \
	  $(YOSYS) -c synth/synth.tcl > $(OUT)/top_N16_synth.log 2>&1
	sed 's/ signed//g' $(OUT)/top_N16_netlist.v > $(OUT)/top_N16_netlist.sta.v

synth-scratchpad: $(OUT)
	SRCS="$(RTL)/scratchpad_dbuf.sv" TOP=scratchpad_dbuf \
	  LIBERTY="$(LIBERTY)" PERIOD_NS=$(SEED_PERIOD_NS) \
	  OUTV=$(OUT)/scratchpad_dbuf_netlist.v OUTLOG=$(OUT)/scratchpad_dbuf_stat.log \
	  $(YOSYS) -c synth/synth.tcl > $(OUT)/scratchpad_dbuf_synth.log 2>&1

# ---- single-point STA at the seed period ----

sta-pe: synth-pe
	LIBERTY="$(LIBERTY)" NETLIST=$(OUT)/pe_netlist.sta.v TOP=pe PERIOD_NS=$(SEED_PERIOD_NS) \
	  $(OPENSTA) sta/sta.tcl > $(OUT)/pe_sta.log 2>&1

sta-top4: synth-top4
	LIBERTY="$(LIBERTY)" NETLIST=$(OUT)/top_N4_netlist.sta.v TOP=top PERIOD_NS=$(SEED_PERIOD_NS) \
	  $(OPENSTA) sta/sta.tcl > $(OUT)/top_N4_sta.log 2>&1

sta-top8: synth-top8
	LIBERTY="$(LIBERTY)" NETLIST=$(OUT)/top_N8_netlist.sta.v TOP=top PERIOD_NS=$(SEED_PERIOD_NS) \
	  $(OPENSTA) sta/sta.tcl > $(OUT)/top_N8_sta.log 2>&1

# ---- fmax sweeps ----

sweep-pe: synth-pe
	LIBERTY="$(LIBERTY)" STA=$(OPENSTA) ./run_sweep.sh pe $(OUT)/pe_netlist.sta.v 6.0 0.2 30 pe > $(OUT)/pe_sweep_summary.log 2>&1

sweep-top4: synth-top4
	LIBERTY="$(LIBERTY)" STA=$(OPENSTA) ./run_sweep.sh top $(OUT)/top_N4_netlist.sta.v 4.0 0.2 40 top_N4 > $(OUT)/top_N4_sweep_summary.log 2>&1

sweep-top8: synth-top8
	LIBERTY="$(LIBERTY)" STA=$(OPENSTA) ./run_sweep.sh top $(OUT)/top_N8_netlist.sta.v 20.0 0.4 30 top_N8 > $(OUT)/top_N8_sweep_summary.log 2>&1

# ---- interface blocks: AXI4 DMA bridge and MMIO command-queue regs ----
# (LibreLane PnR was attempted first; still blocked after the 20-min cap, see INSTALL.md #5.
# FIFOs in axi4_dma_bridge have no memory-compiler SRAM in this open PDK, so RD/WR FIFOs
# (default depth 256) map straight to flip-flops, same as scratchpad_dbuf above.)

synth-axi-bridge: $(OUT)
	SRCS="$(RTL)/stream_ctrl.sv $(RTL)/axi/axi4_dma_bridge.sv" TOP=axi4_dma_bridge NVAL=4 \
	  LIBERTY="$(LIBERTY)" PERIOD_NS=$(SEED_PERIOD_NS) \
	  OUTV=$(OUT)/axi4_dma_bridge_netlist.v OUTLOG=$(OUT)/axi4_dma_bridge_stat.log \
	  $(YOSYS) -c synth/synth.tcl > $(OUT)/axi4_dma_bridge_synth.log 2>&1
	sed 's/ signed//g' $(OUT)/axi4_dma_bridge_netlist.v > $(OUT)/axi4_dma_bridge_netlist.sta.v

sta-axi-bridge: synth-axi-bridge
	LIBERTY="$(LIBERTY)" NETLIST=$(OUT)/axi4_dma_bridge_netlist.sta.v TOP=axi4_dma_bridge \
	  PERIOD_NS=$(SEED_PERIOD_NS) $(OPENSTA) sta/sta.tcl > $(OUT)/axi4_dma_bridge_sta.log 2>&1


# axi4_dma_bridge has a single-gate huge-fanout artifact (see RESULTS.md, same class as
# top_N8's rst path) that pushes its real convergence period out past 300ns; start the
# sweep near there instead of wasting ~1700 tiny 0.2ns steps.
sweep-axi-bridge: synth-axi-bridge
	LIBERTY="$(LIBERTY)" STA=$(OPENSTA) ./run_sweep.sh axi4_dma_bridge $(OUT)/axi4_dma_bridge_netlist.sta.v 340.0 10 20 axi4_dma_bridge > $(OUT)/axi4_dma_bridge_sweep_summary.log 2>&1

synth-cmdq: $(OUT)
	SRCS="$(RTL)/mmio/cmd_queue_regs.sv" TOP=cmd_queue_regs \
	  PARAMS="ADDR_W=32" LIBERTY="$(LIBERTY)" PERIOD_NS=$(SEED_PERIOD_NS) \
	  OUTV=$(OUT)/cmd_queue_regs_netlist.v OUTLOG=$(OUT)/cmd_queue_regs_stat.log \
	  $(YOSYS) -c synth/synth.tcl > $(OUT)/cmd_queue_regs_synth.log 2>&1
	sed 's/ signed//g' $(OUT)/cmd_queue_regs_netlist.v > $(OUT)/cmd_queue_regs_netlist.sta.v

sta-cmdq: synth-cmdq
	LIBERTY="$(LIBERTY)" NETLIST=$(OUT)/cmd_queue_regs_netlist.sta.v TOP=cmd_queue_regs \
	  PERIOD_NS=$(SEED_PERIOD_NS) $(OPENSTA) sta/sta.tcl > $(OUT)/cmd_queue_regs_sta.log 2>&1

sweep-cmdq: synth-cmdq
	LIBERTY="$(LIBERTY)" STA=$(OPENSTA) ./run_sweep.sh cmd_queue_regs $(OUT)/cmd_queue_regs_netlist.sta.v 4.0 0.2 60 cmd_queue_regs > $(OUT)/cmd_queue_regs_sweep_summary.log 2>&1

# ---- gate-level regression ----

gls: synth-top4
	$(MAKE) -C gls run

results:
	@echo "see RESULTS.md; regenerate logs with 'make all' first"

clean:
	rm -rf $(OUT)/*.v $(OUT)/*.log
	$(MAKE) -C gls clean
