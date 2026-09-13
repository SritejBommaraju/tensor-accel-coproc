N ?= 4
TOP = coproc_mmio_top
RTL = ../../rtl/pe.sv ../../rtl/systolic_array.sv ../../rtl/sim_ram.sv ../../rtl/stream_ctrl.sv \
      ../../rtl/stream_top.sv ../../rtl/mmio/cmd_queue_regs.sv ../../rtl/mmio/coproc_mmio_top.sv

.PHONY: run lint clean

run: obj_dir/V$(TOP)
	./obj_dir/V$(TOP)

# sim_ram lives two levels down (top -> u_stream:stream_top -> u_ram_aw/u_ram_c) with mangled
# names that depend on N/ADDR_W, so: verilate first, scrape the real names out of the generated
# headers, then build tb_mmio.cpp against those exact types (same trick as sim/stream/Makefile).
obj_dir/V$(TOP): $(RTL) tb_mmio.cpp
	verilator --cc --exe -Wall --top-module $(TOP) -GN=$(N) $(RTL) tb_mmio.cpp -CFLAGS "-DNN=$(N)"
	USTREAM=$$(grep -oP 'V$(TOP)_\w*(?=\* u_stream)' obj_dir/V$(TOP)_$(TOP).h); \
	WRAM=$$(grep -oP 'V$(TOP)_sim_ram\w*(?=\* u_ram_aw)' obj_dir/$${USTREAM}.h); \
	CRAM=$$(grep -oP 'V$(TOP)_sim_ram\w*(?=\* u_ram_c)' obj_dir/$${USTREAM}.h); \
	printf '#include "%s.h"\n#include "%s.h"\n#include "%s.h"\nusing StreamT = %s;\nusing WRamT = %s;\nusing CRamT = %s;\n' \
	    "$$USTREAM" "$$WRAM" "$$CRAM" "$$USTREAM" "$$WRAM" "$$CRAM" > obj_dir/ram_types.h
	$(MAKE) -C obj_dir -f V$(TOP).mk

lint:
	verilator --lint-only -Wall --top-module $(TOP) -GN=$(N) $(RTL)

clean:
	rm -rf obj_dir
