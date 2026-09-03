# ADR-001: Olist Brazilian E-Commerce as the primary dataset

**Status:** Accepted · **Date:** 2026-09-01 · **Owner:** whole team

## Context

The brief permits three datasets: Olist, Instacart, and London Bicycles. The choice
constrains everything downstream — which business cases are possible, which course
capabilities we can demonstrate, and how much of the effort budget goes to wrangling
rather than to engineering.

We also had to pick a defensible business case early, because the course guidance is
explicit that the business case should determine the grain, the dimensions, the tests
and the final chart. Choosing a dataset without a business case in mind risks building
a warehouse that answers nothing in particular.

## Decision

**Olist**, with **delivery performance** (Business Case 3: *where and when are
deliveries late?*) as the primary business case.

## Rationale

Olist is the only one of the three that supports the full chain we need:

- **Nine related tables** — orders, items, payments, reviews, customers, products,
  sellers, geolocation, category translation. Enough relational structure to make a
  star schema a genuine design exercise rather than a formality.
- **Real money columns** — so revenue reconciliation is possible, which is the
  strongest correctness evidence available in this project.
- **Delivery milestones AND review scores on the same order** — this is what makes
  Business Case 3 answerable end to end: we can connect an operational metric
  (lateness) to a customer outcome (review score) to money (revenue exposed), which
  is exactly the chain an executive audience responds to.
- **Geography on both sides of every shipment** — customer state and seller state,
  so "where" has an origin and a destination rather than just a destination.
- **~1.55M rows / ~120 MB** — large enough to be real, small enough that a cluster
  would be indefensible. That lets us spend the effort budget on quality and
  reproducibility instead of on infrastructure.

## Alternatives rejected

**Instacart.** ~34M rows and excellent for basket and repurchase analysis. Rejected
because it has **no money columns at all** — no price, no revenue. That eliminates
every financial KPI, makes "monthly sales trends" (a brief requirement) impossible as
written, and removes the ability to convert any finding into a business impact. The
larger volume would have justified a Polars or Spark demonstration, but demonstrating
a tool is not worth losing the ability to answer the actual questions.

**London Bicycles.** Clean spatiotemporal story and a legitimate EU-region exercise.
Rejected for two reasons: it has **no customer entity**, which makes the brief's
mandatory "customer segmentation by purchase behaviour" analysis impossible; and it
would force every resource in the project into an EU location, cutting us off from
US-hosted public datasets for any enrichment.

## Consequences

- We inherit Olist's four documented data traps (payment fan-out, review fan-out,
  per-order customer IDs, geolocation cardinality). Each is handled explicitly and
  tested — see [ADR-004](004-order-grain-and-fanout.md).
- Data is a static historical export (Sep 2016 – Oct 2018). There is no genuine
  freshness dimension and no real SCD Type 2 history. We state this rather than
  simulating it.
- Licence is CC BY-NC-SA 4.0, non-commercial. Fine for coursework; recorded in the
  data dictionary.

## Revisit if

A brief revision requires streaming or a dataset large enough that single-node and
BigQuery-native processing stops being sufficient.
