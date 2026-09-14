N ?= 4
TOP = coproc_axi_sim_top
RTL = ../../rtl/pe.sv ../../rtl/systolic_array.sv ../../rtl/stream_ctrl.sv \
      ../../rtl/axi/axi4_dma_bridge.sv ../../rtl/axi/axi4_sim_ram.sv \
      ../../rtl/mmio/cmd_queue_regs.sv ../../rtl/mmio/coproc_axi_top.sv ../../rtl/mmio/coproc_axi_sim_top.sv
SVA = ../axi/axi_protocol_check.sv
SW = ../../sw/coproc_driver.h ../../sw/int8_mlp.h ../../sw/coproc_mmio.h

.PHONY: run lint clean check-c

run: obj_dir/V$(TOP)
	./obj_dir/V$(TOP)

# u_dut (stream_axi_top) and its own u_ram_rd/u_ram_wr get compiler-mangled class names we can't
# predict from N alone: verilate first, scrape the real names out of the generated headers (same
# trick as sim/axi/Makefile and sim/mmio/Makefile), then build tb_fullstack.cpp against those.
obj_dir/V$(TOP): $(RTL) $(SVA) tb_fullstack.cpp $(SW)
	verilator --cc --exe --assert -Wall -Wno-UNOPTFLAT -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM -Wno-PINCONNECTEMPTY -Wno-CASEINCOMPLETE -Wno-WIDTHEXPAND \
	    --top-module $(TOP) -GN=$(N) -I../../rtl/mmio -I../../rtl/axi $(RTL) $(SVA) tb_fullstack.cpp \
	    -CFLAGS "-DNN=$(N) -I../../../sw"
	RDRAM=$$(grep -oP 'V$(TOP)_axi4_sim_ram\w*(?=\* u_ram_rd)' obj_dir/V$(TOP)_$(TOP).h); \
	WRRAM=$$(grep -oP 'V$(TOP)_axi4_sim_ram\w*(?=\* u_ram_wr)' obj_dir/V$(TOP)_$(TOP).h); \
	printf '#include "%s.h"\n#include "%s.h"\nusing RdRamT = %s;\nusing WrRamT = %s;\n' \
	    "$$RDRAM" "$$WRRAM" "$$RDRAM" "$$WRRAM" > obj_dir/ram_types.h
	$(MAKE) -C obj_dir -f V$(TOP).mk

# proves sw/coproc_driver.h + sw/int8_mlp.h are plain, portable, warning-clean C99 -- no
# Verilator/C++ headers involved, bare-metal ops path only.
check-c: check_c99.c $(SW)
	gcc -std=c99 -Wall -Wextra -Werror -I../../sw -o obj_dir_check99.out check_c99.c
	./obj_dir_check99.out
	rm -f obj_dir_check99.out

lint:
	verilator --lint-only --assert -Wall -Wno-UNOPTFLAT -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM -Wno-PINCONNECTEMPTY -Wno-CASEINCOMPLETE -Wno-WIDTHEXPAND \
	    --top-module $(TOP) -GN=$(N) $(RTL) $(SVA)

clean:
	rm -rf obj_dir obj_dir_check99.out
