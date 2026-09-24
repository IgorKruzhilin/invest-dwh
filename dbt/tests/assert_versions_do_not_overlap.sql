-- The versions of a security must not overlap: the range filter
-- valid_from <= t and t < valid_to must match one row at most.
--
-- A gap between two versions is not an error. It is the interval when the
-- security was not in the listing at all: the snapshot closed its version
-- on the run that did not see it and opened a new one when it came back.
-- Inside the gap the honest answer is that the security was not listed,
-- and no row matches. Proved by hand on 2026-09-24 with SBER.
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
where next_valid_from < valid_to
