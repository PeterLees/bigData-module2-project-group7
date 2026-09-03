# ADR-004: Order grain for delivery, item grain for revenue

**Status:** Accepted · **Date:** 2026-09-01 · **Owner:** Modeling Owner

## Context

This is the decision most likely to produce a confidently wrong number, and Olist has
four documented ways of causing exactly that. The profiling notebook quantifies each
one against this dataset rather than taking them on faith.

The primary business case is delivery performance, and lateness is a property of a
**shipment**, not of a line within it. But the brief also requires product-level
revenue analysis, which needs **item** grain. Those are two different grains, and
mixing them in one table is how revenue gets multiplied.

## Decision

Two fact tables at two declared grains, plus a third for payments:

| Table | Grain | Holds |
|---|---|---|
| `fct_orders` | one order (accumulating snapshot) | all delivery measures, order-level money, review score |
| `fct_order_items` | one item line | item revenue and freight; **no delivery measures** |
| `fct_payments` | one payment record | payment values only |

Four fan-out controls, each in a named `int_` model with a uniqueness test:

1. **`int_order_payments`** — payments aggregated to order grain before any join.
   The profiling notebook measures the row-count multiplier a naive join would cause.
2. **`int_order_reviews`** — deduplicated to one review per order, keeping the most
   recent by creation date with `review_id` as a deterministic tie-break.
3. **`dim_customer` keys on `customer_unique_id`** — Olist issues a fresh
   `customer_id` per order, so keying on it makes every customer a one-time buyer.
4. **`stg_geolocation`** — ~1M rows collapsed to one row per zip prefix, using the
   median coordinate and the modal city, before it enriches any dimension.

For route attribution, each order is assigned a **primary seller** (the one
contributing the most revenue), so a route is 1:1 with an order and route-level counts
and sums reconcile to the totals exactly.

## Rationale

Putting delivery measures on `fct_order_items` would let someone average delay across
item lines, which weights multi-item orders more heavily and skews every regional
figure. Keeping them on `fct_orders` makes that impossible.

The choice is enforced, not merely documented:

- `assert_revenue_reconciles_staging_to_mart.sql` asserts total mart revenue equals
  total staging revenue **exactly**, at NUMERIC precision. Any future join that fans
  out fails this immediately and the marts do not publish.
- `assert_order_count_reconciles.sql` asserts `fct_orders` has exactly one row per
  staging order.
- `assert_no_payment_fanout.sql` asserts per-order payment totals match staging.
- `assert_rfm_uses_person_grain.sql` fails if the RFM row count stops matching
  `dim_customer`, or if no customer has frequency above 1 — the signature of someone
  having reverted to `customer_id`.

## Alternatives rejected

**One wide fact table.** Simpler to query, but combining item lines with payment
records is a many-to-many join that multiplies money by the product of both counts.

**Attributing multi-seller orders to every seller.** More faithful for seller-level
analysis, but it double-counts orders and revenue in route aggregates, so route
figures would no longer sum to the totals. The primary-seller rule is documented and
`is_multi_seller_order` is carried through so any analysis that needs the stricter
treatment can exclude them.

**Surrogate keys.** Olist's natural keys are already opaque 32-character hashes and
are stable within the export. Adding surrogate keys would be machinery with no benefit
here. The one substantive renaming — `customer_unique_id` becoming `customer_key` —
exists because it changes the grain, not because it changes the key format.

## Consequences

- `delivered_orders` in `agg_product_performance` sums to more than the total order
  count, because an order spanning two categories counts in both. Documented in the
  model and in the model's description.
- Any analysis needing both delivery and item detail joins the two facts on
  `order_key`, which is deliberate friction: it forces the analyst to think about
  which grain the answer belongs at.
