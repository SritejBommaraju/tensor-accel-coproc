N ?= 4
TOP = stream_top
RTL = ../../rtl/pe.sv ../../rtl/systolic_array.sv ../../rtl/sim_ram.sv ../../rtl/stream_ctrl.sv ../../rtl/stream_top.sv

.PHONY: run lint clean

run: obj_dir/V$(TOP)
	./obj_dir/V$(TOP)

# sim_ram's two instances (act/weight, results) get distinct mangled class names per DEPTH/WIDTH
# that we can't predict from N alone, so: verilate first, read the real names out of the
# generated stream_top wrapper header, then build tb_stream.cpp against those exact types.
obj_dir/V$(TOP): $(RTL) tb_stream.cpp
	verilator --cc --exe -Wall --top-module $(TOP) -GN=$(N) $(RTL) tb_stream.cpp -CFLAGS "-DNN=$(N)"
	WRAM=$$(grep -oP 'V$(TOP)_sim_ram\w*(?=\* u_ram_aw)' obj_dir/V$(TOP)_$(TOP).h); \
	CRAM=$$(grep -oP 'V$(TOP)_sim_ram\w*(?=\* u_ram_c)' obj_dir/V$(TOP)_$(TOP).h); \
	printf '#include "%s.h"\n#include "%s.h"\nusing WRamT = %s;\nusing CRamT = %s;\n' \
	    "$$WRAM" "$$CRAM" "$$WRAM" "$$CRAM" > obj_dir/ram_types.h
	$(MAKE) -C obj_dir -f V$(TOP).mk

lint:
	verilator --lint-only -Wall --top-module $(TOP) -GN=$(N) $(RTL)

clean:
	rm -rf obj_dir
