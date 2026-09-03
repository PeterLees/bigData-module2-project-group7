/*
    BRIEF REQUIREMENT: monthly sales trends.

    Grain: one row per purchase month.

    Definitions, fixed here so no chart can quietly use a different one:
      revenue      = sum of item price. Freight is a SEPARATE column and is
                     never folded into revenue, because freight is a cost the
                     customer bears, not merchandise value.
      order_count  = count of distinct orders, taken from fct_orders where the
                     grain is already one row per order.
      exclusions   = the statuses in the excluded_order_statuses project var.

    Revenue comes from fct_order_items and order counts from fct_orders, each at
    its own natural grain and joined only after aggregation. Computing both from
    one joined query is exactly the mistake that inflates revenue by the item
    count, so the two are kept apart until they are both scalars per month.

    The late rate is joined in so that revenue and service quality can be read
    on one chart: the single most useful cross-read in this project.
*/

{{ config(materialized='table') }}

with items as (

    select *
    from {{ ref('fct_order_items') }}
    where not is_excluded_from_kpis

),

item_revenue as (

    select
        date_trunc(order_purchase_date, month) as month_start_date,
        sum(item_price)                        as revenue,
        sum(freight_value)                     as freight,
        sum(item_gross_value)                  as gross_value,
        count(*)                               as items_sold,
        count(distinct product_key)            as distinct_products_sold,
        count(distinct seller_key)             as active_sellers
    from items
    group by month_start_date

),

order_counts as (

    select
        date_trunc(order_purchase_date, month) as month_start_date,
        count(*)                               as order_count,
        count(distinct customer_key)           as active_customers
    from {{ ref('fct_orders') }}
    where not is_excluded_from_kpis
    group by month_start_date

),

delivery as (

    select
        month_start_date,
        late_rate,
        median_delivery_days,
        avg_review_score
    from {{ ref('agg_delivery_monthly') }}

),

calendar as (

    select distinct
        month_start_date,
        year_month,
        month_label,
        is_in_analysis_window
    from {{ ref('dim_date') }}

),

combined as (

    select
        c.year_month,
        c.month_label,
        c.month_start_date,
        c.is_in_analysis_window,

        r.revenue,
        r.freight,
        r.gross_value,
        r.items_sold,
        r.distinct_products_sold,
        r.active_sellers,

        o.order_count,
        o.active_customers,

        d.late_rate,
        d.median_delivery_days,
        d.avg_review_score

    from calendar as c
    inner join item_revenue as r using (month_start_date)
    left join order_counts as o using (month_start_date)
    left join delivery as d using (month_start_date)

)

select
    *,

    round(safe_divide(revenue, order_count), 2)                                       as avg_order_value,
    round(safe_divide(items_sold, order_count), 3)                                    as avg_items_per_order,
    round(safe_divide(freight, gross_value), 4)                                       as freight_share_of_gross,

    round(safe_divide(revenue, lag(revenue) over (order by month_start_date)) - 1, 4)
        as revenue_mom_growth

from combined
order by month_start_date
