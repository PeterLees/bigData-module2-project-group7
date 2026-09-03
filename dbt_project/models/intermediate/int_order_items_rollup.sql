/*
    FAN-OUT CONTROL 3 of 4.

    Rolls item lines up to ONE ROW PER ORDER, carrying the money measures and
    the primary seller.

    Why a "primary seller": an order can contain items from several sellers, so
    a delivery route (seller state -> customer state) is not naturally 1:1 with
    an order. Attributing the order to the seller contributing the most revenue
    keeps fct_orders at one row per order, so route-level order counts and
    revenue sums add up to the totals exactly.

    The trade-off is documented rather than hidden: multi-seller orders are a
    small minority, and order_seller_count is carried through so any analysis
    can exclude them if it needs to.
*/

with items as (

    select * from {{ ref('stg_order_items') }}

),

sellers_by_value as (

    select
        order_id,
        seller_key,
        sum(item_price) as seller_revenue
    from items
    group by order_id, seller_key

),

primary_seller as (

    select
        order_id,
        seller_key as primary_seller_key
    from sellers_by_value
    qualify row_number() over (
            partition by order_id
            order by seller_revenue desc, seller_key asc
        ) = 1

),

order_rollup as (

    select
        order_id,

        count(*)                    as order_item_count,
        count(distinct product_key) as order_product_count,
        count(distinct seller_key)  as order_seller_count,

        sum(item_price)             as order_revenue,
        sum(freight_value)          as order_freight,
        sum(item_gross_value)       as order_gross_value,

        max(shipping_limit_at)      as order_shipping_limit_at

    from items
    group by order_id

)

select
    r.*,
    p.primary_seller_key,
    r.order_seller_count > 1 as is_multi_seller_order
from order_rollup as r
left join primary_seller as p using (order_id)
