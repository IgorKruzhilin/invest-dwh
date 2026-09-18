-- The versions of a security form a chain: valid_to of one version is
-- valid_from of the next. A gap or an overlap breaks the range join
-- valid_from <= t and t < valid_to.
with versions as (
	select
		security_key
		, valid_to
		, lead(valid_from) over (partition by exchange, sec_id order by valid_from) next_valid_from
	from {{ ref('dim_security') }}
)
select
	security_key
	, valid_to
	, next_valid_from
from versions
where
	next_valid_from is not null
	and valid_to != next_valid_from
