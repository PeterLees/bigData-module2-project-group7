/*
    The customer_id to customer_unique_id bridge.

    customer_id is issued PER ORDER. customer_unique_id is the person. Every
    customer-level analysis must group on customer_unique_id, or one repeat
    buyer is counted as several one-time buyers and RFM segmentation collapses.
*/

with source as (

    select * from {{ source('olist_raw', 'customers') }}

),

renamed as (

    select
        customer_id,
        customer_unique_id           as customer_key,

        customer_zip_code_prefix,
        initcap(trim(customer_city)) as customer_city,
        upper(trim(customer_state))  as customer_state,
        {{ br_region('customer_state') }}                              as customer_region,

        _batch_id,
        _loaded_at

    from source
    where customer_id is not null

)

select * from renamed
