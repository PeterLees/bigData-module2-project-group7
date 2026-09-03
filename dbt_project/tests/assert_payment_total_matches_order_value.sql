{{ config(severity='warn') }}

/*
    Payment total should be close to merchandise plus freight.

    Severity is WARN, not error, and that is a considered decision rather than
    a convenience. Olist has documented, legitimate mismatches: vouchers are
    recorded as payments and reduce the amount actually charged, and a small
    number of orders carry rounding differences. Blocking the build on these
    would be a test that everybody learns to ignore, which is worse than no
    test at all.

    What this does give us is a monitored number. If the mismatch rate or size
    changes materially between runs, something upstream broke, and the report
    carries the current figure openly rather than hiding it.

    A one-cent tolerance absorbs rounding; anything larger is reported.
*/

select
    order_id,
    order_revenue,
    order_freight,
    order_gross_value,
    order_payment_total,
    round(order_payment_total - order_gross_value, 2) as difference,
    payment_type_mix

from {{ ref('fct_orders') }}
where order_payment_total is not null
    and order_gross_value is not null
    and abs(order_payment_total - order_gross_value) > 0.01
    -- vouchers legitimately reduce the charged amount, so they are excluded
    -- from the check rather than allowed to generate permanent noise
    and coalesce(payment_type_mix, '') not like '%voucher%'
