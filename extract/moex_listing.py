"""Load the MOEX board listing into GCS as Parquet.

Usage:
    python moex_listing.py

The source has no date interval: ISS returns the whole listing of the board
in one answer. So the script always reloads it in full and overwrites one
object.
    gs://invest-dwh-raw/moex/listing/market=shares/board=TQBR/data.parquet

The listing already keeps the history of board membership in history_from
and history_till, so we store no snapshot of our own.

An empty answer is an error, not an empty day: a board always has
securities. The script exits with code 1, never with 99.
"""
import sys
import time
import requests
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timezone

market = 'shares'
board = 'TQBR'
bucket = 'invest-dwh-raw'
prefix = 'moex/listing'
retries = 5
pause = 5

# column name in ISS -> type in Parquet, from listing.metadata
expected_columns = {
	'SECID': pa.string()
	, 'BOARDID': pa.string()
	, 'SHORTNAME': pa.string()
	, 'NAME': pa.string()
	, 'history_from': pa.date32()
	, 'history_till': pa.date32()
	}

datecols = ['history_from', 'history_till']

ins_dict = {}
for i in expected_columns:
	ins_dict[i] = None


def log(msg):
	print(datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' ' + msg, flush=True)


log('Start moex_listing ' + market + ' ' + board)
try:
	extracted_at = datetime.now(timezone.utc)

	rows = []
	cur_start = 0
	limit = 100
	cur_len = limit
	while cur_len == limit:
		url = 'https://iss.moex.com/iss/history/engines/stock/markets/' + market + '/boards/' + board + '/listing.json?limit=' + str(limit) + '&start=' + str(cur_start)
		# ISS drops connections now and then, so retry a few times before giving up
		for attempt in range(1, retries + 1):
			try:
				r = requests.get(url, timeout=60)
				r.raise_for_status()
				break
			except requests.RequestException as ex:
				log('start=' + str(cur_start) + ' attempt ' + str(attempt) + ' failed: ' + str(ex))
				if attempt == retries:
					raise
				time.sleep(pause * attempt)
		data = r.json()['listing']['data']
		columns = r.json()['listing']['columns']

		# Fail loud when ISS renames a column. Without this check the column
		# would stay null in every row and the load would look fine.
		if cur_start == 0:
			missing = [col for col in expected_columns if col not in columns]
			if len(missing) > 0:
				raise Exception('columns not found: ' + str(missing) + ', ISS gave: ' + str(columns))

		cur_len = len(data)
		for i in data:
			new_row = ins_dict.copy()
			for col, el in zip(columns, i):
				if col in expected_columns:
					new_row[col] = el
					if col in datecols and el != None and el != '':
						new_row[col] = datetime.strptime(el, '%Y-%m-%d').date()
			rows.append(new_row)
		cur_start += cur_len

	if len(rows) == 0:
		raise Exception('ISS gave no rows for board ' + board)

	arrays = []
	for col in expected_columns:
		arrays.append(pa.array([row[col] for row in rows], type=expected_columns[col]))
	# technical column: when the file was written
	arrays.append(pa.array([extracted_at] * len(rows), type=pa.timestamp('us', tz='UTC')))
	table = pa.Table.from_arrays(arrays, names=list(expected_columns) + ['_extracted_at'])

	path = 'gs://' + bucket + '/' + prefix + '/market=' + market + '/board=' + board + '/data.parquet'
	pq.write_table(table, path)
	log(str(len(rows)) + ' rows -> ' + path)

	log('Finish moex_listing')
except Exception as ex:
	log('ERROR moex_listing: ' + str(ex))
	sys.exit(1)
