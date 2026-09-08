select
	concat(board, '|', secid) listing_key
	, market
	, board
	, secid sec_id
	, boardid board_id
	, shortname short_name
	, name full_name
	, decimals price_decimals
	, history_from listing_from_date
	, history_till listing_till_date
	, _extracted_at extracted_at
from {{ source('raw', 'moex_listing') }}
