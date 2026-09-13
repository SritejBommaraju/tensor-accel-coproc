TOP = top
RTL = ../../rtl/pe.sv ../../rtl/systolic_array.sv ../../rtl/top.sv
SVA = ../../rtl/sva/pe_sva.sv ../../rtl/sva/systolic_array_sva.sv ../../rtl/sva/bind_all.sv
MUTANTS = nogate psum act

.PHONY: run lint clean mutants

run: obj_dir/V$(TOP)
	./obj_dir/V$(TOP)

obj_dir/V$(TOP): $(RTL) $(SVA) tb_sva.cpp
	verilator --cc --exe --build --assert -Wall --top-module $(TOP) $(RTL) $(SVA) tb_sva.cpp

lint:
	verilator --lint-only --assert -Wall --top-module $(TOP) $(RTL) $(SVA)

# Each mutant swaps in a broken pe.sv in place of the real one, in its own obj_dir, and must
# make the assertion-checking testbench exit non-zero (i.e. the checkers catch the bug).
mutants:
	@for m in $(MUTANTS); do \
		rm -rf obj_dir_mut_$$m; \
		mkdir obj_dir_mut_$$m; \
		verilator --cc --exe --build --assert -Wall -Wno-DECLFILENAME -Wno-UNOPTFLAT --top-module $(TOP) -Mdir obj_dir_mut_$$m \
			mutants/pe_mut_$$m.sv ../../rtl/systolic_array.sv ../../rtl/top.sv $(SVA) tb_sva.cpp \
			> obj_dir_mut_$$m/build.log 2>&1 || { echo "BUILD FAILED for mutant $$m"; cat obj_dir_mut_$$m/build.log; exit 1; }; \
		if ./obj_dir_mut_$$m/V$(TOP) > obj_dir_mut_$$m/run.log 2>&1; then \
			echo "UNDETECTED: mutant $$m did not trigger any assertion"; \
			cat obj_dir_mut_$$m/run.log; \
			exit 1; \
		else \
			fired=$$(grep -o 'u_pe_sva\.[A-Z_]*\|u_systolic_array_sva\.[A-Za-z0-9_.]*\.[A-Z_]*' obj_dir_mut_$$m/run.log | sed 's/.*\.//' | sort -u | tr '\n' ' '); \
			echo "DETECTED: mutant $$m killed by assertion(s): $${fired:-see run.log}"; \
		fi; \
	done

clean:
	rm -rf obj_dir obj_dir_mut_*
