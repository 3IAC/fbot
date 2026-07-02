from flask import Flask, jsonify, render_template, request
import bot.database as db
import bot.oanda_client as oanda
import time as _time

app = Flask(__name__)

# 30-second in-memory cache for candle + price data
_cache: dict = {}
_CACHE_TTL = 30

def _cached(key, fn):
    now = _time.time()
    if key in _cache and now - _cache[key][1] < _CACHE_TTL:
        return _cache[key][0]
    data = fn()
    _cache[key] = (data, now)
    return data

_TF_MAP = {"M1":"M1","M5":"M5","M15":"M15","H1":"H1","H4":"H4","D":"D"}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/account")
def api_account():
    data = oanda.get_account()
    if data:
        acc = data.get("account", {})
        return jsonify({
            "balance": float(acc.get("balance", 0)),
            "nav": float(acc.get("NAV", 0)),
            "unrealized_pnl": float(acc.get("unrealizedPL", 0)),
            "open_trade_count": int(acc.get("openTradeCount", 0)),
        })
    return jsonify({})

@app.route("/api/candles")
def api_candles():
    instrument = request.args.get("instrument", "EUR_USD")
    tf = _TF_MAP.get(request.args.get("tf", "M5"), "M5")
    count = min(int(request.args.get("count", "200")), 500)
    key = f"candles_{instrument}_{tf}"
    candles = _cached(key, lambda: oanda.get_candles(instrument, granularity=tf, count=count))
    return jsonify(candles)

@app.route("/api/positions")
def api_positions():
    trades = oanda.get_open_trades()
    for t in trades:
        inst = t.get("instrument", "")
        price = _cached(f"price_{inst}", lambda i=inst: oanda.get_price(i))
        t["current_price"] = price
    return jsonify(trades)

@app.route("/api/trades")
def api_trades():
    return jsonify(db.get_all_trades(limit=50))

@app.route("/api/stats")
def api_stats():
    return jsonify(db.get_stats())

@app.route("/api/signals")
def api_signals():
    return jsonify(db.get_recent_signals(limit=20))

@app.route("/api/brain")
def api_brain():
    return jsonify(db.get_latest_brain() or {})

@app.route("/api/performance")
def api_performance():
    return jsonify(db.get_performance())
