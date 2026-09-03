{{ config(severity='warn') }}

/*
    Surfaces orders whose status and delivery timestamp disagree.

    First real run found 14 out of 99,441 (0.014%), in two shapes:

      * 8 orders with status 'delivered' but NO delivery timestamp. These are
        the ones that matter: is_late is NULL for them, so they drop out of the
        late-rate DENOMINATOR. The pipeline already handles that correctly and
        deliberately (is_late is NULL rather than false precisely so an order
        that never recorded a delivery cannot be counted as on time), which is
        why this is a warn and not an error.

      * 6 orders with status 'canceled' but WITH a delivery timestamp. Delivered
        and then cancelled, i.e. a return or refund. A normal business outcome.

    Severity: warn. Blocking the whole build on 8 rows of a documented source
    characteristic is the "every threshold is 100%" mistake: it produces a red
    build nobody can clear, and the honest fix is to know the number and quote
    it, not to pretend it is zero.

    The count is what is being monitored. If it grows materially the late-rate
    denominator is being eroded and someone needs to look.
*/

select
    order_id,
    order_status,
    order_delivered_at,
    case
        when is_delivered and order_delivered_at is null
            then 'status is delivered but no delivery timestamp'
        else 'has a delivery timestamp but status is not delivered'
    end as violation

from {{ ref('int_order_delivery') }}
where (is_delivered and order_delivered_at is null)
   or (not is_delivered and order_delivered_at is not null)
