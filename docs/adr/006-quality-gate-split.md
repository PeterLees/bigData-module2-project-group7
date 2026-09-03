# ADR-006: Great Expectations before the load, dbt tests after

**Status:** Accepted · **Date:** 2026-09-01 · **Owner:** Quality Owner

## Context

The brief names both Great Expectations and SQL-based checks. Using both without a
clear division of responsibility is tool collecting, and a reviewer will ask why two
testing frameworks are present. There needs to be a job that only one of them can do.

## Decision

Two gates with a strict boundary:

**Quality Gate 1 — Great Expectations, on the files, before anything is loaded.**
Column set and order, row count against the manifest, non-null primary keys, money
ranges, categorical domains, coordinate bounding box. Failure blocks the BigQuery
load entirely.

**Quality Gate 2 — dbt tests, on the models, after loading.** 161 tests covering
uniqueness, not-null, referential integrity, accepted values, numeric ranges,
milestone chronology, delivery-measure validity, and source-to-mart reconciliation.
Failure blocks mart publication.

## Rationale

The boundary is not stylistic — it follows from what each tool can physically reach.

**dbt can only test data that is already in the warehouse.** By the time a dbt test
fails, the defect has been loaded. For most defects that is fine, because raw is
immutable and the fix is a rerun. But it means dbt structurally cannot answer
"should this file be loaded at all?" — and a malformed export (a renamed column, a
truncated download, a shifted delimiter) is exactly the failure where you want to
stop before the warehouse is touched.

**GX runs against the files on disk**, so it can. That is the job it is here to do,
and it is the only job it is here to do. Everything that lives in a table is dbt's,
because dbt tests sit inside the DAG, run automatically on every `dbt build`, and
produce failing rows rather than a boolean.

Severity is assigned deliberately rather than uniformly:

- **error** for anything that would make a published number wrong: keys, referential
  integrity, milestone chronology, revenue reconciliation, the `is_late` flag
  agreeing with `delay_vs_promise_days`.
- **warn** for `assert_payment_total_matches_order_value`, because Olist has
  *legitimate* mismatches — vouchers reduce the amount charged. Making this an error
  would produce a permanently red build that everyone learns to ignore, which is
  worse than no test. It stays as a monitored number and is reported openly.

## The fault-injection demonstration

A required Phase 6 deliverable, not an optional extra. Inject a duplicate
`order_item_key` and a negative price; capture the red tests, the failing rows, and
the fact that downstream marts did not build; fix; capture green. A passing test suite
proves nothing on its own — a suite that has been *seen to fail correctly* does.

## Alternatives rejected

**dbt tests only.** Cannot validate files pre-load. Would mean a corrupted export
reaches the warehouse before anything notices.

**GX everywhere, including on warehouse tables.** Duplicates what dbt already does,
sits outside the dbt DAG so it does not automatically block downstream models, and
means two places to look when a number is wrong.

**Only testing technical fields (not-null, unique).** Catches nothing about business
logic. It would not catch revenue doubling from a fan-out, an order delivered before
it was purchased, or an `is_late` flag that disagrees with the measure behind it —
which are the failures that actually reach a slide.
