.PHONY: install test redteam perf ci ci-fast lint smoke clean

PY ?= .venv/bin/python
PIP ?= .venv/bin/pip
PYTEST = $(PY) -m pytest

install:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev,extractors]"

test:
	$(PYTEST) tests/ -q --ignore=tests/redteam --ignore=tests/perf

redteam:
	$(PYTEST) tests/redteam/ -q

perf:
	$(PYTEST) tests/perf/ -q -s

lint:
	$(PY) -m ruff check src/ tests/ hooks/

smoke:
	$(PY) -m privacy_agent.cli audit verify

ci-fast:
	bash scripts/ci.sh fast

ci:
	bash scripts/ci.sh full

clean:
	rm -rf .venv .pytest_cache .ruff_cache build dist *.egg-info
	find . -name __pycache__ -exec rm -rf {} +
