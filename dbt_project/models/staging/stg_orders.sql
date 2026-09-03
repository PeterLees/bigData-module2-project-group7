/*
    One row per order, renamed and typed.

    Deliberately does NOT deduplicate on order_id. If duplicates ever appear we
    want the unique test to fail loudly rather than have a silent qualify clause
    hide a real ingestion problem.
*/

with source as (

    select * from {{ source('olist_raw', 'orders') }}

),

renamed as (

    select
        order_id,
        customer_id,
        lower(trim(order_status))            as order_status,

        -- milestone timestamps, in the order they occur
        order_purchase_timestamp             as order_purchased_at,
        order_approved_at,
        order_delivered_carrier_date         as order_handed_to_carrier_at,
        order_delivered_customer_date        as order_delivered_at,
        order_estimated_delivery_date        as order_promised_at,

        -- date grains used for partitioning and joining to dim_date
        date(order_purchase_timestamp)       as order_purchase_date,
        date(order_delivered_customer_date)  as order_delivered_date,
        date(order_estimated_delivery_date)  as order_promised_date,

        -- convenience flags, defined once here rather than in every consumer
        order_status = 'delivered'           as is_delivered,
        order_status in {{ excluded_statuses() }} as is_excluded_from_kpis,

        _batch_id,
        _loaded_at

    from source
    where order_id is not null

)

select * from renamed
