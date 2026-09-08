select
	concat(cast(dt as string), '|', board, '|', secid) history_key
	, market
	, board
	, dt
	, secid sec_id
	, boardid board_id
	, tradedate trade_date
	, trade_session_date
	, tradingsession trading_session
	, shortname short_name
	, currencyid currency_id
	, open open_price
	, high high_price
	, low low_price
	, close close_price
	, legalcloseprice legal_close_price
	, waprice wa_price
	, marketprice2 market_price_2
	, marketprice3 market_price_3
	, admittedquote admitted_quote
	, trendclspr trend_close_price
	, cast(numtrades as int64) num_trades
	, cast(volume as int64) volume
	, value trade_value
	, mp2valtrd mp2_value_traded
	, marketprice3tradesvalue market_price_3_value
	, admittedvalue admitted_value
	, waval avg_turnover_3m
	, _extracted_at extracted_at
from {{ source('raw', 'moex_history') }}
