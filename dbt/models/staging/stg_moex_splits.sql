select
	concat(cast(tradedate as string), '|', secid) split_key
	, engine
	, tradedate trade_date
	, secid sec_id
	, before split_before
	, after split_after
	, _extracted_at extracted_at
from {{ source('raw', 'moex_splits') }}
