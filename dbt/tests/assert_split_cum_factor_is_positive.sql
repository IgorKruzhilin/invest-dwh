-- The factor is a product of positive ratios, so it is always above zero.
-- Zero or null would drop a position to nothing in the site's formula.
-- The source ratios have their own test, this one guards the fact.
select
	exchange
	, sec_id
	, trade_date
	, split_cum_factor
from {{ ref('fct_price_daily') }}
where
	trade_date >= date '{{ var("window_start", "1900-01-01") }}'
	and (
		split_cum_factor is null
		or split_cum_factor <= 0
	)
