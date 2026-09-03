{#
    Map a Brazilian two-letter state code to its official IBGE macro-region.

    The delivery business case is fundamentally geographic: nearly all Olist
    sellers sit in the Southeast, so distance to region is the strongest
    structural driver of transit time. Grouping to five regions gives charts
    that an executive can read, where 27 states cannot.
#}
{% macro br_region(state_column) -%}
    case upper(trim({{ state_column }}))
        when 'AC' then 'Norte'        when 'AP' then 'Norte'
        when 'AM' then 'Norte'        when 'PA' then 'Norte'
        when 'RO' then 'Norte'        when 'RR' then 'Norte'
        when 'TO' then 'Norte'

        when 'AL' then 'Nordeste'     when 'BA' then 'Nordeste'
        when 'CE' then 'Nordeste'     when 'MA' then 'Nordeste'
        when 'PB' then 'Nordeste'     when 'PE' then 'Nordeste'
        when 'PI' then 'Nordeste'     when 'RN' then 'Nordeste'
        when 'SE' then 'Nordeste'

        when 'DF' then 'Centro-Oeste' when 'GO' then 'Centro-Oeste'
        when 'MT' then 'Centro-Oeste' when 'MS' then 'Centro-Oeste'

        when 'ES' then 'Sudeste'      when 'MG' then 'Sudeste'
        when 'RJ' then 'Sudeste'      when 'SP' then 'Sudeste'

        when 'PR' then 'Sul'          when 'RS' then 'Sul'
        when 'SC' then 'Sul'
        else 'Unknown'
    end
{%- endmacro %}
