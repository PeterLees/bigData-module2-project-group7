/*
    Collapse ~1,000,163 geolocation points to ONE ROW PER ZIP-CODE PREFIX.

    This is a fan-out control, not a convenience. The source has many rows per
    prefix; joining it directly to customers or sellers multiplies the row count
    by an unpredictable factor and quietly corrupts every count and sum
    downstream.

    Coordinates use the median (via APPROX_QUANTILES) rather than the mean so
    that a handful of mis-geocoded points cannot drag a prefix into the ocean.
    City and state use the modal value, since a prefix occasionally carries
    spelling variants of the same city.
*/

with source as (

    select * from {{ source('olist_raw', 'geolocation') }}
    where geolocation_zip_code_prefix is not null

),

coordinates as (

    select
        geolocation_zip_code_prefix                     as zip_code_prefix,
        approx_quantiles(geolocation_lat, 2)[offset(1)] as latitude,
        approx_quantiles(geolocation_lng, 2)[offset(1)] as longitude,
        count(*)                                        as geolocation_point_count
    from source
    group by 1

),

modal_place as (

    select
        geolocation_zip_code_prefix     as zip_code_prefix,
        initcap(trim(geolocation_city)) as city,
        upper(trim(geolocation_state))  as state
    from source
    group by 1, 2, 3
    -- QUALIFY is evaluated after SELECT, so it must reference the grouped
    -- aliases. The raw source columns no longer exist at this point:
    -- "references column geolocation_city which is neither grouped nor aggregated".
    qualify row_number() over (
            partition by zip_code_prefix
            order by count(*) desc, city
        ) = 1

)

select
    c.zip_code_prefix,
    c.latitude,
    c.longitude,
    c.geolocation_point_count,
    m.city  as geolocation_city,
    m.state as geolocation_state
from coordinates as c
left join modal_place as m using (zip_code_prefix)
