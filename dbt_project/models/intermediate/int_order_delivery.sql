/*
    THE MODEL THE WHOLE PROJECT IS ABOUT.

    Turns five raw milestone timestamps into the delivery measures that answer
    the business case: where, when, and at what cost are deliveries late?

    Milestone chain:
        purchased -> approved -> handed to carrier -> delivered
        with `promised` set at purchase time as the customer-facing commitment.

    Three deliberate decisions, each of which changes the headline number:

    1. LATENESS IS MEASURED IN WHOLE DAYS ON DATE BOUNDARIES.
       The promise made to the customer is a date, not a timestamp, so an order
       delivered at 23:00 on the promised day is on time. Using timestamps here
       would manufacture lateness that the customer never experienced.

    2. STAGE DURATIONS USE HOURS DIVIDED BY 24, NOT DATE_DIFF.
       Internal handling time is an operational measure, and rounding it to
       whole days would erase most of the seller-handover signal, which is
       frequently under a day.

    3. LATENESS IS NULL, NOT FALSE, FOR ORDERS THAT NEVER ARRIVED.
       Counting undelivered orders as on-time would understate the late rate.
       Every consumer must therefore filter to delivered orders explicitly,
       which is exactly the discipline we want.
*/

with orders as (

    select * from {{ ref('stg_orders') }}

),

durations as (

    select
        order_id,
        order_status,
        is_delivered,
        is_excluded_from_kpis,

        order_purchased_at,
        order_approved_at,
        order_handed_to_carrier_at,
        order_delivered_at,
        order_promised_at,

        order_purchase_date,
        order_delivered_date,
        order_promised_date,

        -- ---------------------------------------------------------------
        -- Stage durations, in fractional days. Together these localise WHERE
        -- the time is lost: payment approval, seller handover, or carrier.
        -- ---------------------------------------------------------------
        round(timestamp_diff(order_approved_at, order_purchased_at, hour) / 24.0, 3)
            as approval_days,

        round(timestamp_diff(order_handed_to_carrier_at, order_approved_at, hour) / 24.0, 3)
            as seller_handover_days,

        round(timestamp_diff(order_delivered_at, order_handed_to_carrier_at, hour) / 24.0, 3)
            as carrier_transit_days,

        round(timestamp_diff(order_delivered_at, order_purchased_at, hour) / 24.0, 3)
            as total_delivery_days,

        -- What the customer was promised at the moment of purchase.
        date_diff(date(order_promised_at), date(order_purchased_at), day)
            as promised_delivery_days

    from orders

),

lateness as (

    select
        *,

        -- Whole-day delay against the promised date. Negative = early.
        case
            when order_delivered_at is null or order_promised_at is null then null
            else date_diff(date(order_delivered_at), date(order_promised_at), day)
        end as delay_vs_promise_days

    from durations

),

final as (

    select
        *,

        -- The headline flag. NULL when the order never arrived, so that an
        -- undelivered order can never be silently counted as on-time.
        case
            when delay_vs_promise_days is null then null
            else delay_vs_promise_days > 0
        end as is_late,

        {{ lateness_bucket('delay_vs_promise_days') }}     as lateness_bucket,

        -- How wrong the PROMISE itself was, independent of how slow delivery
        -- was. A systematically padded or optimistic estimate is a much
        -- cheaper problem to fix than the logistics, so the two are kept apart.
        case
            when total_delivery_days is null or promised_delivery_days is null then null
            else round(promised_delivery_days - total_delivery_days, 3)
        end as promise_slack_days

    from lateness

)

select * from final
