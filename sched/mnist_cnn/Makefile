PY = python3

.PHONY: all fetch train quant rtl clean

all: rtl

fetch:
	$(PY) ../mnist/fetch_mnist.py

train: fetch
	$(PY) train_cnn.py

quant: train
	$(PY) quantize_cnn.py

../obj_dir/Vtop:
	$(MAKE) -C ..

rtl: quant ../obj_dir/Vtop
	$(PY) run_rtl_cnn.py --count 200

clean:
	rm -f weights_fp32.npz weights_int8.npz weights_int8.graph.pkl results.txt
