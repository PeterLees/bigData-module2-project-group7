# Architecture Decision Records

One file per decision that was expensive to make and would be expensive to reverse.
Each records what we chose, what we rejected, and — most importantly — the condition
that would make us revisit it.

The point is not documentation for its own sake. In the Q&A the question is never
"what did you build?", it is "why not X?". These are the answers, written down while
the reasoning was fresh.

| ADR | Decision | Status |
|---|---|---|
| [001](001-dataset-selection.md) | Olist as the primary dataset | Accepted |
| [002](002-bigquery-us-region.md) | BigQuery, US multi-region | Accepted |
| [003](003-elt-with-dbt.md) | ELT with dbt rather than ETL | Accepted |
| [004](004-order-grain-and-fanout.md) | Order grain for delivery, item grain for revenue | Accepted |
| [005](005-orchestration-scope.md) | Dagster + GitHub Actions; no Spark, no Kafka | Accepted |
| [006](006-quality-gate-split.md) | Great Expectations before load, dbt tests after | Accepted |
