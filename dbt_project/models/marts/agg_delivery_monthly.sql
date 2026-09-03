/*
    ANSWERS: "WHEN are deliveries late?"

    Grain: one row per purchase month.

    Two things this model is careful about:

    1. Orders are bucketed by PURCHASE month, not delivery month. The business
       question is "if I order in November, what happens to me?", and bucketing
       by delivery date would push a November disaster into December and hide
       the seasonal peak that caused it.

    2. is_in_analysis_window is carried through rather than filtered out. The
       first and last months of the Olist export are sparse, and dropping them
       silently would leave a chart that looks like a demand collapse. Charts
       trim or annotate them using this flag, and the decision stays visible.

    The stage medians are the point of this model: they show whether time is
    lost in payment approval, in the seller's warehouse, or with the carrier.
    Those three findings lead to three completely different recommendations.
*/

{{ config(materialized='table') }}

with orders as (

    select *
    from {{ ref('fct_orders') }}
    where not is_excluded_from_kpis

),

dates as (

    select
        date_key,
        year_month,
        month_label,
        month_start_date,
        is_in_analysis_window
    from {{ ref('dim_date') }}

),

joined as (

    select
        d.year_month,
        d.month_label,
        d.month_start_date,
        d.is_in_analysis_window,
        o.*
    from orders as o
    left join dates as d on o.order_purchase_date = d.date_key

),

monthly as (

    select
        year_month,
        month_label,
        month_start_date,
        is_in_analysis_window,

        -- ---------------- volume ----------------
        count(*)                                                            as orders_placed,
        countif(is_delivered)                                               as orders_delivered,
        sum(order_revenue)                                                  as revenue,
        sum(order_freight)                                                  as freight,

        -- ---------------- lateness (delivered orders only) ----------------
        countif(is_late)                                                    as late_orders,
        round(safe_divide(countif(is_late), countif(is_delivered)), 4)
            as late_rate,
        sum(late_order_revenue)                                             as late_revenue,

        -- ---------------- speed ----------------
        round(approx_quantiles(
            case when is_delivered then total_delivery_days end, 100
        )[offset(50)], 2)
            as median_delivery_days,
        round(approx_quantiles(
            case when is_delivered then total_delivery_days end, 100
        )[offset(90)], 2)
            as p90_delivery_days,

        -- ---------------- where the time goes ----------------
        round(approx_quantiles(
            case when is_delivered then approval_days end, 100
        )[offset(50)], 2)
            as median_approval_days,
        round(approx_quantiles(
            case when is_delivered then seller_handover_days end, 100
        )[offset(50)], 2)
            as median_handover_days,
        round(approx_quantiles(
            case when is_delivered then carrier_transit_days end, 100
        )[offset(50)], 2)
            as median_transit_days,

        -- ---------------- the promise ----------------
        round(approx_quantiles(promised_delivery_days, 100)[offset(50)], 2)
            as median_promised_days,
        round(avg(promise_slack_days), 2)                                   as avg_promise_slack_days,

        -- ---------------- cost ----------------
        round(avg(review_score), 3)                                         as avg_review_score,
        round(avg(case when is_late then review_score end), 3)              as avg_review_score_when_late,
        round(avg(case when not is_late then review_score end), 3)          as avg_review_score_when_on_time

    from joined
    group by year_month, month_label, month_start_date, is_in_analysis_window

)

select
    *,
    round(avg_review_score_when_on_time - avg_review_score_when_late, 3)
        as review_score_penalty_when_late,

    -- Month-over-month movement in the headline metric, so the deck can say
    -- "improving" or "worsening" with a number attached rather than a vibe.
    round(late_rate - lag(late_rate) over (order by month_start_date), 4)
        as late_rate_mom_change

from monthly
order by month_start_date
