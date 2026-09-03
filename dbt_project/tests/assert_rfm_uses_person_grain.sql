/*
    Proves the customer-identity trap was actually avoided.

    Severity: error. If RFM is keyed on the wrong column the entire
    segmentation is wrong, and it is wrong in a way that looks plausible: every
    customer becomes a one-time buyer and the frequency distribution collapses
    to a single value.

    Three assertions, and the first one is a correction of this test's original
    form. It used to compare agg_customer_rfm against ALL of dim_customer, which
    failed on the first real run: 96,096 people exist, but only 94,990 have an
    order that survives the excluded-status filter. The other 1,106 placed
    nothing but canceled or unavailable orders, and there is no recency,
    frequency or monetary value to compute for them. Excluding them is correct
    behaviour, so the test now compares against the right denominator.

    1. RFM row count == distinct people holding at least one kept order.
       Catches both a dropped join and an accidental fan-out.

    2. RFM row count is materially BELOW the distinct source customer_id count.
       This is the real trap made numeric: customer_id is issued per order, so
       there are 99,441 of them for 96,096 people. If someone re-keys RFM on
       customer_id this ratio goes to 1.0 and the test fires.

    3. At least one customer has frequency > 1. Olist genuinely has repeat
       buyers (the maximum is 16), so a segmentation in which nobody repeats is
       a bug, not a finding.
*/

with rfm as (

    select
        count(*)        as customer_rows,
        max(frequency)  as max_frequency
    from {{ ref('agg_customer_rfm') }}

),

expected as (

    select
        count(distinct customer_key)        as people_with_kept_orders,
        count(distinct source_customer_id)  as distinct_customer_ids
    from {{ ref('fct_orders') }}
    where not is_excluded_from_kpis

)

select
    r.customer_rows,
    e.people_with_kept_orders,
    e.distinct_customer_ids,
    r.max_frequency,
    case
        when r.customer_rows != e.people_with_kept_orders
            then 'row count does not match the number of people with a kept order'
        when r.customer_rows >= e.distinct_customer_ids
            then 'as many rows as customer_ids: RFM is probably keyed on the per-order id'
        when r.max_frequency <= 1
            then 'no repeat customers: RFM is probably keyed on the per-order id'
    end as violation

from rfm r
cross join expected e
where r.customer_rows != e.people_with_kept_orders
   or r.customer_rows >= e.distinct_customer_ids
   or r.max_frequency <= 1
