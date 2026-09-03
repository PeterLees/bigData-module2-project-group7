/*
    Grain: ONE ROW PER PAYMENT RECORD (order_id + payment_sequential).

    Kept as a separate fact table on purpose. Payments and order items are two
    independent many-to-one relationships with the order, so putting them in
    one table would create a many-to-many join and multiply money by the
    product of both counts. Anyone needing payment totals per order should use
    order_payment_total on fct_orders, which is already aggregated safely.
*/

{{
    config(
        materialized='table',
        cluster_by=['payment_type', 'order_id']
    )
}}

with payments as (

    select * from {{ ref('stg_order_payments') }}

),

orders as (

    select
        order_id,
        order_status,
        order_purchase_date
    from {{ ref('stg_orders') }}

)

select
    p.payment_key,
    p.order_id            as order_key,
    p.order_id,
    p.payment_sequential,

    o.order_purchase_date as order_date_key,
    o.order_status,

    p.payment_type,
    p.payment_installments,
    p.payment_value

from payments as p
left join orders as o using (order_id)
