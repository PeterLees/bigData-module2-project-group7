# ADR-002: BigQuery, US multi-region

**Status:** Accepted · **Date:** 2026-09-01 · **Owner:** Platform Owner

## Context

A BigQuery dataset's location is **immutable after creation**, and datasets in
different locations cannot be joined. This decision therefore had to be made and
agreed before a single `bq mk` command was run — getting it wrong means deleting
everything and reloading.

## Decision

BigQuery as the warehouse. **US multi-region** for the GCS bucket and all four
BigQuery datasets (`olist_raw`, `olist_staging`, `olist_marts`, `olist_snapshots`).

## Rationale

Warehouse choice: BigQuery is the stack taught in course units 2.5–2.7, it separates
storage from compute so the free tier comfortably covers a 120 MB dataset, and its
columnar engine with partitioning and clustering gives us something concrete to
demonstrate on cost control.

Location: Olist carries **no data-residency constraint** — unlike London Bicycles,
which mandates the EU. Given a free choice, US multi-region gives the widest
compatibility with BigQuery public datasets should we enrich, keeps the always-free
tier (1 TB scanned + 10 GB stored per month) available, and is the default most
tooling assumes.

All resources are pinned to the same location, and `ingestion/load_olist.py` asserts
the dataset location at runtime and fails fast rather than producing a confusing
cross-region error several steps later.

## Alternatives rejected

**asia-southeast1** (lower latency for an Asia-based team). Rejected because it
cannot join US-hosted public datasets, and because latency on a 120 MB batch pipeline
is irrelevant — we would be optimising a number nobody experiences.

**Snowflake / DuckDB / Postgres.** Snowflake is not the taught stack and adds cost.
DuckDB is genuinely capable at this data size and is an excellent local tool, but it
gives no shared multi-user warehouse, no IAM story, and no partitioning-and-clustering
demonstration — three things this project is explicitly graded on.

## Consequences

- Expected spend is zero; the free tier covers the whole project many times over.
- Four separate datasets rather than one, so a defect stays reproducible in raw
  without contaminating marts, and the Analytics Owner can be given read-only access
  to marts alone.
- Cross-region joins are impossible by construction, which is the point.

## Revisit if

A future source or enrichment dataset is region-locked outside the US, in which case
the whole project moves — datasets cannot be relocated piecemeal.
