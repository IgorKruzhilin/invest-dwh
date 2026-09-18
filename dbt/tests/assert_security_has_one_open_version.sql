-- Every security has exactly one open version. Zero means the row
-- disappeared from the listing and the snapshot closed it. Two means a
-- second board of the same security or a broken key.
select
	exchange
	, sec_id
	, countif(valid_to = timestamp '9999-12-31') open_versions
from {{ ref('dim_security') }}
group by
	exchange
	, sec_id
having open_versions != 1
