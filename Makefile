# Convenience targets for the hotel KPI pipeline.
# Most targets assume an activated virtualenv (see `make install`).

VENV ?= .venv
PY   ?= $(VENV)/bin/python
PIP  ?= $(VENV)/bin/pip

HOTEL    ?= 1035
FROM_DATE ?= 2026-05-01
TO_DATE   ?= 2026-05-31
CSV       ?= output/kpi_$(HOTEL)_$(subst -,_,$(FROM_DATE))_to_$(subst -,_,$(TO_DATE)).csv

.PHONY: help install run test lint format dbt-test pytest reconcile check clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Create venv and install runtime + dev dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

run: ## Run the pipeline (override HOTEL/FROM_DATE/TO_DATE as needed)
	$(PY) run_pipeline.py --hotel-id $(HOTEL) --from-date $(FROM_DATE) --to-date $(TO_DATE)

lint: ## Lint Python (ruff) and SQL (sqlfluff)
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/sqlfluff lint

format: ## Auto-format Python and SQL
	$(VENV)/bin/ruff format .
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/sqlfluff fix --force

pytest: ## Run the Python test suite
	$(PY) -m pytest

reconcile: run ## Run the pipeline then the independent reconciliation
	$(PY) scripts/cross_check.py --csv $(CSV) \
		--hotel-id $(HOTEL) --from-date $(FROM_DATE) --to-date $(TO_DATE)

dbt-test: ## Build dbt models and run dbt tests
	HOTEL_KPI_DUCKDB_PATH=$(CURDIR)/dbt/hotel_kpi/hotel_kpi.duckdb \
		$(VENV)/bin/dbt build --project-dir dbt/hotel_kpi --profiles-dir dbt/hotel_kpi \
		--vars '{hotel_id: $(HOTEL), from_date: $(FROM_DATE), to_date: $(TO_DATE)}'

test: reconcile pytest ## Run the full pipeline, reconciliation, and pytest

check: lint test ## What CI runs: lint + full test

clean: ## Remove generated artifacts
	rm -f dbt/hotel_kpi/hotel_kpi.duckdb dbt/hotel_kpi/hotel_kpi.duckdb.wal
	rm -rf dbt/hotel_kpi/target dbt/hotel_kpi/logs
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
