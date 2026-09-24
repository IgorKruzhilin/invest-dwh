select
	security_key
	, listing_from_date
	, listing_till_date
from {{ ref('dim_security') }}
where listing_from_date > listing_till_date
