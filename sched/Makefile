RTL = ../rtl/pe.sv ../rtl/systolic_array.sv ../rtl/top.sv

.PHONY: all clean

all: obj_dir/Vtop

obj_dir/Vtop: $(RTL) tile_runner.cpp
	verilator --cc --exe --build -Wall -GN=4 --top-module top $(RTL) tile_runner.cpp -Mdir obj_dir -o Vtop

clean:
	rm -rf obj_dir
