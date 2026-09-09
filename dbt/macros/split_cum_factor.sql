-- macros/split_cum_factor.sql
{% macro split_cum_factor(split_after, split_before) -%}
    coalesce(
        round(exp(sum(ln({{ split_after }} / {{ split_before }}))), 6)
        , 1
    )
{%- endmacro %}