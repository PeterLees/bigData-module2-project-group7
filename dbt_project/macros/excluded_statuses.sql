{#
    The order statuses excluded from revenue and delivery KPIs, rendered as a
    SQL list literal. Sourced from the `excluded_order_statuses` project var so
    the caliber is defined in exactly one place.

    Usage:  where order_status not in {{ excluded_statuses() }}
#}
{% macro excluded_statuses() -%}
    ({%- for status in var('excluded_order_statuses') -%}
        '{{ status }}'{% if not loop.last %}, {% endif %}
    {%- endfor -%})
{%- endmacro %}
