{#
    Bucket delay-versus-promise into labels an executive can act on.

    Kept as a macro rather than repeated CASE statements so the buckets used in
    fct_orders, in the aggregates and in the notebooks can never diverge. The
    numeric measure is always stored alongside the bucket, so nobody is forced
    to reverse-engineer the boundaries.

    Negative = delivered before the promised date.
#}
{% macro lateness_bucket(delay_days_column) -%}
    case
        when {{ delay_days_column }} is null      then 'Not delivered'
        when {{ delay_days_column }} <= -8        then '1. Very early (8+ days)'
        when {{ delay_days_column }} <= -1        then '2. Early (1-7 days)'
        when {{ delay_days_column }} = 0          then '3. On the promised day'
        when {{ delay_days_column }} <= 3         then '4. Late (1-3 days)'
        when {{ delay_days_column }} <= 7         then '5. Late (4-7 days)'
        when {{ delay_days_column }} <= 15        then '6. Late (8-15 days)'
        else                                           '7. Late (16+ days)'
    end
{%- endmacro %}
