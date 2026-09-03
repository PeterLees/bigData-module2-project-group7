/*
    ANSWERS: "WHERE are deliveries late?"

    Grain: one row per delivery route (seller_state -> customer_state).

    Because fct_orders carries a single primary seller per order, every order
    belongs to exactly one route, so order counts and revenue across routes sum
    back to the totals. Attributing multi-seller orders to every seller state
    involved would double-count them, which is why the primary-seller rule
    exists upstream.

    Only DELIVERED orders are counted. Including undelivered orders would
    understate the late rate, because an order that never arrived has no
    lateness value at all.

    Medians rather than means throughout: a handful of extreme outliers can
    otherwise define an entire state's reputation. The p90 is reported next to
    the median because the tail is what customers complain about.
*/

{{ config(materialized='table') }}

with orders as (

    select *
    from {{ ref('fct_orders') }}
    where is_delivered
        and not is_excluded_from_kpis
        and delay_vs_promise_days is not null

),

by_route as (

    select
        delivery_route,
        seller_state,
        seller_region,
        customer_state,
        customer_region,
        is_intra_state_route,

        -- ---------------- volume ----------------
        count(*)                                                            as delivered_orders,
        sum(order_revenue)                                                  as delivered_revenue,

        -- ---------------- lateness ----------------
        countif(is_late)                                                    as late_orders,
        round(safe_divide(countif(is_late), count(*)), 4)                   as late_rate,
        sum(late_order_revenue)                                             as late_revenue,
        round(safe_divide(sum(late_order_revenue), sum(order_revenue)), 4)
            as late_revenue_share,

        -- ---------------- speed ----------------
        round(approx_quantiles(total_delivery_days, 100)[offset(50)], 2)
            as median_delivery_days,
        round(approx_quantiles(total_delivery_days, 100)[offset(90)], 2)
            as p90_delivery_days,
        round(avg(total_delivery_days), 2)                                  as avg_delivery_days,

        -- ---------------- where the time goes ----------------
        round(approx_quantiles(approval_days, 100)[offset(50)], 2)          as median_approval_days,
        round(approx_quantiles(seller_handover_days, 100)[offset(50)], 2)   as median_handover_days,
        round(approx_quantiles(carrier_transit_days, 100)[offset(50)], 2)   as median_transit_days,

        -- ---------------- the promise itself ----------------
        round(approx_quantiles(promised_delivery_days, 100)[offset(50)], 2)
            as median_promised_days,
        round(approx_quantiles(delay_vs_promise_days, 100)[offset(50)], 2)
            as median_delay_vs_promise_days,

        -- ---------------- cost ----------------
        round(avg(review_score), 3)                                         as avg_review_score,
        round(avg(case when is_late then review_score end), 3)              as avg_review_score_when_late,
        round(avg(case when not is_late then review_score end), 3)          as avg_review_score_when_on_time,
        round(avg(freight_share_of_order), 4)                               as avg_freight_share

    from orders
    group by
        delivery_route,
        seller_state,
        seller_region,
        customer_state,
        customer_region,
        is_intra_state_route

)

select
    *,

    -- Satisfaction actually lost on this route when an order runs late. This is
    -- the number that converts a logistics metric into a customer outcome.
    round(avg_review_score_when_on_time - avg_review_score_when_late, 3)
        as review_score_penalty_when_late,

    -- Reporting flag rather than a filter: low-volume routes stay in the table
    -- so totals reconcile, but charts suppress them. A 100% late rate on three
    -- orders is noise, not a finding.
    delivered_orders >= {{ var('min_orders_for_reporting') }}                                             as is_reportable

from by_route
order by late_orders desc
