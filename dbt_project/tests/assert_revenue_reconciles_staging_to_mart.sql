/*
    THE MOST IMPORTANT TEST IN THE PROJECT.

    Total revenue in the mart must equal total revenue in staging, to the cent.

    This is what proves that no join anywhere in the DAG multiplied money. If a
    future change joins payments to items, or reviews to orders, without
    aggregating first, this test fails immediately and the marts do not publish.
    Without it, an inflated revenue figure is completely plausible and could
    survive all the way into the executive deck.

    Compared at NUMERIC precision, so it is an exact equality, not an
    approximate one.

    Severity: error.
*/

with staging_total as (

    select sum(item_price) as revenue
    from {{ ref('stg_order_items') }}

),

fact_item_total as (

    select sum(item_price) as revenue
    from {{ ref('fct_order_items') }}

),

fact_order_total as (

    select sum(order_revenue) as revenue
    from {{ ref('fct_orders') }}

)

select
    'stg_order_items vs fct_order_items' as comparison,
    s.revenue                            as staging_revenue,
    i.revenue                            as mart_revenue,
    i.revenue - s.revenue                as difference
from staging_total as s
cross join fact_item_total as i
where s.revenue != i.revenue

union all

select
    'stg_order_items vs fct_orders' as comparison,
    s.revenue                       as staging_revenue,
    o.revenue                       as mart_revenue,
    o.revenue - s.revenue           as difference
from staging_total as s
cross join fact_order_total as o
where s.revenue != o.revenue
