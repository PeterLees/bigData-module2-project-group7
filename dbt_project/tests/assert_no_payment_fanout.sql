/*
    Guards the specific mistake this dataset is famous for.

    int_order_payments must produce exactly one row per order, and the payment
    total on fct_orders must equal the raw payment total for that order. If
    someone later replaces the aggregation with a direct join, the row count
    inflates and this test catches it before any revenue figure is published.

    Severity: error.
*/

with raw_payments as (

    select
        order_id,
        sum(payment_value) as payment_total
    from {{ ref('stg_order_payments') }}
    group by order_id

),

mart as (

    select
        order_id,
        order_payment_total
    from {{ ref('fct_orders') }}
    where order_payment_total is not null

)

select
    m.order_id,
    r.payment_total                         as staging_payment_total,
    m.order_payment_total                   as mart_payment_total,
    m.order_payment_total - r.payment_total as difference
from mart as m
inner join raw_payments as r using (order_id)
where m.order_payment_total != r.payment_total
