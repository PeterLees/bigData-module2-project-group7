/*
    PRIMARY FACT TABLE for the delivery-performance business case.

    Grain: ONE ROW PER ORDER, modelled as an accumulating snapshot across the
    delivery milestone chain.

    Why order grain rather than item grain: lateness is a property of a
    shipment, not of a line within it. Averaging delay across item lines would
    silently weight multi-item orders more heavily and skew every regional
    figure. Revenue therefore arrives here pre-aggregated from
    int_order_items_rollup, and is reconciled back to staging by a singular
    test so the aggregation cannot drift.

    Every input is already at order grain before it is joined:
        int_order_delivery      one row per order
        int_order_items_rollup  one row per order   (fan-out control)
        int_order_payments      one row per order   (fan-out control)
        int_order_reviews       one row per order   (fan-out control)
    That is what makes these four LEFT JOINs safe.

    Partitioned by order_purchase_date and clustered on the three columns the
    delivery analysis filters and groups by most.
*/

{{
    config(
        materialized='table',
        partition_by={
            'field': 'order_purchase_date',
            'data_type': 'date',
            'granularity': 'month'
        },
        cluster_by=['customer_state', 'seller_state', 'order_status']
    )
}}

with delivery as (

    select * from {{ ref('int_order_delivery') }}

),

items as (

    select * from {{ ref('int_order_items_rollup') }}

),

payments as (

    select * from {{ ref('int_order_payments') }}

),

reviews as (

    select * from {{ ref('int_order_reviews') }}

),

customers as (

    select
        customer_id,
        customer_key
    from {{ ref('stg_customers') }}

),

customer_geo as (

    select
        customer_key,
        customer_state,
        customer_region,
        customer_city
    from {{ ref('dim_customer') }}

),

seller_geo as (

    select
        seller_key,
        seller_state,
        seller_region,
        seller_city
    from {{ ref('dim_seller') }}

),

orders as (

    select
        order_id,
        customer_id
    from {{ ref('stg_orders') }}

),

joined as (

    select
        -- ---------------- keys ----------------
        d.order_id                                                          as order_key,
        d.order_id,
        c.customer_key,
        i.primary_seller_key                                                as seller_key,
        d.order_purchase_date                                               as order_date_key,

        -- ---------------- degenerate attributes ----------------
        o.customer_id                                                       as source_customer_id,
        d.order_status,
        d.is_delivered,
        d.is_excluded_from_kpis,

        -- ---------------- route geography (the WHERE) ----------------
        cg.customer_state,
        cg.customer_region,
        cg.customer_city,
        sg.seller_state,
        sg.seller_region,
        sg.seller_city,
        concat(
            coalesce(sg.seller_state, '??'), ' -> ', coalesce(cg.customer_state, '??')
        )                                                                   as delivery_route,
        coalesce(sg.seller_state, '??') = coalesce(cg.customer_state, '??')
            as is_intra_state_route,

        -- ---------------- milestones (the WHEN) ----------------
        d.order_purchased_at,
        d.order_approved_at,
        d.order_handed_to_carrier_at,
        d.order_delivered_at,
        d.order_promised_at,
        d.order_purchase_date,
        d.order_delivered_date,
        d.order_promised_date,

        -- ---------------- delivery measures ----------------
        d.approval_days,
        d.seller_handover_days,
        d.carrier_transit_days,
        d.total_delivery_days,
        d.promised_delivery_days,
        d.delay_vs_promise_days,
        d.promise_slack_days,
        d.is_late,
        d.lateness_bucket,

        -- ---------------- money measures ----------------
        i.order_item_count,
        i.order_product_count,
        i.order_seller_count,
        i.is_multi_seller_order,
        i.order_revenue,
        i.order_freight,
        i.order_gross_value,
        i.order_shipping_limit_at,

        p.order_payment_total,
        p.payment_record_count,
        p.primary_payment_type,
        p.payment_type_mix,
        p.max_payment_installments,

        -- ---------------- experience measure (the COST) ----------------
        r.review_id,
        r.review_score,
        r.has_comment                                                       as review_has_comment,
        r.source_review_count

    from delivery as d
    left join orders as o using (order_id)
    left join customers as c on o.customer_id = c.customer_id
    left join customer_geo as cg using (customer_key)
    left join items as i using (order_id)
    left join seller_geo as sg on i.primary_seller_key = sg.seller_key
    left join payments as p using (order_id)
    left join reviews as r using (order_id)

),

final as (

    select
        *,

        -- Freight as a share of what the customer paid. A high freight burden
        -- on a late route is a double penalty and a strong candidate for
        -- renegotiation, so it is precomputed here for the route aggregate.
        case
            when order_gross_value > 0
                then round(safe_divide(order_freight, order_gross_value), 4)
        end                                      as freight_share_of_order,

        -- Revenue that is actually at risk from a late delivery: nulls out for
        -- orders that were on time, so a plain SUM answers "how much revenue
        -- did we deliver late?" without a CASE in every query.
        case when is_late then order_revenue end as late_order_revenue

    from joined

)

select * from final
