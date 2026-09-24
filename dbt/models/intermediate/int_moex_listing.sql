select
	concat('MOEX', '|', sec_id) security_id
	, 'MOEX' exchange
	, sec_id
	, board
	, short_name
	, full_name
	, price_decimals
	, listing_from_date
	-- The source moves the last trade date of every listed security each
	-- trading day. The snapshot below tracks this column, so the moving
	-- date is replaced by the open-interval sentinel while the security is
	-- on the board: the latest date in the whole listing is "today" for
	-- the board. A delisting then opens exactly one version.
	, case
		when listing_till_date = max(listing_till_date) over () then date '9999-12-31'
		else listing_till_date
	end listing_till_date
	, extracted_at
from {{ ref('stg_moex_listing') }}
