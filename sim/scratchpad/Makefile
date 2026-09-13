TOP = scratchpad_dbuf
RTL = ../../rtl/scratchpad_dbuf.sv

.PHONY: run lint clean

run: obj_dir/V$(TOP)
	./obj_dir/V$(TOP)

obj_dir/V$(TOP): $(RTL) tb_scratchpad.cpp
	verilator --cc --exe --build -Wall --top-module $(TOP) $(RTL) tb_scratchpad.cpp

lint:
	verilator --lint-only -Wall --top-module $(TOP) $(RTL)
	verilator --lint-only -Wall --top-module $(TOP) -GDEPTH=1024 -GWIDTH=64 $(RTL)

clean:
	rm -rf obj_dir
