{{ config(severity='warn') }}

/*
    Monitors milestone orderings that are odd but not impossible.

    Severity: warn, and that is a considered decision rather than a convenience.

    Two cases, both artefacts of the source recording events asynchronously
    rather than of corrupt data:

      * carrier handover recorded before payment approval - 1,359 orders (1.37%)
        on the first real run, median gap 21 hours, p95 about 4 days. A boleto
        settles in one to three business days, so the seller ships and the
        approval row lands afterwards.

      * delivered before carrier handover - 23 orders, median gap 43 hours.

    Why this must not block the build: the headline metrics are unaffected.
    total_delivery_days and delay_vs_promise_days are both measured from
    order_purchased_at, which is never out of order. Only the STAGE
    decomposition is affected, and only for 1.4% of orders, where
    seller_handover_days goes negative.

    Why it must not be deleted either: if this count moves materially, something
    upstream has changed, and the stage-level chart in the report would start
    lying. The number is quoted in the report with this caveat attached.
*/

select
    order_id,
    order_approved_at,
    order_handed_to_carrier_at,
    order_delivered_at,
    case
        when order_handed_to_carrier_at < order_approved_at
            then 'carrier handover recorded before payment approval'
        when order_delivered_at < order_handed_to_carrier_at
            then 'delivered before carrier handover'
    end as anomaly

from {{ ref('int_order_delivery') }}
where order_handed_to_carrier_at < order_approved_at
   or order_delivered_at         < order_handed_to_carrier_at
