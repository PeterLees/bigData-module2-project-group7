/*
    FAN-OUT CONTROL 1 of 4.

    Collapses payment records to ONE ROW PER ORDER.

    An order can have several payment lines (an installment plan plus a
    voucher, for example). Joining raw payments to order items produces
    N items x M payments rows, which inflates revenue by a factor that looks
    plausible and is therefore very hard to spot. Aggregating here, once, makes
    that mistake impossible for every downstream consumer.
*/

with payments as (

    select * from {{ ref('stg_order_payments') }}

),

aggregated as (

    select
        order_id,

        count(*)                                                                                 as payment_record_count,
        sum(payment_value)                                                                       as order_payment_total,
        max(payment_installments)                                                                as max_payment_installments,

        -- the payment method carrying the largest value; used for reporting
        array_agg(payment_type order by payment_value desc, payment_type asc limit 1)[offset(0)]
            as primary_payment_type,

        string_agg(distinct payment_type, ' + ' order by payment_type)
            as payment_type_mix,

        countif(payment_type = 'voucher')                                                        as voucher_payment_count

    from payments
    group by order_id

)

select * from aggregated
