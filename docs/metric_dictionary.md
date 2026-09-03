# Metric Dictionary

Every KPI used in a notebook, the report or the deck is defined here, once. If a number
appears anywhere in this project, its definition is in this file and its
implementation is in a tested dbt model.

The rule: **no metric is redefined in a notebook.** If a figure cannot be produced from
the marts layer, the fix is a dbt model, not a pandas workaround — otherwise the
definition lives somewhere nobody tests.

Fixed parameters, set once in `dbt_project.yml` and referenced everywhere:

| Parameter | Value | Why it is fixed |
|---|---|---|
| `olist_snapshot_date` | `2018-10-17` | The analytical "today". Recency is measured against this, never `CURRENT_DATE` — the export ends in 2018, so using the real date would mark every customer dormant and make results change every day they are run. |
| `analysis_start_date` | `2016-09-01` | Start of usable coverage. |
| `analysis_end_date` | `2018-10-31` | End of usable coverage. |
| `excluded_order_statuses` | `canceled`, `unavailable` | Excluded from all revenue and delivery KPIs — these orders were never fulfilled. |
| `min_orders_for_reporting` | `30` | Volume floor for reporting a rate. A 100% late rate on three orders is noise. |

---

## 1. Delivery metrics — the primary business case

| Metric | Definition | Implemented in | Traps avoided |
|---|---|---|---|
| **Late rate** | `countif(is_late) / count(*)`, over **delivered orders only** | `agg_delivery_by_route`, `agg_delivery_monthly` | Including undelivered orders would understate the rate, because an order that never arrived has no lateness value. `is_late` is NULL, not false, for those. |
| **`is_late`** | `delay_vs_promise_days > 0`. NULL when the order was not delivered or has no promised date. | `int_order_delivery` | Never silently false. Tested against the measure it derives from by `assert_is_late_matches_delay`. |
| **`delay_vs_promise_days`** | `date_diff(date(delivered), date(promised), DAY)`. Negative means early. | `int_order_delivery` | Measured on **date** boundaries, not timestamps: the promise made to the customer is a date, so an order delivered at 23:00 on the promised day is on time. Using timestamps would manufacture lateness nobody experienced. |
| **`total_delivery_days`** | `timestamp_diff(delivered, purchased, HOUR) / 24`, fractional | `int_order_delivery` | Fractional so short stages are not rounded away. |
| **`approval_days`** | purchase → payment approval | `int_order_delivery` | Stage 1 of 3. Usually well under a day. |
| **`seller_handover_days`** | approval → carrier handover | `int_order_delivery` | Stage 2. The seller's own fulfilment time. |
| **`carrier_transit_days`** | carrier handover → customer delivery | `int_order_delivery` | Stage 3. The carrier's time. Kept separate because these three lead to three different recommendations. |
| **`promised_delivery_days`** | `date_diff(promised, purchased, DAY)` | `int_order_delivery` | What the customer was told at purchase. |
| **`promise_slack_days`** | `promised_delivery_days - total_delivery_days`. Positive means the promise was padded. | `int_order_delivery` | Deliberately **not** collapsed into the late flag. A systematically wrong estimate is cheap to fix; slow logistics is expensive. Conflating them hides the cheaper option. |
| **Median delivery days** | `approx_quantiles(total_delivery_days, 100)[offset(50)]` | aggregates | Median, not mean: a handful of 200-day outliers would otherwise define a state. |
| **p90 delivery days** | `approx_quantiles(...)[offset(90)]` | aggregates | Reported alongside the median because the tail is what customers complain about. |
| **Delivery route** | `seller_state -> customer_state` | `fct_orders` | Uses the **primary seller** (largest revenue contribution) so a route is 1:1 with an order and route totals reconcile. |
| **Revenue delivered late** | `sum(late_order_revenue)` where that column is `order_revenue` if late, else NULL | `fct_orders` | Precomputed so a plain SUM answers the question without a CASE in every query. |
| **Review score penalty when late** | `avg(review_score) when on time − avg(review_score) when late` | `agg_delivery_by_route`, `agg_delivery_monthly` | **Correlational.** Controlled for state and category in the notebook; seller quality and product mix are not controlled. Always presented with that caveat. |

---

## 2. Revenue metrics

| Metric | Definition | Implemented in | Traps avoided |
|---|---|---|---|
| **Revenue** | `sum(item_price)` — merchandise value only | `fct_order_items`, `agg_monthly_sales` | Freight is **never** folded in: it is a cost the customer bears, not merchandise value. It is always a separate column. |
| **Freight** | `sum(freight_value)` | same | Reported as its own series. |
| **Gross value** | `revenue + freight` | same | Used only for freight-share calculations. |
| **Order count** | `count(distinct order_id)`, taken from `fct_orders` where the grain is already one row per order | `agg_monthly_sales` | Counted at order grain and revenue at item grain, aggregated **separately** and joined only once both are scalars per month. Computing both in one joined query is exactly what multiplies revenue by the item count. |
| **Average order value** | `revenue / order_count` | `agg_monthly_sales` | Both inputs already reconciled. |
| **`order_payment_total`** | `sum(payment_value)` per order | `int_order_payments` | Aggregated to order grain **before** any join. A direct payments-to-items join inflates revenue by a factor the profiling notebook measures. |
| **Freight share** | `freight / (revenue + freight)` | `fct_orders`, aggregates | A high freight burden on a late route is a double penalty. |
| **Revenue MoM growth** | `revenue / lag(revenue) - 1` by month | `agg_monthly_sales` | Partial edge months are flagged by `is_in_analysis_window` and excluded from trend readings. |

**Reconciliation guarantee.** `sum(item_price)` in staging, in `fct_order_items` and in
`fct_orders` are asserted **exactly equal** at NUMERIC precision on every build by
`assert_revenue_reconciles_staging_to_mart`. If any join anywhere in the DAG fans out,
the build fails and marts do not publish.

---

## 3. Product metrics

| Metric | Definition | Implemented in | Traps avoided |
|---|---|---|---|
| **Units sold** | `count(*)` of item lines | `agg_product_performance` | Reported **with** revenue and order count, never alone. |
| **Category revenue rank** | `dense_rank()` over revenue | same | Ranking on revenue alone flatters high-price, low-volume categories. Volume rank is reported beside it, and the gap between the two ranks is itself a finding. |
| **Product category** | English name from the translation table; `'unknown'` where missing | `stg_products` | The source is Portuguese; the untranslated bucket is labelled rather than dropped. |
| **`is_high_value_poor_delivery`** | top-10 revenue category AND above-average late rate | `agg_product_performance` | The headline cross-read: where a logistics fix protects the most money. |
| **Category delivery metrics** | late rate and median days per category | same | Computed at **order** grain via distinct (order, category) pairs, because lateness is a property of the shipment. An order spanning two categories counts in both, so `delivered_orders` sums to more than the total order count — documented, and sales measures are unaffected. |

---

## 4. Customer metrics (RFM)

Grain is `customer_unique_id` — **the person**, never the per-order `customer_id`.

| Metric | Definition | Implemented in | Traps avoided |
|---|---|---|---|
| **Recency** | `date_diff(olist_snapshot_date, max(order_purchase_date), DAY)` | `agg_customer_rfm` | Against the snapshot date, never today. |
| **Frequency** | `count(*)` of orders, from `fct_orders` | same | Counted at order grain. Aggregating from item lines would count a three-item order as three purchases. |
| **Monetary** | `sum(order_revenue)` | same | Order revenue, already reconciled. |
| **R / F / M scores** | quintiles via `ntile(5)`; recency reversed so 5 is always best | same | |
| **RFM segment** | Champions · High value recent · At risk high value · New/promising · Dormant low value · Occasional | same | Frequency thresholds are set **low on purpose**: Olist's base is overwhelmingly single-purchase, and demanding `f_score >= 4` would leave Champions nearly empty and produce a segmentation nobody could act on. |
| **`is_high_value_with_late_delivery`** | `m_score >= 4 AND late_orders > 0` | same | The retention argument: the most expensive churn risk in the dataset. |

`assert_rfm_uses_person_grain` fails the build if the RFM row count stops matching
`dim_customer`, or if no customer has frequency above 1 — the signature of someone
having reverted to `customer_id`.

---

## 5. Known limitations, stated up front

| Limitation | Effect | How it is handled |
|---|---|---|
| Static export, Sep 2016 – Oct 2018 | No genuine freshness dimension; no real SCD Type 2 history | Snapshot date recorded; the product snapshot is described as a capability demonstration, not as captured history |
| Sparse first and last months | A naive trend chart looks like a demand collapse | `is_in_analysis_window` on `dim_date`; charts trim or annotate, and the excluded months are shown explicitly |
| Voucher payments | `order_payment_total` legitimately differs from `revenue + freight` | Tested at **warn** severity, excluded where a voucher is present, reported openly |
| Multi-seller orders | Route attribution uses the primary seller only | `is_multi_seller_order` carried through so any analysis can exclude them |
| Reviews are one per order after dedup | Loses secondary reviews | `source_review_count` retained so the loss is visible and quantifiable |
| No cost data | Margin cannot be computed; only revenue | Every recommendation is framed on revenue and satisfaction, never on profit |
| Correlation, not causation | Late delivery is *associated* with lower review scores | Labelled as a hypothesis; an A/B or quasi-experiment is proposed rather than a causal claim |
