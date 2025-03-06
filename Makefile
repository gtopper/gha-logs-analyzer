.PHONY: all
all: download unzip analyze

.PHONY: download
download:
	python download_logs.py

.PHONY: unzip
unzip:
	./unzip.sh

.PHONY: analyze
analyze:
	python analyze_logs.py

.PHONY: install-requirements
install-requirements:
	pip install -r requirements.txt
