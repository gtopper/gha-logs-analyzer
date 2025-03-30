BRANCH ?= development

.PHONY: all
all: download unzip analyze

.PHONY: download
download:
	BRANCH=$(BRANCH) python download_logs.py

.PHONY: unzip
unzip:
	BRANCH=$(BRANCH) ./unzip.sh

.PHONY: analyze
analyze:
	BRANCH=$(BRANCH) python analyze_logs.py

.PHONY: install-requirements
install-requirements:
	pip install -r requirements.txt
