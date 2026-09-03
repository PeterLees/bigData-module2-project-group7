/*
    FAN-OUT CONTROL 4 of 4: one row per PERSON, not per order.

    Grain: one row per customer_unique_id.

    Olist issues a fresh customer_id for every order, so the naive dimension
    (one row per customer_id) makes every customer look like a one-time buyer
    and destroys RFM segmentation entirely. source_customer_id_count is carried
    through as direct evidence of how much collapsing actually happened.

    Geography is taken from the customer's MOST RECENT order, since that is
    where they would be delivered to today. SCD Type 1: Olist is a static
    export, so there is no genuine history to preserve, and we say so rather
    than manufacturing Type 2 versions that would all share one valid_from.
*/

with customers as (

    select * from {{ ref('stg_customers') }}

),

orders as (

    select
        customer_id,
        order_purchase_date
    from {{ ref('stg_orders') }}

),

customer_orders as (

    select
        c.customer_key,
        c.customer_id,
        c.customer_zip_code_prefix,
        c.customer_city,
        c.customer_state,
        c.customer_region,
        o.order_purchase_date
    from customers as c
    left join orders as o using (customer_id)

),

latest_attributes as (

    select
        customer_key,
        customer_zip_code_prefix,
        customer_city,
        customer_state,
        customer_region
    from customer_orders
    qualify row_number() over (
            partition by customer_key
            order by order_purchase_date desc nulls last, customer_id asc
        ) = 1

),

activity as (

    select
        customer_key,
        count(distinct customer_id) as source_customer_id_count,
        min(order_purchase_date)    as first_order_date,
        max(order_purchase_date)    as latest_order_date
    from customer_orders
    group by customer_key

),

geo as (

    select
        zip_code_prefix,
        latitude,
        longitude
    from {{ ref('stg_geolocation') }}

)

select
    a.customer_key,

    l.customer_city,
    l.customer_state,
    l.customer_region,
    l.customer_zip_code_prefix,

    g.latitude                     as customer_latitude,
    g.longitude                    as customer_longitude,

    a.first_order_date,
    a.latest_order_date,
    a.source_customer_id_count,
    a.source_customer_id_count > 1 as is_repeat_customer

from activity as a
left join latest_attributes as l using (customer_key)
left join geo as g on l.customer_zip_code_prefix = g.zip_code_prefix
