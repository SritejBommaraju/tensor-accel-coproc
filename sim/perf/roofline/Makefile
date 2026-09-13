.PHONY: run test clean

run: ../results.csv
	python3 roofline.py

../results.csv:
	$(MAKE) -C .. sweep

test:
	python3 -m unittest test_roofline.py -v

clean:
	rm -f roofline.md roofline.svg _test_tmp.csv
