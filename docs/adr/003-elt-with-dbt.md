# ADR-003: ELT with dbt, not ETL

**Status:** Accepted · **Date:** 2026-09-01 · **Owner:** Modeling Owner

## Context

The brief requires transformation and names dbt as an option. The real decision is not
"which tool" but **where the transformation happens**: before loading (ETL) or inside
the warehouse after loading (ELT).

## Decision

ELT. Load the source files into an immutable `olist_raw` layer with explicit schemas
and no business logic, then transform entirely in BigQuery with dbt-core.

## Rationale

- **Replayability.** Raw preserves the source exactly, including the two misspelled
  product columns. Any transformation bug can be fixed and rerun against data we still
  have, without going back to Kaggle.
- **Reviewability.** dbt transformations are SQL and YAML in Git. They can be diffed
  in a pull request. A Python ETL script that mutates data in flight cannot be reviewed
  the same way, and its intermediate states are not inspectable after the fact.
- **Lineage, tests and docs from one source.** The DAG, the 161 data tests and the
  model documentation are all generated from the same model definitions, so they
  cannot drift from the code.
- **Compute is where the data is.** BigQuery does the work; nothing large moves across
  the network into a Python process.

Layering is `raw -> stg_ -> int_ -> dim_/fct_/agg_`. The `int_` layer exists
specifically to hold the fan-out controls (see [ADR-004](004-order-grain-and-fanout.md))
so that aggregation to order grain happens exactly once, in a named model with a
uniqueness test, rather than being re-derived in each consumer.

## Alternatives rejected

**Meltano for extract-load.** Genuinely the right tool for a live, incrementally
growing source, and it is what the course used. Rejected here because Olist is a
static CSV export: there is no incremental key to bookmark, no state to advance and
no deletions to detect. Meltano's catalog, state and connector configuration would be
ceremony around a problem we do not have. A ~200-line Python loader with a checksum
manifest and `WRITE_TRUNCATE` gives idempotency plus a reconciliation report in less
code and with fewer moving parts. Meltano is documented as the migration path the
moment a live source is added.

**Pandas ETL before loading.** Would put the business definitions in a script with no
lineage, no tests and no documentation, and would make the "which SQL produced this
number?" question unanswerable.

**dbt Cloud.** Costs money and hides the orchestration we are being asked to
demonstrate.

## Consequences

- Everyone needs a BigQuery connection to develop, which is why per-person
  `dbt_<name>` dev datasets exist.
- Transformation cost is BigQuery cost, which is why partitioning, clustering and the
  ban on `SELECT *` in models are enforced rather than suggested.

## Revisit if

A source appears that cannot legally or practically be landed raw in the warehouse
(personal data requiring pre-load masking would be the obvious trigger).
