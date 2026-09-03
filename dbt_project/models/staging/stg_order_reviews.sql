/*
    Customer reviews, at source grain.

    Two source defects are handled here:
      1. exact duplicate rows are removed (safe: no information is lost);
      2. review_id is NOT unique and some orders carry several reviews, which is
         a semantic problem, so it is resolved deliberately in
         int_order_reviews rather than silently here.
*/

with source as (

    select distinct * from {{ source('olist_raw', 'order_reviews') }}

),

renamed as (

    select
        review_id,
        order_id,
        review_score,

        review_comment_title                                  as review_title,
        review_comment_message                                as review_message,
        review_creation_date                                  as review_created_at,
        review_answer_timestamp                               as review_answered_at,

        coalesce(length(trim(review_comment_message)), 0) > 0 as has_comment,

        _batch_id,
        _loaded_at

    from source
    where order_id is not null

)

select * from renamed
