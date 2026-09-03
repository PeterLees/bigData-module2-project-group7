/*
    BRIEF REQUIREMENT: top-selling products.

    Grain: one row per product category.

    Reported deliberately as revenue AND units AND distinct orders together.
    Ranking on revenue alone flatters high-price, low-volume categories and
    hides the categories that actually move volume; the course guidance names
    this as the standard mistake.

    The delivery columns are what make this more than a sales table. A category
    that sells well but ships badly is the highest-value intersection of the two
    analyses in this project, and it is invisible unless both live side by side.

    Note on the delivery join, because it is a real attribution decision:
    lateness is a property of an ORDER, so the delivery block first reduces item
    lines to distinct (order, category) pairs and then joins to fct_orders at
    order grain. An order spanning two categories therefore counts once in each,
    which is correct for a category diagnostic but means the delivered_orders
    column sums to more than the total order count. Sales measures above are
    unaffected: they aggregate item lines directly.

    Product-level detail is available from fct_order_items. This model rolls up
    to category because category is the level at which assortment and supplier
    decisions are actually made.
*/

{{ config(materialized='table') }}

with items as (

    select *
    from {{ ref('fct_order_items') }}
    where not is_excluded_from_kpis

),

products as (

    select
        product_key,
        product_category,
        product_weight_band
    from {{ ref('dim_product') }}

),

items_with_category as (

    select
        i.*,
        p.product_category,
        p.product_weight_band
    from items as i
    left join products as p using (product_key)

),

sales as (

    select
        product_category,

        sum(item_price)              as revenue,
        sum(freight_value)           as freight,
        count(*)                     as units_sold,
        count(distinct order_id)     as order_count,
        count(distinct product_key)  as distinct_products,
        count(distinct seller_key)   as distinct_sellers,
        count(distinct customer_key) as distinct_customers,

        round(avg(item_price), 2)    as avg_item_price,
        round(safe_divide(
            sum(freight_value),
            sum(item_price) + sum(freight_value)
        ), 4)
            as freight_share_of_gross

    from items_with_category
    group by product_category

),

order_category_pairs as (

    select distinct
        order_id,
        product_category
    from items_with_category

),

delivery as (

    select
        ocp.product_category,

        count(*)                                                           as delivered_orders,
        countif(o.is_late)                                                 as late_orders,
        round(safe_divide(countif(o.is_late), count(*)), 4)                as late_rate,

        round(approx_quantiles(o.total_delivery_days, 100)[offset(50)], 2)
            as median_delivery_days,
        round(approx_quantiles(o.total_delivery_days, 100)[offset(90)], 2)
            as p90_delivery_days,

        round(avg(o.review_score), 3)                                      as avg_review_score,
        round(avg(case when o.is_late then o.review_score end), 3)         as avg_review_score_when_late,
        round(avg(case when not o.is_late then o.review_score end), 3)     as avg_review_score_when_on_time

    from order_category_pairs as ocp
    inner join {{ ref('fct_orders') }} as o
        on ocp.order_id = o.order_id
    where o.is_delivered
        and o.delay_vs_promise_days is not null
    group by product_category

),

combined as (

    select
        s.*,

        d.delivered_orders,
        d.late_orders,
        d.late_rate,
        d.median_delivery_days,
        d.p90_delivery_days,
        d.avg_review_score,
        d.avg_review_score_when_late,
        d.avg_review_score_when_on_time,
        round(d.avg_review_score_when_on_time - d.avg_review_score_when_late, 3)
            as review_score_penalty_when_late

    from sales as s
    left join delivery as d using (product_category)

)

select
    *,

    round(safe_divide(revenue, sum(revenue) over ()), 4)  as revenue_share,
    dense_rank() over (order by revenue desc)             as revenue_rank,
    dense_rank() over (order by units_sold desc)          as volume_rank,

    -- The headline cross-read: high revenue, bad delivery. These are the
    -- categories where a logistics fix protects the most money.
    dense_rank() over (order by revenue desc) <= 10
    and late_rate > (select avg(late_rate) from delivery) as is_high_value_poor_delivery,

    order_count >= {{ var('min_orders_for_reporting') }}                                   as is_reportable

from combined
order by revenue desc
