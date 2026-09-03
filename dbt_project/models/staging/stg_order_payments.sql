/*
    One row per payment record.

    Left at payment grain on purpose. Aggregation to order grain happens exactly
    once, in int_order_payments, so that no consumer can accidentally join this
    to order items and multiply revenue by the item count.
*/

with source as (

    select * from {{ source('olist_raw', 'order_payments') }}

),

renamed as (

    select
        concat(order_id, '-', cast(payment_sequential as string)) as payment_key,

        order_id,
        payment_sequential,
        lower(trim(payment_type))                                 as payment_type,
        payment_installments,
        cast(payment_value as numeric)                            as payment_value,

        _batch_id,
        _loaded_at

    from source
    where order_id is not null
        and payment_sequential is not null

)

select * from renamed
