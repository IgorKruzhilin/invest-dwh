-- macros/window_start.sql
{% macro window_start(days=7) -%}
    {%- if var('window_start', none) is not none -%}
        date '{{ var("window_start") }}'
        {{ log("fct_price_daily window_start = " ~ var("window_start"), info=true) }}
    {%- elif execute -%}
        {%- set query -%}
            select cast(date_sub(max(trade_date), interval {{ days }} day) as string)
            from {{ this }}
        {%- endset -%}
        {%- set result = run_query(query) -%}
        date '{{ result.columns[0].values()[0] }}'
        {{ log("fct_price_daily window_start = " ~ result.columns[0].values()[0], info=true) }}
    {%- else -%}
        date '1900-01-01'
    {%- endif -%}
{%- endmacro %}