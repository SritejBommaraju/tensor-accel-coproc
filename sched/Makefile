RTL = ../rtl/pe.sv ../rtl/systolic_array.sv ../rtl/top.sv

COPROC_RTL = ../rtl/pe.sv ../rtl/systolic_array.sv ../rtl/stream_ctrl.sv \
             ../rtl/axi/axi4_dma_bridge.sv ../rtl/axi/axi4_sim_ram.sv \
             ../rtl/mmio/cmd_queue_regs.sv ../rtl/mmio/coproc_axi_top.sv ../rtl/mmio/coproc_axi_sim_top.sv

.PHONY: all clean clean-coproc

all: obj_dir/Vtop

obj_dir/Vtop: $(RTL) tile_runner.cpp
	verilator --cc --exe --build -Wall -GN=4 --top-module top $(RTL) tile_runner.cpp -Mdir obj_dir -o Vtop

# axi4_sim_ram's two instances (read/write host memory) get distinct mangled class names per
# DATA_W/DEPTH we can't predict from N alone (same trick as sim/axi/Makefile): verilate first,
# grep the real names out of the generated header, then build coproc_runner.cpp against those.
obj_dir_coproc/Vcoproc_axi_sim_top: $(COPROC_RTL) coproc_runner.cpp
	verilator --cc --exe --assert -Wall -Wno-UNOPTFLAT -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM -Wno-PINCONNECTEMPTY -Wno-CASEINCOMPLETE -Wno-WIDTHEXPAND \
	    --top-module coproc_axi_sim_top -GN=4 $(COPROC_RTL) coproc_runner.cpp -Mdir obj_dir_coproc -o Vcoproc_axi_sim_top
	RDRAM=$$(grep -oP 'Vcoproc_axi_sim_top_axi4_sim_ram\w*(?=\* u_ram_rd)' obj_dir_coproc/Vcoproc_axi_sim_top_coproc_axi_sim_top.h); \
	WRRAM=$$(grep -oP 'Vcoproc_axi_sim_top_axi4_sim_ram\w*(?=\* u_ram_wr)' obj_dir_coproc/Vcoproc_axi_sim_top_coproc_axi_sim_top.h); \
	printf '#include "%s.h"\n#include "%s.h"\nusing RdRamT = %s;\nusing WrRamT = %s;\n' \
	    "$$RDRAM" "$$WRRAM" "$$RDRAM" "$$WRRAM" > obj_dir_coproc/ram_types.h
	$(MAKE) -C obj_dir_coproc -f Vcoproc_axi_sim_top.mk

clean: clean-coproc
	rm -rf obj_dir

clean-coproc:
	rm -rf obj_dir_coproc
