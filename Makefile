.PHONY: help install install-dev test test-cov lint format verify smoke run force health clean

PYTHON ?= python3
VENV   ?= venv
PIP    := $(VENV)/bin/pip
PY     := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest
RUFF   := $(VENV)/bin/ruff

help:
	@echo "CyberDigest developer targets"
	@echo "  make install-dev  Create venv + install runtime & dev deps"
	@echo "  make test         Run unit/integration tests"
	@echo "  make test-cov     Tests + coverage gate (70%)"
	@echo "  make lint         Ruff lint"
	@echo "  make verify       Full local verification (lint + cov + smoke)"
	@echo "  make smoke        CLI smoke (--version/--help/--healthcheck)"
	@echo "  make force        Force one digest run"
	@echo "  make health       Run healthcheck"
	@echo "  make clean        Remove caches and build artifacts"

$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

install: $(VENV)/bin/python
	$(PIP) install -r requirements.txt

install-dev: $(VENV)/bin/python
	$(PIP) install -e .[dev]

test: $(VENV)/bin/python
	$(PYTEST) -q

test-cov: $(VENV)/bin/python
	$(PYTEST) -q --cov=cyberdigest --cov-report=term-missing --cov-fail-under=80

lint: $(VENV)/bin/python
	$(RUFF) check src/cyberdigest tests news_agent.py

security: $(VENV)/bin/python
	$(PIP) install -q pip-audit
	$(VENV)/bin/pip-audit -r requirements.txt

format: $(VENV)/bin/python
	$(RUFF) check --fix src/cyberdigest tests news_agent.py || true
	$(RUFF) format src/cyberdigest tests news_agent.py || true

smoke: $(VENV)/bin/python
	$(PY) news_agent.py --version
	$(PY) news_agent.py --help >/dev/null
	$(PY) -m cyberdigest --version
	$(PY) -m compileall -q src/cyberdigest news_agent.py

health: $(VENV)/bin/python
	$(PY) news_agent.py --healthcheck || true

force: $(VENV)/bin/python
	$(PY) news_agent.py --force --cli-only

verify: install-dev lint test-cov smoke
	@echo ""
	@echo "✔  verify passed — lint, coverage≥70%, CLI smoke OK"

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -not -path './venv/*' -exec rm -rf {} + 2>/dev/null || true
