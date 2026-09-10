-- A null official close is expected only on a day without trades.
-- A row with trades and no price is a case to look at, not to hide.
-- One such row from 2021 is known, so this test warns and does not fail.
-- The filter on dt prunes the history files by the GCS path.
{{ config(severity='warn') }}

select
	f.exchange
	, f.sec_id
	, f.trade_date
	, h.volume
	, h.num_trades
from
	{{ ref('fct_price_daily') }} f
	join {{ ref('stg_moex_history') }} h
		on h.sec_id = f.sec_id
		and h.board = f.board
		and h.dt = f.trade_date
where
	f.trade_date >= date '{{ var("window_start", "1900-01-01") }}'
	and h.dt >= date '{{ var("window_start", "1900-01-01") }}'
	and f.close_price is null
	and h.volume > 0
order by
	f.trade_date
	, f.sec_id
