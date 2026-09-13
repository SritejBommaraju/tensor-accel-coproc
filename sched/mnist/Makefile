PY = python3

.PHONY: all fetch train quant rtl clean

all: rtl

fetch:
	$(PY) fetch_mnist.py

train: fetch
	$(PY) train_fp32.py

quant: train
	$(PY) quantize.py

../obj_dir/Vtop:
	$(MAKE) -C ..

rtl: quant ../obj_dir/Vtop
	$(PY) run_rtl.py

clean:
	rm -f weights_fp32.npz weights_int8.npz results.txt
