from flask import Flask, jsonify, render_template
import bot.database as db
import bot.oanda_client as oanda

app = Flask(__name__)

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

@app.route("/api/positions")
def api_positions():
    return jsonify(oanda.get_open_trades())
