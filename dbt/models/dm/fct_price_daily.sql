{{ config(
    materialized='incremental'
    , incremental_strategy='merge'
    , unique_key='price_key'
    , partition_by={'field': 'trade_date', 'data_type': 'date'}
    , cluster_by=['exchange', 'sec_id']
    , incremental_predicates=[
        "DBT_INTERNAL_DEST.trade_date >= date '" ~ var('window_start', '1900-01-01') ~ "'"
    ]
) }}
with hist as (
	select
		'MOEX' exchange
		, dt trade_date
		, sec_id
		, board
		, case currency_id when 'SUR' then 'RUB' else currency_id end currency
		, legal_close_price close_price
		, extracted_at
	from {{ ref('stg_moex_history') }}
	{% if is_incremental() %}
	where dt >= {{ window_start() }}
	{% endif %} 
), splits as (
	select
		hist.trade_date
		, hist.sec_id
		, {{ split_cum_factor('s.split_after', 's.split_before') }} split_cum_factor
	from 
		{{ ref('stg_moex_splits') }} s
		join hist
			on hist.sec_id = s.sec_id
			and hist.trade_date >= s.trade_date
	group by 
		hist.trade_date
		, hist.sec_id
)
select
	concat(hist.exchange, '|', hist.sec_id, '|', cast(hist.trade_date as string)) price_key
	, hist.exchange
	, hist.trade_date
	, hist.sec_id
	, hist.board
	, hist.currency
	, hist.close_price
	, coalesce(splits.split_cum_factor,1) split_cum_factor
	, hist.extracted_at
	, current_timestamp() updated_at

from 
	hist
	left join splits
		on splits.trade_date=hist.trade_date
		and splits.sec_id=hist.sec_id
