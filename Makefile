# Module 2 Group 7 -- Olist delivery-performance pipeline.
#
# The whole pipeline in dependency order:
#     make all   ==   manifest -> quality gate -> load -> dbt build -> tests
#
# Every target is safe to rerun: the loader truncates per batch and dbt models
# are rebuilt from source, so nothing accumulates duplicates.

SHELL       := /bin/bash
DBT         := cd dbt_project && dbt
DBT_TARGET  ?= dev

# Load .env and export it to every recipe. python-dotenv covers the Python
# scripts, but dbt resolves env_var() against the real process environment, so
# without this every dbt target fails with "Env var required but not provided".
ifneq (,$(wildcard .env))
include .env
export
endif

.DEFAULT_GOAL := help
.PHONY: help setup manifest gate ingest deps debug build test docs snapshot analyse dashboard lint unit all evidence clean

help:  ## Show this help
	@# Scan only this Makefile. `include .env` appends .env to MAKEFILE_LIST, and
	@# grep across two files prefixes every match with the filename, which awk
	@# then reads as the target name.
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(firstword $(MAKEFILE_LIST)) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------
setup:  ## Install dependencies and dbt packages (run once per machine)
	pip install -r requirements.txt
	$(DBT) deps

deps:  ## Refresh dbt packages only
	$(DBT) deps

debug:  ## Verify the dbt connection (use this, not a bare `dbt debug`)
	$(DBT) debug --target $(DBT_TARGET)

# ---------------------------------------------------------------------------
# ingestion  (Quality Gate 1 runs BEFORE anything reaches BigQuery)
# ---------------------------------------------------------------------------
manifest:  ## Checksum and row-count the local CSVs, no cloud calls
	python ingestion/load_olist.py --manifest-only

gate: manifest  ## QUALITY GATE 1: validate the CSV files before loading
	python quality/run_raw_gate.py

ingest: gate  ## Upload to GCS and load into BigQuery raw, then reconcile
	python ingestion/load_olist.py

# ---------------------------------------------------------------------------
# transformation  (Quality Gate 2 is dbt build: run + test together)
# ---------------------------------------------------------------------------
build:  ## QUALITY GATE 2: models, snapshots and tests in dependency order
	$(DBT) build --target $(DBT_TARGET)

snapshot:  ## Run the snapshot alone (dbt build already includes it)
	$(DBT) snapshot --target $(DBT_TARGET)

test:  ## Run tests only, against whatever is already built
	$(DBT) test --target $(DBT_TARGET)

docs:  ## Generate and serve the dbt lineage graph and model docs
	# $(DBT) expands to `cd dbt_project && dbt`, so chaining two $(DBT) calls
	# with && on one recipe line ran `cd dbt_project` twice in the SAME shell,
	# the second time from inside dbt_project/ itself -- "No such file or
	# directory", every time, right after generate had already succeeded.
	# Make gives each recipe LINE its own fresh shell by default, so splitting
	# these onto two lines lets each `cd dbt_project` start from the
	# Makefile's own directory instead of compounding.
	$(DBT) docs generate --target $(DBT_TARGET)
	$(DBT) docs serve

# ---------------------------------------------------------------------------
# analysis and code quality
# ---------------------------------------------------------------------------
analyse:  ## Execute the notebooks top to bottom, exactly as a reviewer would
	jupyter nbconvert --to notebook --execute --inplace \
		notebooks/01_profiling.ipynb \
		notebooks/02_delivery_performance.ipynb \
		notebooks/03_business_kpis.ipynb

dashboard:  ## Serve the interactive delivery-performance dashboard
	streamlit run dashboard/app.py

lint:  ## Lint the dbt SQL
	cd dbt_project && sqlfluff lint models tests

unit:  ## Run the Python unit tests (no cloud credentials needed)
	pytest tests -q

# ---------------------------------------------------------------------------
# end to end
# ---------------------------------------------------------------------------
all: gate ingest build unit  ## The full pipeline, in order, with both gates
	@echo ""
	@echo "Pipeline complete. Run 'make analyse' for the notebooks, 'make dashboard' for the UI."

evidence:  ## Collect test artifacts into docs/evidence/ for the report
	@mkdir -p docs/evidence
	@cp dbt_project/target/run_results.json docs/evidence/ 2>/dev/null || true
	@cp dbt_project/target/manifest.json     docs/evidence/dbt_manifest.json 2>/dev/null || true
	@cp ingestion/manifest.json              docs/evidence/ingestion_manifest.json 2>/dev/null || true
	@echo "Evidence copied to docs/evidence/"

clean:  ## Remove dbt build artifacts
	$(DBT) clean
