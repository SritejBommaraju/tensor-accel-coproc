# Builds an ungated tb_power (rtl/top.sv) and a gated tb_power_cg (rtl/cg/top_cg.sv) as two
# independent Verilator executables, runs both over four identical-stimulus scenarios (dumping
# VCDs + per-cycle psum CSVs), checks psum_out bit-equivalence, then reports toggle counts.
# `run` does the whole flow for N=4 and N=8.
VROOT := $(shell verilator --getenv VERILATOR_ROOT 2>/dev/null || echo /usr/share/verilator)
RTL_BASE = ../../rtl/pe.sv ../../rtl/systolic_array.sv ../../rtl/top.sv
RTL_CG   = ../../rtl/cg/icg_cell.sv ../../rtl/cg/pe_cg.sv ../../rtl/cg/systolic_array_cg.sv ../../rtl/cg/top_cg.sv
NS = 4 8

.PHONY: run lint clean one

run:
	rm -f results.md
	mkdir -p vcd
	@for n in $(NS); do $(MAKE) N=$$n one || exit 1; done

one: obj_dir_base_$(N)/Vtop__ALL.a obj_dir_cg_$(N)/Vtop_cg__ALL.a
	g++ -std=c++17 -O2 -DNN=$(N) \
	    -Iobj_dir_base_$(N) -I$(VROOT)/include -I$(VROOT)/include/vltstd \
	    $(VROOT)/include/verilated.cpp $(VROOT)/include/verilated_vcd_c.cpp $(VROOT)/include/verilated_threads.cpp \
	    tb_power.cpp obj_dir_base_$(N)/Vtop__ALL.a -lpthread -o tb_power_$(N)
	g++ -std=c++17 -O2 -DNN=$(N) -DGATED \
	    -Iobj_dir_cg_$(N) -I$(VROOT)/include -I$(VROOT)/include/vltstd \
	    $(VROOT)/include/verilated.cpp $(VROOT)/include/verilated_vcd_c.cpp $(VROOT)/include/verilated_threads.cpp \
	    tb_power.cpp obj_dir_cg_$(N)/Vtop_cg__ALL.a -lpthread -o tb_power_cg_$(N)
	./tb_power_$(N)
	./tb_power_cg_$(N)
	python3 check_equiv.py $(N)
	python3 toggle_count.py $(N)

obj_dir_base_$(N)/Vtop__ALL.a: $(RTL_BASE)
	verilator --cc --trace -Wall --top-module top -GN=$(N) -Mdir obj_dir_base_$(N) $(RTL_BASE)
	$(MAKE) -C obj_dir_base_$(N) -f Vtop.mk

obj_dir_cg_$(N)/Vtop_cg__ALL.a: $(RTL_CG)
	verilator --cc --trace -Wall --top-module top_cg -GN=$(N) -Mdir obj_dir_cg_$(N) --prefix Vtop_cg $(RTL_CG)
	$(MAKE) -C obj_dir_cg_$(N) -f Vtop_cg.mk

lint:
	verilator --lint-only --assert -Wall --top-module top_cg -GN=4 $(RTL_CG)

clean:
	rm -rf obj_dir_base_* obj_dir_cg_* vcd tb_power_* results.md
