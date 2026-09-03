/*
    PHYSICALLY IMPOSSIBLE milestone orderings only.

    Severity: error. These cannot happen in reality, so if one appears a
    timestamp is corrupt and every duration derived from it is wrong.

    Deliberately narrower than it first looks. The original version of this test
    also failed when the carrier-handover timestamp preceded the payment-approval
    timestamp, and that fired on 1,382 orders (1.37%) on the first real run.
    Investigation showed a median gap of 21 hours and a p95 of about 4 days,
    which is the signature of ASYNCHRONOUS EVENT RECORDING, not corruption: a
    Brazilian boleto settles in one to three business days, so a seller can ship
    before the approval row is written. That case is monitored separately by
    assert_milestone_recording_order at warn severity.

    Keeping both in one error-severity test would have meant a permanently red
    build over a documented source characteristic, which is the fastest way to
    teach a team to ignore its own tests.
*/

select
    order_id,
    order_purchased_at,
    order_approved_at,
    order_delivered_at,
    case
        when order_approved_at  < order_purchased_at then 'approved before purchase'
        when order_delivered_at < order_purchased_at then 'delivered before purchase'
    end as violation

from {{ ref('int_order_delivery') }}
where order_approved_at  < order_purchased_at
   or order_delivered_at < order_purchased_at
