# Data Dictionary

## Source

| Field | Value |
|---|---|
| Dataset | Brazilian E-Commerce Public Dataset by Olist |
| URL | <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce> |
| Licence | CC BY-NC-SA 4.0 (non-commercial — coursework use only) |
| Coverage | September 2016 – October 2018 |
| Analytical snapshot date | 2018-10-17 |
| Files | 9 CSV, ~120 MB unzipped, 1,550,922 rows |
| Download date | *record when Step C is performed* |
| Currency | Brazilian Real (R$) |
| Timestamps | Naive local time in the source; loaded as UTC TIMESTAMP. No timezone conversion is applied, and none of the analyses depend on absolute time zone — only on differences between timestamps within the same order. |

---

## Raw layer — `olist_raw`

Source columns are preserved **exactly**, including the two misspellings, so a defect
stays reproducible after it has been corrected downstream. Every table additionally
carries `_batch_id`, `_loaded_at`, `_source_uri` and `_source_sha256`.

### `orders` — 99,441 rows

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `order_id` | STRING | no | Natural key, 32-char hash |
| `customer_id` | STRING | no | **Per-order** identifier, not a person |
| `order_status` | STRING | no | One of 8: delivered, shipped, canceled, unavailable, invoiced, processing, created, approved |
| `order_purchase_timestamp` | TIMESTAMP | no | Event time for all trend analysis |
| `order_approved_at` | TIMESTAMP | yes | Payment approval. Null for unapproved orders |
| `order_delivered_carrier_date` | TIMESTAMP | yes | Handed to the carrier. Null before shipment |
| `order_delivered_customer_date` | TIMESTAMP | yes | **Delivered to the customer.** Null unless delivered |
| `order_estimated_delivery_date` | TIMESTAMP | yes | The date promised at purchase. The benchmark for lateness |

### `order_items` — 112,650 rows

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `order_id` | STRING | no | FK to orders |
| `order_item_id` | INT64 | no | Line sequence within the order, from 1. **Not globally unique** |
| `product_id` | STRING | no | FK to products |
| `seller_id` | STRING | no | FK to sellers |
| `shipping_limit_date` | TIMESTAMP | yes | Seller's shipping deadline |
| `price` | NUMERIC | no | Merchandise value of the line |
| `freight_value` | NUMERIC | no | Shipping cost of the line |

### `order_payments` — 103,886 rows

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `order_id` | STRING | no | FK to orders. **One order may have many payment rows** |
| `payment_sequential` | INT64 | no | Payment sequence within the order |
| `payment_type` | STRING | no | credit_card, boleto, voucher, debit_card, not_defined |
| `payment_installments` | INT64 | yes | Number of installments |
| `payment_value` | NUMERIC | yes | Value of this payment record |

### `order_reviews` — 99,224 rows

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `review_id` | STRING | no | **Not unique in the source** |
| `order_id` | STRING | no | FK to orders. Some orders have several reviews |
| `review_score` | INT64 | no | 1–5. The satisfaction measure |
| `review_comment_title` | STRING | yes | Free text |
| `review_comment_message` | STRING | yes | Free text, **contains newlines inside quoted fields** |
| `review_creation_date` | TIMESTAMP | yes | Used as the dedup ordering key |
| `review_answer_timestamp` | TIMESTAMP | yes | |

### `customers` — 99,441 rows

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `customer_id` | STRING | no | Unique here, but issued **per order** |
| `customer_unique_id` | STRING | no | **The person.** The correct grain for customer analysis |
| `customer_zip_code_prefix` | INT64 | yes | First 5 digits of the postcode |
| `customer_city` | STRING | yes | |
| `customer_state` | STRING | no | Two-letter code. The **destination** of a delivery route |

### `products` — 32,951 rows

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `product_id` | STRING | no | Natural key |
| `product_category_name` | STRING | yes | Portuguese |
| `product_name_lenght` | INT64 | yes | **Source misspelling.** Corrected in staging |
| `product_description_lenght` | INT64 | yes | **Source misspelling.** Corrected in staging |
| `product_photos_qty` | INT64 | yes | |
| `product_weight_g` | INT64 | yes | Plausible driver of transit time |
| `product_length_cm` / `height` / `width` | INT64 | yes | Plausible drivers of transit time |

### `sellers` — 3,095 rows

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `seller_id` | STRING | no | Natural key |
| `seller_zip_code_prefix` | INT64 | yes | |
| `seller_city` | STRING | yes | |
| `seller_state` | STRING | no | Two-letter code. The **origin** of a delivery route |

### `geolocation` — 1,000,163 rows

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `geolocation_zip_code_prefix` | INT64 | no | **Many rows per prefix.** Must be collapsed before any join |
| `geolocation_lat` / `lng` | FLOAT64 | yes | Coordinates |
| `geolocation_city` / `state` | STRING | yes | Spelling varies within a prefix |

### `product_category_translation` — 71 rows

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `product_category_name` | STRING | no | Portuguese |
| `product_category_name_english` | STRING | no | English |

---

## Marts layer — `olist_marts`

Full column-level documentation is generated from
`dbt_project/models/marts/_olist__marts.yml` by `dbt docs generate`. Summary:

| Model | Grain | Primary key | Owner |
|---|---|---|---|
| `fct_orders` | one order (accumulating snapshot) | `order_key` | Modeling |
| `fct_order_items` | one item line | `order_item_key` | Modeling |
| `fct_payments` | one payment record | `payment_key` | Modeling |
| `dim_customer` | one **person** | `customer_key` | Modeling |
| `dim_product` | one product | `product_key` | Modeling |
| `dim_seller` | one seller | `seller_key` | Modeling |
| `dim_date` | one calendar day | `date_key` | Modeling |
| `agg_delivery_by_route` | one seller-state → customer-state route | `delivery_route` | Analytics |
| `agg_delivery_monthly` | one purchase month | `year_month` | Analytics |
| `agg_monthly_sales` | one purchase month | `year_month` | Analytics |
| `agg_product_performance` | one product category | `product_category` | Analytics |
| `agg_customer_rfm` | one person | `customer_key` | Analytics |

---

## Known data issues and how each is handled

These are not incidental notes — each one changes a headline number if handled wrongly,
and each has a corresponding fan-out control and test. The profiling notebook
(`notebooks/01_profiling.ipynb`) quantifies every one of them against this dataset.

| # | Issue | Consequence if ignored | Handled by |
|---|---|---|---|
| 1 | An order can have several payment records | A payments-to-items join multiplies revenue | `int_order_payments` aggregates to order grain; `assert_no_payment_fanout` |
| 2 | `review_id` is not unique; some orders have several reviews | Orders duplicate, taking their revenue and delivery measures with them | `int_order_reviews` keeps the most recent per order; unique test on `order_id` |
| 3 | `customer_id` is issued per order | Every customer looks like a one-time buyer; RFM is destroyed | `dim_customer` keys on `customer_unique_id`; `assert_rfm_uses_person_grain` |
| 4 | ~1M geolocation rows, many per zip prefix | Joining it raw multiplies the row count unpredictably | `stg_geolocation` collapses to one row per prefix (median coordinate, modal city) |
| 5 | Review comments contain newlines inside quoted fields | `wc -l` overcounts; BigQuery CSV load fails without `allow_quoted_newlines` | `count_data_rows()` uses the csv module; load config sets `allow_quoted_newlines=True`; both unit-tested |
| 6 | Delivery timestamps are null for non-delivered orders | Counting them as on-time understates the late rate | `is_late` is NULL, not false; `assert_delivered_orders_have_delivery_date` |
| 7 | Some milestone timestamps are out of chronological order | Every derived duration is wrong | `assert_delivery_milestones_in_order` at error severity |
| 8 | Vouchers reduce the amount actually charged | Payment total legitimately differs from revenue + freight | Tested at **warn** severity, vouchers excluded from the check, reported openly |
| 9 | First and last months are sparse | A trend chart reads as a demand collapse | `is_in_analysis_window` on `dim_date`; charts trim or annotate and show what was excluded |
| 10 | `product_name_lenght` / `product_description_lenght` misspelled | Everyone downstream has to remember the typo | Corrected once in `stg_products`; raw keeps the original |
| 11 | An order can span several sellers | Route attribution would double-count orders | Primary seller (largest revenue share) used; `is_multi_seller_order` carried through |
| 12 | Some products have no category or no translation | Silent nulls in category reporting | Bucketed as `'unknown'` rather than dropped; `not_null` test on `product_category` |
| 13 | **29 mis-geocoded points** in `olist_geolocation` (0.0029% of 1,000,163) carry Brazilian city and state names but coordinates in Spain, Mexico, Italy, the Philippines and Argentina. Data extent runs to lat 45.07 / lng 121.11. | A mean coordinate per zip prefix would be dragged out of the country | `stg_geolocation` uses the **median** per prefix, so a handful of outliers cannot move it. Quality Gate 1 checks the Brazil bounding box at `mostly=0.999`, which still catches a wrong-country export or swapped lat/lng columns while tolerating the known noise. **Found by Gate 1 on the first real run.** |


---

## First real BigQuery run - findings and dispositions

The first end-to-end run against BigQuery produced **PASS=182, WARN=5, ERROR=0**
across 187 nodes. Revenue reconciled exactly: staging, `fct_order_items` and
`fct_orders` all report **13,591,643.70**, and order counts match at **99,441**.

Two defects were found in the code and fixed:

| Defect | Symptom | Fix |
|---|---|---|
| `stg_geolocation` window referenced un-grouped columns | `Window ORDER BY expression references column geolocation_city which is neither grouped nor aggregated` | QUALIFY is evaluated after SELECT, so it must reference the grouped aliases, not the raw source columns |
| `assert_rfm_uses_person_grain` compared against the wrong denominator | Failed on 96,096 vs 94,990 | RFM legitimately excludes the 1,106 people whose only orders were canceled. The test now compares against people holding a kept order, and additionally asserts the row count stays below the distinct `customer_id` count |

The five remaining warnings are **documented source characteristics**, each
deliberately at warn severity rather than error:

| Warning | Count | Disposition |
|---|---|---|
| `assert_milestone_recording_order` | 1,382 (1.37% of orders) | Carrier handover recorded before payment approval (1,359, median gap 21h, p95 ~4 days) and delivered before carrier handover (23). Asynchronous event recording, not corruption: a boleto settles in 1-3 business days so a seller can ship before the approval row is written. **Headline metrics unaffected** - `total_delivery_days` and `delay_vs_promise_days` both measure from `order_purchased_at`, which is never out of order. Only the stage decomposition is affected, where `seller_handover_days` goes negative for those orders. |
| `assert_payment_total_matches_order_value` | 296 | Voucher payments reduce the amount charged, so payment total legitimately differs from merchandise + freight. |
| `assert_delivered_orders_have_delivery_date` | 14 | 8 orders with status `delivered` but no delivery timestamp (they carry `is_late = NULL` and are therefore already excluded from the late-rate denominator by design), plus 6 `canceled` orders that do have one - delivered then refunded. |
| `stg_geolocation` latitude range | 5 prefixes | The mis-geocoded points of data issue 13 surviving the median collapse. |
| `stg_geolocation` longitude range | 6 prefixes | Same. |

### First measured business numbers

| Metric | Value |
|---|---|
| Delivered orders in scope | 96,470 |
| **Late-delivery rate** | **6.77%** |
| Median delivery time | 10.2 days |
| 90th percentile | 23.1 days |
| Mean review score, on time | **4.29 stars** |
| Mean review score, late | **2.27 stars** |
| Satisfaction penalty | **-2.02 stars** |
| Revenue delivered late | R$ 985,924 |

The delivery-to-satisfaction link the whole project was designed around is real
and large: a late delivery costs roughly two full stars.
