/*
    The boolean flag and the numeric measure must never disagree.

    is_late is what every aggregate counts; delay_vs_promise_days is what every
    chart plots. If they can drift apart, the headline late rate and the
    distribution behind it tell different stories and neither can be trusted.

    Also asserts that is_late is NULL exactly when the delay is NULL, which is
    what stops undelivered orders being counted as on-time.

    Severity: error.
*/

select
    order_id,
    delay_vs_promise_days,
    is_late,
    lateness_bucket

from {{ ref('fct_orders') }}
where (delay_vs_promise_days is null and is_late is not null)
    or (delay_vs_promise_days is not null and is_late is null)
    or (delay_vs_promise_days > 0 and not is_late)
    or (delay_vs_promise_days <= 0 and is_late)
