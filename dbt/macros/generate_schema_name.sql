-- Return the custom schema as it is. The dbt default joins it with the
-- profile schema, which is for many developers on one project.
-- The CI target is the exception: a build from a pull request puts
-- everything into the one CI dataset and never touches dm.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none or target.name == 'ci' -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
