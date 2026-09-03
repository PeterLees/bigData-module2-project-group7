/*
    Grain: one row per product.

    Physical attributes are retained because product size and weight are
    plausible confounders for transit time: a heavy or bulky category may look
    like a logistics failure when it is really a product-mix effect. The
    delivery analysis controls for category before drawing conclusions.
*/

with products as (

    select * from {{ ref('stg_products') }}

)

select
    product_key,

    product_category,
    product_category_pt,

    product_weight_g,
    product_length_cm,
    product_height_cm,
    product_width_cm,
    product_volume_cm3,

    -- coarse size banding, so charts can control for bulk without a scatter plot
    case
        when product_weight_g is null then 'Unknown'
        when product_weight_g < 500 then '1. Light (<0.5kg)'
        when product_weight_g < 2000 then '2. Medium (0.5-2kg)'
        when product_weight_g < 10000 then '3. Heavy (2-10kg)'
        else '4. Very heavy (10kg+)'
    end as product_weight_band,

    product_photo_count,
    product_name_length,
    product_description_length

from products
