TOP = top
RTL = ../rtl/pe.sv ../rtl/systolic_array.sv ../rtl/top.sv

N ?= 4
SEED ?= 1
COUNT ?= 20
M ?= 8

OBJ_DIR = obj_dir_N$(N)
VEC_DIR = vectors/N$(N)_M$(M)_S$(SEED)

.PHONY: run lint clean vectors

run: $(OBJ_DIR)/V$(TOP) vectors
	./$(OBJ_DIR)/V$(TOP) $(VEC_DIR)

vectors:
	python3 ../model/gen_vectors.py --seed $(SEED) --count $(COUNT) --n $(N) --m $(M) --out $(VEC_DIR)

$(OBJ_DIR)/V$(TOP): $(RTL) tb_main.cpp
	verilator --cc --exe --build -Wall --top-module $(TOP) -GN=$(N) -CFLAGS "-DTB_N=$(N) -std=c++17" \
		--Mdir $(OBJ_DIR) $(RTL) tb_main.cpp

lint:
	verilator --lint-only -Wall --top-module $(TOP) -GN=$(N) $(RTL)

clean:
	rm -rf obj_dir obj_dir_N* vectors
