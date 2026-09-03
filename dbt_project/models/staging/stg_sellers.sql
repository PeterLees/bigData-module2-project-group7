/*
    One row per seller. seller_state is the ORIGIN half of a delivery route,
    which makes it a first-class attribute for the delivery business case
    rather than an incidental descriptor.
*/

with source as (

    select * from {{ source('olist_raw', 'sellers') }}

),

renamed as (

    select
        seller_id                  as seller_key,

        seller_zip_code_prefix,
        initcap(trim(seller_city)) as seller_city,
        upper(trim(seller_state))  as seller_state,
        {{ br_region('seller_state') }}                            as seller_region,

        _batch_id,
        _loaded_at

    from source
    where seller_id is not null

)

select * from renamed
