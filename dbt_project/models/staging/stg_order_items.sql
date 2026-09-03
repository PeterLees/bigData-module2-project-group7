/*
    One row per item line within an order. This is the revenue backbone.

    price and freight_value are cast to NUMERIC so that money arithmetic is
    exact; FLOAT64 would introduce rounding that breaks the source-to-mart
    reconciliation test by fractions of a cent.
*/

with source as (

    select * from {{ source('olist_raw', 'order_items') }}

),

renamed as (

    select
        -- composite key: order_id alone is not unique at item grain
        concat(order_id, '-', cast(order_item_id as string))    as order_item_key,

        order_id,
        order_item_id,
        product_id                                              as product_key,
        seller_id                                               as seller_key,

        shipping_limit_date                                     as shipping_limit_at,

        cast(price as numeric)                                  as item_price,
        cast(freight_value as numeric)                          as freight_value,
        cast(price as numeric) + cast(freight_value as numeric) as item_gross_value,

        _batch_id,
        _loaded_at

    from source
    where order_id is not null
        and order_item_id is not null

)

select * from renamed
