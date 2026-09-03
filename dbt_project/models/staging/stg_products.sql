/*
    One row per product, with the English category name attached.

    The source misspellings (product_name_lenght, product_description_lenght)
    are corrected here and only here: raw keeps them so the export stays
    byte-reproducible, and nothing downstream ever has to remember them.

    Physical dimensions are kept because size and weight are plausible drivers
    of transit time, which the delivery business case needs to control for.
*/

with products as (

    select * from {{ source('olist_raw', 'products') }}

),

translation as (

    select * from {{ source('olist_raw', 'product_category_translation') }}

),

renamed as (

    select
        p.product_id                                                   as product_key,

        lower(trim(p.product_category_name))                           as product_category_pt,
        coalesce(
            lower(trim(t.product_category_name_english)),
            'unknown'
        )                                                              as product_category,

        p.product_name_lenght                                          as product_name_length,
        p.product_description_lenght                                   as product_description_length,
        p.product_photos_qty                                           as product_photo_count,

        p.product_weight_g,
        p.product_length_cm,
        p.product_height_cm,
        p.product_width_cm,

        -- volumetric size, a better predictor of shipping difficulty than weight alone
        p.product_length_cm * p.product_height_cm * p.product_width_cm
            as product_volume_cm3,

        p._batch_id,
        p._loaded_at

    from products as p
    left join translation as t
        on lower(trim(p.product_category_name)) = lower(trim(t.product_category_name))
    where p.product_id is not null

)

select * from renamed
