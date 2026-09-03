/*
    Grain: one row per seller.

    seller_state and seller_region are first-class attributes here, not
    descriptive filler: the origin of a shipment is half of a delivery route,
    and nearly all Olist sellers sit in the Southeast, which is the structural
    reason distant regions receive orders late.
*/

with sellers as (

    select * from {{ ref('stg_sellers') }}

),

geo as (

    select
        zip_code_prefix,
        latitude,
        longitude
    from {{ ref('stg_geolocation') }}

)

select
    s.seller_key,
    s.seller_city,
    s.seller_state,
    s.seller_region,
    s.seller_zip_code_prefix,

    g.latitude  as seller_latitude,
    g.longitude as seller_longitude

from sellers as s
left join geo as g on s.seller_zip_code_prefix = g.zip_code_prefix
