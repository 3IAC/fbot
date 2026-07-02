import requests
from bot.config import OANDA_API_KEY, OANDA_ACCOUNT_ID, OANDA_BASE_URL
import bot.database as db


def _headers():
    return {
        "Authorization": f"Bearer {OANDA_API_KEY}",
        "Content-Type": "application/json",
        "Accept-Datetime-Format": "RFC3339",
    }


def _get(path, params=None):
    try:
        r = requests.get(f"{OANDA_BASE_URL}{path}", headers=_headers(), params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        db.log_error("oanda", f"GET {path} -> {r.status_code}: {r.text[:300]}")
    except Exception as e:
        db.log_error("oanda", f"GET {path} exception: {e}")
    return None


def _post(path, body):
    try:
        r = requests.post(f"{OANDA_BASE_URL}{path}", headers=_headers(), json=body, timeout=15)
        if r.status_code in (200, 201):
            return r.json()
        db.log_error("oanda", f"POST {path} -> {r.status_code}: {r.text[:300]}")
    except Exception as e:
        db.log_error("oanda", f"POST {path} exception: {e}")
    return None


def get_account():
    return _get(f"/v3/accounts/{OANDA_ACCOUNT_ID}/summary")


def get_open_trades():
    data = _get(f"/v3/accounts/{OANDA_ACCOUNT_ID}/openTrades")
    return data.get("trades", []) if data else []


def get_candles(instrument, granularity="M5", count=100):
    """
    Fetch OHLCV candles.
    granularity: M1, M5, M15, H1, H4, D
    Returns list of dicts with keys: time, o, h, l, c, volume
    """
    data = _get(
        f"/v3/instruments/{instrument}/candles",
        params={"granularity": granularity, "count": count, "price": "M"}
    )
    if not data:
        return []
    candles = []
    for c in data.get("candles", []):
        if c.get("complete", True):
            mid = c.get("mid", {})
            candles.append({
                "t": c["time"],
                "o": float(mid.get("o", 0)),
                "h": float(mid.get("h", 0)),
                "l": float(mid.get("l", 0)),
                "c": float(mid.get("c", 0)),
                "v": int(c.get("volume", 0)),
            })
    return candles


def get_price(instrument):
    """Get current mid price for an instrument."""
    data = _get(f"/v3/accounts/{OANDA_ACCOUNT_ID}/pricing",
                params={"instruments": instrument})
    if data:
        prices = data.get("prices", [])
        if prices:
            bid = float(prices[0].get("bids", [{}])[0].get("price", 0))
            ask = float(prices[0].get("asks", [{}])[0].get("price", 0))
            return round((bid + ask) / 2, 5)
    return None


def place_order(instrument, units, stop_loss_price, take_profit_price):
    """
    Place a market order with bracket (SL + TP).
    units > 0 = buy, units < 0 = sell.
    """
    body = {
        "order": {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(units),
            "timeInForce": "FOK",
            "stopLossOnFill": {"price": f"{stop_loss_price:.5f}"},
            "takeProfitOnFill": {"price": f"{take_profit_price:.5f}"},
        }
    }
    return _post(f"/v3/accounts/{OANDA_ACCOUNT_ID}/orders", body)


def close_trade(trade_id):
    try:
        r = requests.put(
            f"{OANDA_BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/trades/{trade_id}/close",
            headers=_headers(), timeout=10
        )
        if r.status_code in (200, 201):
            return r.json()
        db.log_error("oanda", f"close trade {trade_id} -> {r.status_code}: {r.text[:200]}")
    except Exception as e:
        db.log_error("oanda", f"close trade exception: {e}")
    return None


def get_trade(trade_id):
    data = _get(f"/v3/accounts/{OANDA_ACCOUNT_ID}/trades/{trade_id}")
    return data.get("trade") if data else None
