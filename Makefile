VENV ?= .venv
VENV_PY := $(VENV)/bin/python
PY ?= $(VENV_PY)
BOOTSTRAP_PY ?= python3
OPP ?= ATL
ASOF ?=
ASOF_FLAG := $(if $(ASOF),--as-of $(ASOF),)

.PHONY: setup lint format typecheck ingest refresh validate test report check-report check fixtures break-feed restore-feed clean

# Creates $(VENV) only when PY is the default; with PY=... it installs into that interpreter.
setup:
ifeq ($(PY),$(VENV_PY))
	$(BOOTSTRAP_PY) -m venv $(VENV)
endif
	$(PY) -m pip install -r requirements.txt

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

typecheck:
	$(PY) -m mypy

ingest:
	$(PY) -m scout.ingest

refresh:
	$(PY) -m scout.ingest --refresh

validate:
	$(PY) -m scout.validate

test:
	$(PY) -m pytest -q

report:
	$(PY) -m scout.report --opponent $(OPP) $(ASOF_FLAG)

check-report:
	$(PY) -m scout.report --opponent ATL --no-pdf > /tmp/report_path.txt
	$(PY) -m scout.check_report $$(cat /tmp/report_path.txt)

# Everything a PR must pass.
check: lint typecheck ingest validate test check-report
	@echo "make check: all green"

fixtures:
	$(PY) scripts/make_fixtures.py

# Demo only: simulate an upstream schema change, then undo it.
break-feed:
	$(PY) scripts/simulate_upstream_change.py

restore-feed:
	$(PY) scripts/simulate_upstream_change.py --restore

clean:
	rm -rf data/clean reports/*.md reports/*.pdf reports/*.json
