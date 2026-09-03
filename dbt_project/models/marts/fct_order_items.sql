/*
    Grain: ONE ROW PER ITEM LINE within an order.

    This is the revenue backbone and the only correct grain for product and
    seller analysis. order_id alone is not unique here, which is precisely why
    the key is the composite order_item_key.

    No delivery measures live on this table. Lateness belongs to the shipment,
    so it is stored once on fct_orders; carrying it here as well would invite
    someone to average delay across item lines, which weights multi-item orders
    incorrectly. The order_key foreign key makes joining to fct_orders trivial
    when both are genuinely needed.
*/

{{
    config(
        materialized='table',
        partition_by={
            'field': 'order_purchase_date',
            'data_type': 'date',
            'granularity': 'month'
        },
        cluster_by=['product_key', 'seller_key', 'customer_key']
    )
}}

with items as (

    select * from {{ ref('stg_order_items') }}

),

orders as (

    select
        order_id,
        customer_id,
        order_status,
        order_purchase_date,
        is_delivered,
        is_excluded_from_kpis
    from {{ ref('stg_orders') }}

),

customers as (

    select
        customer_id,
        customer_key
    from {{ ref('stg_customers') }}

)

select
    -- ---------------- keys ----------------
    i.order_item_key,
    i.order_id            as order_key,
    i.order_id,
    i.order_item_id,
    i.product_key,
    i.seller_key,
    c.customer_key,
    o.order_purchase_date as order_date_key,

    -- ---------------- context ----------------
    o.order_status,
    o.is_delivered,
    o.is_excluded_from_kpis,
    o.order_purchase_date,
    i.shipping_limit_at,

    -- ---------------- measures ----------------
    i.item_price,
    i.freight_value,
    i.item_gross_value

from items as i
left join orders as o using (order_id)
left join customers as c on o.customer_id = c.customer_id
