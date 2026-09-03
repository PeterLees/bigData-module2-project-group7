{% snapshot snap_product_category %}

/*
    SCD Type 2 demonstration on product category.

    Stated honestly, because the alternative is misleading: Olist is a static
    historical export, so no product actually changes category during this
    project. Nothing real is being captured here.

    It exists because tracking a changing dimension is a course capability we
    need to demonstrate, and product category is the field where a change would
    genuinely matter: recategorising a product retrospectively would silently
    rewrite every historical category report. With a Type 2 snapshot, a report
    for March 2018 keeps the category the product had in March 2018.

    check strategy rather than timestamp, because the source has no reliable
    updated_at column. To see it work, change one product's category in the raw
    table and rerun the snapshot: a second row appears with the new
    dbt_valid_from and the old row gets a dbt_valid_to.
*/

    {{
        config(
            target_schema=target.schema ~ '_snapshots' if target.name not in ('prod', 'ci') else 'olist_snapshots',
            unique_key='product_key',
            strategy='check',
            check_cols=['product_category', 'product_category_pt'],
            invalidate_hard_deletes=True
        )
    }}

    select
        product_key,
        product_category,
        product_category_pt,
        product_weight_g,
        product_volume_cm3
    from {{ ref('stg_products') }}

{% endsnapshot %}
