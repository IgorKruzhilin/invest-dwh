select
	concat(exchange, '|', sec_id, '|', cast(valid_from as string)) security_key
	, exchange
	, sec_id
	, board
	, short_name
	, full_name
	, price_decimals
	, listing_from_date
	, listing_till_date
	, valid_from
	, valid_to
	, extracted_at
	, current_timestamp() updated_at
from {{ ref('snap_moex_listing') }}
