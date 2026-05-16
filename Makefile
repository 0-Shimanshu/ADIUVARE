PYTHON ?= python

.PHONY: test build tui

test:
	$(PYTHON) -m pytest -q

build:
	$(PYTHON) -m build

tui:
	$(PYTHON) -m adiuvare.cli

