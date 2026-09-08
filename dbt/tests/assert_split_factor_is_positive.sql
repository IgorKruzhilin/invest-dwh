select
	sec_id
	, trade_date
	, split_before
	, split_after
from {{ ref('stg_moex_splits') }}
where
	split_before <= 0
	or split_after <= 0
