"""Load the MOEX splits reference into GCS as Parquet.

Usage:
    python moex_splits.py

The source has no date interval and no paging: ISS gives the whole table
in one answer. So the script always reloads it in full and overwrites one
object.
    gs://invest-dwh-raw/moex/splits/engine=stock/data.parquet

There is no paging on purpose. The endpoint ignores limit and start, it
always answers with all rows (checked on 2026-09-08). A paging loop would
work by luck and would double every row on the day the table has exactly
as many rows as the limit.

An empty answer is an error: the table is small but it is never empty.
The script exits with code 1, never with 99.
"""
import sys
import time
import requests
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timezone

engine = 'stock'
bucket = 'invest-dwh-raw'
prefix = 'moex/splits'
# name of the block in the ISS answer
block = 'splits'
retries = 5
pause = 5

# column name in ISS -> type in Parquet, from splits.metadata
expected_columns = {
	'tradedate': pa.date32()
	, 'secid': pa.string()
	, 'before': pa.int64()
	, 'after': pa.int64()
	}

datecols = ['tradedate']

ins_dict = {}
for i in expected_columns:
	ins_dict[i] = None


def log(msg):
	print(datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' ' + msg, flush=True)


log('Start moex_splits ' + engine)
try:
	extracted_at = datetime.now(timezone.utc)

	url = 'https://iss.moex.com/iss/statistics/engines/' + engine + '/splits.json'
	# ISS drops connections now and then, so retry a few times before giving up
	for attempt in range(1, retries + 1):
		try:
			r = requests.get(url, timeout=60)
			r.raise_for_status()
			break
		except requests.RequestException as ex:
			log('attempt ' + str(attempt) + ' failed: ' + str(ex))
			if attempt == retries:
				raise
			time.sleep(pause * attempt)

	data = r.json()[block]['data']
	columns = r.json()[block]['columns']

	# Fail loud when ISS renames a column. Without this check the column
	# would stay null in every row and the load would look fine.
	missing = [col for col in expected_columns if col not in columns]
	if len(missing) > 0:
		raise Exception('columns not found: ' + str(missing) + ', ISS gave: ' + str(columns))

	rows = []
	for i in data:
		new_row = ins_dict.copy()
		for col, el in zip(columns, i):
			if col in expected_columns:
				new_row[col] = el
				if col in datecols and el != None and el != '':
					new_row[col] = datetime.strptime(el, '%Y-%m-%d').date()
		rows.append(new_row)

	if len(rows) == 0:
		raise Exception('ISS gave no rows for engine ' + engine)

	arrays = []
	for col in expected_columns:
		arrays.append(pa.array([row[col] for row in rows], type=expected_columns[col]))
	# technical column: when the file was written
	arrays.append(pa.array([extracted_at] * len(rows), type=pa.timestamp('us', tz='UTC')))
	table = pa.Table.from_arrays(arrays, names=list(expected_columns) + ['_extracted_at'])

	path = 'gs://' + bucket + '/' + prefix + '/engine=' + engine + '/data.parquet'
	pq.write_table(table, path)
	log(str(len(rows)) + ' rows -> ' + path)

	log('Finish moex_splits')
except Exception as ex:
	log('ERROR moex_splits: ' + str(ex))
	sys.exit(1)
