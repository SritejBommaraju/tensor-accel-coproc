N ?= 4
RTL = ../../rtl/pe.sv ../../rtl/systolic_array.sv ../../rtl/top.sv
OBJDIR = obj_dir_n$(N)

.PHONY: run sweep test clean

run: $(OBJDIR)/Vtop
	./$(OBJDIR)/Vtop +csv=results.csv

$(OBJDIR)/Vtop: $(RTL) tb_perf.cpp metrics.h
	verilator --cc --exe --build -Wall --top-module top -GN=$(N) -CFLAGS "-DTB_N=$(N) -Wall" -Mdir $(OBJDIR) $(RTL) tb_perf.cpp

sweep:
	rm -f results.csv
	$(MAKE) N=4 run
	$(MAKE) N=8 run
	$(MAKE) N=16 run
	@echo "sweep complete: results.csv"

test: test_metrics
	./test_metrics

test_metrics: test_metrics.cpp metrics.h
	g++ -std=c++17 -Wall -Wextra -O2 -o test_metrics test_metrics.cpp

clean:
	rm -rf obj_dir_n* test_metrics results.csv
