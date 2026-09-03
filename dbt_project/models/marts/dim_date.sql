/*
    Grain: one calendar day.

    A conformed date dimension exists here for one concrete reason: the "WHEN"
    half of the delivery business case needs month, week and weekday cuts that
    are consistent across every model and chart. Deriving them ad hoc with
    string functions on a timestamp is both inconsistent and, in BigQuery,
    actively harmful, because wrapping the partition column in a function
    prevents partition pruning.

    Range is fixed rather than derived from the data so that the dimension does
    not silently change shape if a future load has different coverage.
*/

{% set date_start = "2016-01-01" %}
{% set date_end   = "2019-01-01" %}

with spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('" ~ date_start ~ "' as date)",
        end_date="cast('" ~ date_end ~ "' as date)"
    ) }}

),

enriched as (

    select
        cast(date_day as date)                              as date_key,

        extract(year    from date_day)                      as calendar_year,
        extract(quarter from date_day)                      as calendar_quarter,
        extract(month   from date_day)                      as calendar_month,
        extract(day     from date_day)                      as day_of_month,
        extract(week    from date_day)                      as week_of_year,
        extract(dayofweek from date_day)                    as day_of_week,   -- 1 = Sunday

        format_date('%Y-%m', date_day)                      as year_month,
        format_date('%b %Y', date_day)                      as month_label,
        format_date('%A',    date_day)                      as day_name,

        date_trunc(date_day, month)                         as month_start_date,
        date_trunc(date_day, week)                          as week_start_date,

        extract(dayofweek from date_day) in (1, 7)          as is_weekend,

        -- Whether this day sits inside the window with usable Olist coverage.
        -- Charts use it to trim or annotate the sparse first and last months
        -- rather than presenting them as a collapse in demand.
        date_day between date('{{ var("analysis_start_date") }}')
                     and date('{{ var("analysis_end_date") }}')   as is_in_analysis_window

    from spine

)

select * from enriched
