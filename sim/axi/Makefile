N ?= 4
TOP = stream_axi_top
RTL = ../../rtl/pe.sv ../../rtl/systolic_array.sv ../../rtl/stream_ctrl.sv \
      ../../rtl/axi/axi4_dma_bridge.sv ../../rtl/axi/axi4_sim_ram.sv ../../rtl/axi/stream_axi_top.sv
SVA = axi_protocol_check.sv

.PHONY: run lint clean

run: obj_dir/V$(TOP)
	./obj_dir/V$(TOP)

# axi4_sim_ram's two instances (read/write memories) get distinct mangled class names per
# DATA_W/DEPTH that we can't predict from N alone, so: verilate first, read the real names
# out of the generated stream_axi_top wrapper header, then build tb_axi.cpp against those.
obj_dir/V$(TOP): $(RTL) $(SVA) tb_axi.cpp
	verilator --cc --exe --assert -Wall -Wno-UNOPTFLAT -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM -Wno-PINCONNECTEMPTY -Wno-CASEINCOMPLETE -Wno-WIDTHEXPAND \
	    --top-module $(TOP) -GN=$(N) $(RTL) $(SVA) tb_axi.cpp -CFLAGS "-DNN=$(N)"
	RDRAM=$$(grep -oP 'V$(TOP)_axi4_sim_ram\w*(?=\* u_ram_rd)' obj_dir/V$(TOP)_$(TOP).h); \
	WRRAM=$$(grep -oP 'V$(TOP)_axi4_sim_ram\w*(?=\* u_ram_wr)' obj_dir/V$(TOP)_$(TOP).h); \
	printf '#include "%s.h"\n#include "%s.h"\nusing RdRamT = %s;\nusing WrRamT = %s;\n' \
	    "$$RDRAM" "$$WRRAM" "$$RDRAM" "$$WRRAM" > obj_dir/ram_types.h
	$(MAKE) -C obj_dir -f V$(TOP).mk

lint:
	verilator --lint-only --assert -Wall -Wno-UNOPTFLAT -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM -Wno-PINCONNECTEMPTY -Wno-CASEINCOMPLETE -Wno-WIDTHEXPAND \
	    --top-module $(TOP) -GN=$(N) $(RTL) $(SVA)

clean:
	rm -rf obj_dir
