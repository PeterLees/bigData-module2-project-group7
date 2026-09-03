# ADR-005: Dagster + GitHub Actions; explicitly no Spark, Kafka or Redis

**Status:** Accepted · **Date:** 2026-09-01 · **Owner:** Orchestration / DevOps Owner

## Context

Item 6 of the brief (pipeline orchestration) is optional. The course guidance is
blunt about the trap here: complexity earns credit only when it solves a stated
constraint, and adding Kafka or Spark to a 120 MB static dataset is over-engineering
that a technical reviewer will identify immediately.

At the same time, "we ran some scripts in order" is not orchestration, and the
guidance is equally clear that a cron job alone does not qualify.

## Decision

**Take item 6, with Dagster and GitHub Actions. Explicitly exclude Spark, Kafka,
Redis and Kubernetes**, and document the threshold that would justify each.

- **Dagster** models the pipeline as assets: manifest → GX gate → BigQuery load →
  dbt models, with every dbt test surfacing as an asset check. A daily schedule, a
  retry policy on the idempotent ingest steps only, and a demonstrable fail-stop.
- **GitHub Actions** runs two workflows: `ci.yml` on every pull request
  (credential-free: lint, `dbt parse`, pytest, a secret-scan guard) and
  `scheduled.yml` nightly (credentialed: `dbt build` against the shared marts, with
  run results uploaded as artifacts).

## Rationale

Orchestration is where the *operational* evidence comes from, and operational evidence
is hard to fake:

- Dagster shows a failed upstream asset **skipping** downstream assets. That is the
  difference between orchestration and scheduling, and it is a screenshot.
- Retries are configured **only** on the ingest assets, because those are genuinely
  idempotent (`WRITE_TRUNCATE`). Transformation failures are code defects, and
  retrying them would hide the signal.
- CI catches broken `ref()`s, malformed YAML and style drift before merge, without
  needing cloud credentials — so it also runs safely on a fork.

## Alternatives rejected

**Apache Spark.** 1.55M rows and 120 MB fit comfortably in BigQuery and in
single-node memory. A cluster adds scheduling, shuffle and operational cost for no
measurable gain. *Would adopt if:* the working set exceeded single-node memory, or a
job missed its SLA on BigQuery with the scan already optimised.

**Kafka + Structured Streaming.** The dataset is a static historical export. There is
no event stream and no business value that decays with latency. *Would adopt if:* a
live order feed existed and a decision — fraud hold, courier dispatch — lost value
within minutes.

**Redis.** No low-latency serving surface exists in this project, and a cache is not
a source of truth. *Would adopt if:* a customer-facing API needed sub-10ms reads of a
precomputed segment.

**Cron alone.** Runs everything regardless of failure. Not orchestration.

**Airflow.** Perfectly viable. Dagster was chosen because its asset-centric model maps
directly onto dbt models, so the lineage graph is the data lineage rather than a
parallel task graph that has to be kept in sync by hand.

**Cloud Composer.** Managed Airflow, and the cheapest tier still costs real money per
month for a pipeline that processes 120 MB.

## Consequences

- A running Dagster instance is a local dev tool, not production infrastructure. The
  nightly GitHub Actions build is the automated schedule that actually runs unattended.
- Exactly one service account exists, for CI, with `bigquery.jobUser` plus Data Editor
  on staging and marts only. It cannot touch `olist_raw`, so a CI bug can never
  destroy the reproducible copy of the source data.
- The daily Dagster schedule exists to prove the pipeline reruns cleanly and to catch
  drift, not because new data arrives overnight. Stated plainly in the code.
