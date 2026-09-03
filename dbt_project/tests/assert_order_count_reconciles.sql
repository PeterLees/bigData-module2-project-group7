/*
    Every order in staging must appear exactly once in fct_orders, and
    fct_orders must not invent any.

    A shortfall means an unintended filter or a failed join dropped orders. A
    surplus means a join fanned out. Either way every rate computed from
    fct_orders is wrong, because the denominator moved.

    Severity: error.
*/

with staging as (

    select count(distinct order_id) as order_count
    from {{ ref('stg_orders') }}

),

mart as (

    select
        count(*)                 as row_count,
        count(distinct order_id) as order_count
    from {{ ref('fct_orders') }}

)

select
    s.order_count as staging_orders,
    m.order_count as mart_orders,
    m.row_count   as mart_rows,
    case
        when m.row_count != m.order_count then 'fct_orders is not at order grain'
        when m.order_count < s.order_count then 'orders were dropped'
        else 'orders were invented'
    end           as violation
from staging as s
cross join mart as m
where s.order_count != m.order_count
    or m.row_count != m.order_count
