"""Load MOEX daily trade history for one board into GCS as Parquet.

Usage:
    python moex_history.py 2026-09-01
    python moex_history.py 2026-08-01 2026-08-31

One trade date gives one file. The partition key in the path is dt,
not tradedate: BigQuery column names are case-insensitive, and the files
already have a TRADEDATE column.
    gs://invest-dwh-raw/moex/history/market=shares/board=TQBR/dt=2026-09-01/data.parquet

A rerun for the same date overwrites the file. The script never reads
the current date, the interval always comes from arguments.
"""
import sys
import time
import requests
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timedelta, timezone

market = 'shares'
board = 'TQBR'
bucket = 'invest-dwh-raw'
prefix = 'moex/history'
retries = 5
pause = 5

# column name in ISS -> type in Parquet, from history.metadata
expected_columns = {
	'BOARDID': pa.string()
	, 'TRADEDATE': pa.date32()
	, 'SHORTNAME': pa.string()
	, 'SECID': pa.string()
	, 'NUMTRADES': pa.float64()
	, 'VALUE': pa.float64()
	, 'OPEN': pa.float64()
	, 'LOW': pa.float64()
	, 'HIGH': pa.float64()
	, 'LEGALCLOSEPRICE': pa.float64()
	, 'WAPRICE': pa.float64()
	, 'CLOSE': pa.float64()
	, 'VOLUME': pa.float64()
	, 'MARKETPRICE2': pa.float64()
	, 'MARKETPRICE3': pa.float64()
	, 'ADMITTEDQUOTE': pa.float64()
	, 'MP2VALTRD': pa.float64()
	, 'MARKETPRICE3TRADESVALUE': pa.float64()
	, 'ADMITTEDVALUE': pa.float64()
	, 'WAVAL': pa.float64()
	, 'TRADINGSESSION': pa.int32()
	, 'CURRENCYID': pa.string()
	, 'TRENDCLSPR': pa.float64()
	, 'TRADE_SESSION_DATE': pa.date32()
	}

datecols = ['TRADEDATE', 'TRADE_SESSION_DATE']

ins_dict = {}
for i in expected_columns:
	ins_dict[i] = None


def log(msg):
	print(datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' ' + msg, flush=True)


if len(sys.argv) not in (2, 3):
	print('usage: python moex_history.py FROM_DATE [TILL_DATE]')
	sys.exit(1)
fromdate = datetime.strptime(sys.argv[1], '%Y-%m-%d').date()
tilldate = datetime.strptime(sys.argv[-1], '%Y-%m-%d').date()

log('Start moex_history ' + str(fromdate) + ' .. ' + str(tilldate))
try:
	extracted_at = datetime.now(timezone.utc)
	written = 0

	cur_date = fromdate
	while cur_date <= tilldate:
		tradedate = cur_date.strftime('%Y-%m-%d')

		rows = []
		cur_start = 0
		limit = 100
		cur_len = limit
		while cur_len == limit:
			url = 'https://iss.moex.com/iss/history/engines/stock/markets/' + market + '/boards/' + board + '/securities.json?date=' + tradedate + '&limit=' + str(limit) + '&start=' + str(cur_start)
			# ISS drops connections now and then, so retry a few times before giving up
			for attempt in range(1, retries + 1):
				try:
					r = requests.get(url, timeout=60)
					r.raise_for_status()
					break
				except requests.RequestException as ex:
					log(tradedate + ' start=' + str(cur_start) + ' attempt ' + str(attempt) + ' failed: ' + str(ex))
					if attempt == retries:
						raise
					time.sleep(pause * attempt)
			data = r.json()['history']['data']
			columns = r.json()['history']['columns']
			cur_len = len(data)
			for i in data:
				new_row = ins_dict.copy()
				for col, el in zip(columns, i):
					if col in expected_columns:
						new_row[col] = el
						if col in datecols and el != None:
							new_row[col] = datetime.strptime(el, '%Y-%m-%d').date()
				rows.append(new_row)
			cur_start += cur_len

		if len(rows) == 0:
			log(tradedate + ': 0 rows, file not written')
		else:
			arrays = []
			for col in expected_columns:
				arrays.append(pa.array([row[col] for row in rows], type=expected_columns[col]))
			# technical column: when the file was written
			arrays.append(pa.array([extracted_at] * len(rows), type=pa.timestamp('us', tz='UTC')))
			table = pa.Table.from_arrays(arrays, names=list(expected_columns) + ['_extracted_at'])

			path = 'gs://' + bucket + '/' + prefix + '/market=' + market + '/board=' + board + '/dt=' + tradedate + '/data.parquet'
			pq.write_table(table, path)
			log(tradedate + ': ' + str(len(rows)) + ' rows -> ' + path)
			written += 1

		cur_date += timedelta(days=1)

	log('Finish moex_history')

	# Nothing was written for the whole interval. Exit 99 so that Airflow
	# marks the task as skipped, not as success.
	if written == 0:
		sys.exit(99)
except Exception as ex:
	log('ERROR moex_history: ' + str(ex))
	sys.exit(1)
