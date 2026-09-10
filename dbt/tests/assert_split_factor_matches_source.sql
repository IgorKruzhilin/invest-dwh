-- The factor stored by past runs must match the splits source of today.
-- A split published late changes rows before the window, and the model
-- never sees them again. This test does, with the same macro on newer data.
-- Only securities with a split are recomputed. Securities without a split
-- must have a factor of 1, that part runs on the window only.
-- A red row shows the first bad trade_date: rerun the model with
-- window_start set to that date, not a full refresh.
with split_securities as (
	select distinct sec_id
	from {{ ref('stg_moex_splits') }}
), recomputed as (
	select
		f.exchange
		, f.sec_id
		, f.trade_date
		, f.split_cum_factor stored
		, {{ split_cum_factor('s.split_after', 's.split_before') }} expected
	from
		{{ ref('fct_price_daily') }} f
		join split_securities ss
			on ss.sec_id = f.sec_id
		left join {{ ref('stg_moex_splits') }} s
			on s.sec_id = f.sec_id
			and s.trade_date <= f.trade_date
	where f.exchange = 'MOEX'
	group by
		f.exchange
		, f.sec_id
		, f.trade_date
		, f.split_cum_factor
), no_split as (
	select
		f.exchange
		, f.sec_id
		, f.trade_date
		, f.split_cum_factor stored
		, 1 expected
	from {{ ref('fct_price_daily') }} f
	where
		f.exchange = 'MOEX'
		and f.trade_date >= date '{{ var("window_start", "1900-01-01") }}'
		and f.sec_id not in (select sec_id from split_securities)
), checked as (
	select
		exchange
		, sec_id
		, trade_date
		, stored
		, expected
	from recomputed
	union all
	select
		exchange
		, sec_id
		, trade_date
		, stored
		, expected
	from no_split
)
select
	exchange
	, sec_id
	, trade_date
	, stored
	, expected
from checked
where abs(stored - expected) > 1e-6
order by
	sec_id
	, trade_date
