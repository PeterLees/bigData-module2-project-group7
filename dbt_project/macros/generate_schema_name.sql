{#
    Control where models land.

    dev  : dbt_<yourname>_staging / dbt_<yourname>_marts
           Personal sandbox, so nobody can overwrite anyone else's tables.

    prod : olist_staging / olist_marts exactly, with no prefix.
    ci   : same as prod.

    This is what makes the "everyone develops in isolation, only a passing
    build reaches the shared marts" rule in the development plan enforceable.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- elif target.name in ('prod', 'ci') -%}
        olist_{{ custom_schema_name | trim }}
    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
