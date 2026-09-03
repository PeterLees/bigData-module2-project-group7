/*
    FAN-OUT CONTROL 2 of 4.

    Collapses reviews to ONE ROW PER ORDER.

    The source contains repeated review_id values and orders with more than one
    review. Joining it directly to orders duplicates the order and therefore
    duplicates its revenue and its delivery measures.

    Tie-break rule, stated explicitly because it is a judgement call: keep the
    MOST RECENT review by creation date, and break exact ties on review_id so
    the result is deterministic across runs. The most recent review is the
    customer's settled opinion, which is what the delivery business case needs.
*/

with reviews as (

    select * from {{ ref('stg_order_reviews') }}

),

deduplicated as (

    select
        order_id,
        review_id,
        review_score,
        review_created_at,
        review_answered_at,
        has_comment,

        -- how many reviews this order actually had, kept for transparency
        count(*) over (partition by order_id) as source_review_count

    from reviews
    qualify row_number() over (
            partition by order_id
            order by review_created_at desc, review_id asc
        ) = 1

)

select * from deduplicated
