import bot.database as db
import bot.oanda_client as oanda
from bot.brain import analyze_signal, learn_from_trades
from bot.indicators import get_all_indicators
from bot.config import (
    INSTRUMENTS, STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    MAX_OPEN_TRADES, DEFAULT_CONFIDENCE_THRESHOLD,
    UNITS_EUR_USD, UNITS_GBP_USD, UNITS_XAU_USD
)

_UNITS_MAP = {
    "EUR_USD": UNITS_EUR_USD,
    "GBP_USD": UNITS_GBP_USD,
    "XAU_USD": UNITS_XAU_USD,
}


def run_scan():
    """Scan all forex/gold instruments and place trades on qualified signals."""
    print("[FBOT] Starting scan...")

    acc_data = oanda.get_account()
    if not acc_data:
        print("[FBOT] Could not fetch account")
        return

    balance = float(acc_data.get("account", {}).get("balance", 10000))
    open_trades = oanda.get_open_trades()
    open_instruments = {t["instrument"] for t in open_trades}

    if len(open_trades) >= MAX_OPEN_TRADES:
        print(f"[FBOT] Max trades ({MAX_OPEN_TRADES}) reached")
        return

    recent_db_trades = db.get_all_trades(limit=100)

    for instrument in INSTRUMENTS:
        if len(open_trades) >= MAX_OPEN_TRADES:
            break
        if instrument in open_instruments:
            print(f"[FBOT] {instrument}: position already open, skipping")
            continue

        try:
            candles = oanda.get_candles(instrument, granularity="M5", count=100)
            if not candles or len(candles) < 20:
                print(f"[FBOT] {instrument}: insufficient candle data")
                continue

            indicators = get_all_indicators(candles)
            db.save_snapshot(instrument, indicators.get("price"), indicators.get("rsi"),
                             indicators.get("ma20"), indicators.get("ma50"))

            inst_trades = [t for t in recent_db_trades if t["instrument"] == instrument]
            signal = analyze_signal(instrument, indicators, inst_trades)
            threshold = db.get_adaptive_threshold(instrument, DEFAULT_CONFIDENCE_THRESHOLD)

            print(f"[FBOT] {instrument}: {signal['action'].upper()} "
                  f"({signal['confidence']:.0%}) threshold={threshold:.0%} — {signal['key_signal']}")

            if signal["action"] != "buy" or signal["confidence"] < threshold:
                continue

            price = indicators["price"]
            units = _UNITS_MAP.get(instrument, 1000)
            stop_loss  = round(price * (1 - STOP_LOSS_PCT), 5)
            take_profit = round(price * (1 + TAKE_PROFIT_PCT), 5)

            result = oanda.place_order(instrument, units, stop_loss, take_profit)
            if result:
                trade_id = result.get("orderFillTransaction", {}).get("tradeOpened", {}).get("tradeID")
                fill_price = float(result.get("orderFillTransaction", {}).get("price", price))
                db_id = db.log_trade(
                    instrument, "buy", units, fill_price, trade_id,
                    signal["reasoning"], stop_loss, take_profit
                )
                print(f"[FBOT] BUY {units} {instrument} @ {fill_price:.5f} "
                      f"| SL: {stop_loss:.5f} | TP: {take_profit:.5f} | db_id={db_id}")
            else:
                print(f"[FBOT] {instrument}: order failed")

        except Exception as e:
            db.log_error(f"trader.{instrument}", str(e))


def check_open_trades():
    """Exit monitor: reconcile open DB trades with OANDA and close settled ones."""
    open_db = db.get_open_trades()
    if not open_db:
        return

    oanda_open = {t["id"]: t for t in oanda.get_open_trades()}

    for trade in open_db:
        oanda_id = trade.get("oanda_trade_id")
        if not oanda_id:
            continue
        if oanda_id not in oanda_open:
            # Trade closed by TP or SL
            price = oanda.get_price(trade["instrument"])
            if price:
                db.close_trade(trade["id"], price)
                pnl_pct = (price - trade["entry_price"]) / trade["entry_price"] * 100
                outcome = "WIN" if price > trade["entry_price"] else "LOSS"
                print(f"[FBOT] {outcome} {trade['instrument']} | "
                      f"entry={trade['entry_price']:.5f} exit={price:.5f} | {pnl_pct:+.2f}%")
                _log_learning(trade["instrument"], trade, price, pnl_pct)


def _log_learning(instrument, trade, exit_price, pnl_pct):
    closed = db.get_closed_trades_for_instrument(instrument, limit=20)
    if not closed:
        return
    wins = sum(1 for t in closed if t.get("pnl", 0) and t["pnl"] > 0)
    win_rate = wins / len(closed) if closed else 0
    new_threshold = db.get_adaptive_threshold(instrument)
    detail = (f"win_rate={win_rate:.1%} over {len(closed)} trades | "
              f"pnl={pnl_pct:+.2f}% | threshold now={new_threshold:.2f}")
    print(f"[LEARN] {instrument}: {detail}")


def run_learn():
    print("[FBOT] Running learning cycle...")
    result = learn_from_trades(db.get_all_trades(limit=100))
    if result:
        print(f"[FBOT] Brain updated: {result['summary'][:80]}...")
    else:
        print("[FBOT] Not enough data to learn yet")
