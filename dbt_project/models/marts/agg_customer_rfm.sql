/*
    BRIEF REQUIREMENT: customer segmentation by purchase behaviour.

    Grain: one row per customer_unique_id (a PERSON, not an order).

    Three decisions that make or break this model:

    1. GRAIN. Segmentation runs on customer_unique_id. Olist issues a fresh
       customer_id per order, so segmenting on it makes every customer a
       one-time buyer and produces a frequency distribution of exactly 1.

    2. RECENCY BASELINE. Measured against the olist_snapshot_date project var,
       never CURRENT_DATE. The export ends in late 2018; measuring recency
       against today would make every single customer "dormant for 8 years" and
       render the R score meaningless. Fixing the baseline also makes the
       results reproducible forever.

    3. AGGREGATION ORDER. Orders are aggregated to the customer from fct_orders,
       which is already one row per order. Aggregating from item lines instead
       would count a three-item order as three purchases and inflate frequency.

    The delivery columns are the point of doing this in a delivery project: they
    quantify how much high-value customer revenue is exposed to late delivery,
    which turns a segmentation exercise into a retention argument.
*/

{{ config(materialized='table') }}

{% set snapshot_date = var('olist_snapshot_date') %}

with orders as (

    select *
    from {{ ref('fct_orders') }}
    where not is_excluded_from_kpis
        and customer_key is not null

),

customer_orders as (

    select
        customer_key,

        -- ---------------- RFM inputs ----------------
        date_diff(date('{{ snapshot_date }}'), max(order_purchase_date), day)
            as recency_days,
        count(*)                                                                  as frequency,
        sum(order_revenue)                                                        as monetary,

        min(order_purchase_date)                                                  as first_order_date,
        max(order_purchase_date)                                                  as latest_order_date,
        round(avg(order_revenue), 2)                                              as avg_order_value,
        sum(order_item_count)                                                     as total_items_purchased,

        -- ---------------- delivery experience ----------------
        countif(is_delivered)                                                     as delivered_orders,
        countif(is_late)                                                          as late_orders,
        round(safe_divide(countif(is_late), nullif(countif(is_delivered), 0)), 4)
            as late_rate,
        sum(late_order_revenue)                                                   as revenue_delivered_late,
        round(avg(total_delivery_days), 2)                                        as avg_delivery_days,
        round(avg(review_score), 3)                                               as avg_review_score

    from orders
    group by customer_key

),

scored as (

    select
        *,

        -- Quintiles across the customer base. Recency is reversed: fewer days
        -- since the last order is better, so 5 is the best score on all three.
        6 - ntile(5) over (order by recency_days asc)        as r_score,
        ntile(5) over (order by frequency asc, monetary asc) as f_score,
        ntile(5) over (order by monetary asc)                as m_score

    from customer_orders

),

segmented as (

    select
        *,
        concat(cast(r_score as string), cast(f_score as string), cast(m_score as string))
            as rfm_cell,
        r_score + f_score + m_score                                                       as rfm_total,

        /*
            Segment names are chosen so that each one implies a different
            action, which is what the insight cards require. Olist's population
            is overwhelmingly single-purchase, so the frequency thresholds are
            deliberately low: demanding f_score >= 4 would leave the
            "Champions" segment nearly empty and produce a segmentation nobody
            could act on.
        */
        case
            when r_score >= 4 and f_score >= 3 and m_score >= 4 then '1. Champions'
            when r_score >= 3 and m_score >= 4 then '2. High value, recent'
            when r_score <= 2 and m_score >= 4 then '3. At risk, high value'
            when r_score >= 4 and f_score <= 2 then '4. New / promising'
            when r_score <= 2 and m_score <= 2 then '5. Dormant, low value'
            else '6. Occasional'
        end                                                                               as rfm_segment

    from scored

)

select
    customer_key,

    recency_days,
    frequency,
    monetary,
    avg_order_value,
    total_items_purchased,

    first_order_date,
    latest_order_date,

    r_score,
    f_score,
    m_score,
    rfm_cell,
    rfm_total,
    rfm_segment,

    delivered_orders,
    late_orders,
    late_rate,
    revenue_delivered_late,
    avg_delivery_days,
    avg_review_score,

    -- The retention argument in one column: a high-value customer whose orders
    -- arrive late is the most expensive kind of churn risk in the dataset.
    m_score >= 4 and late_orders > 0 as is_high_value_with_late_delivery

from segmented
