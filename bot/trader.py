import json
from datetime import datetime, timezone, timedelta
import bot.database as db
import bot.oanda_client as oanda
from bot.brain import analyze_signal, learn_from_trades
from bot.indicators import get_all_indicators
from bot.config import (
    INSTRUMENTS, STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    MAX_OPEN_TRADES, DEFAULT_CONFIDENCE_THRESHOLD,
    UNITS_EUR_USD, UNITS_GBP_USD, UNITS_XAU_USD,
    MAX_TRADE_DURATION_MINUTES
)

_UNITS_MAP = {
    "EUR_USD": UNITS_EUR_USD,
    "GBP_USD": UNITS_GBP_USD,
    "XAU_USD": UNITS_XAU_USD,
}


def run_scan():
    """Scan all forex/gold instruments on M1 bars. Executes BUY and SELL signals."""
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
            candles = oanda.get_candles(instrument, granularity="M1", count=100)
            if not candles or len(candles) < 20:
                print(f"[FBOT] {instrument}: insufficient candle data")
                continue

            indicators = get_all_indicators(candles)
            db.save_snapshot(instrument, indicators.get("price"), indicators.get("rsi"),
                             indicators.get("ma20"), indicators.get("ma50"))

            inst_trades = [t for t in recent_db_trades if t["instrument"] == instrument]
            signal = analyze_signal(instrument, indicators, inst_trades)
            threshold = db.get_adaptive_threshold(instrument, DEFAULT_CONFIDENCE_THRESHOLD)

            action = signal["action"]
            conf = signal["confidence"]
            print(f"[FBOT] {instrument}: {action.upper()} ({conf:.0%}) "
                  f"threshold={threshold:.0%} — {signal['key_signal']}")

            # Execute both BUY and SELL if above threshold
            if action not in ("buy", "sell") or conf < threshold:
                continue

            price = indicators["price"]
            base_units = _UNITS_MAP.get(instrument, 1000)

            if action == "buy":
                units = base_units
                stop_loss   = round(price * (1 - STOP_LOSS_PCT), 5)
                take_profit = round(price * (1 + TAKE_PROFIT_PCT), 5)
            else:  # sell / short
                units = -base_units
                stop_loss   = round(price * (1 + STOP_LOSS_PCT), 5)
                take_profit = round(price * (1 - TAKE_PROFIT_PCT), 5)

            print(f"[FBOT] Placing {action.upper()} {abs(units)} {instrument} @ {price:.5f} "
                  f"SL={stop_loss:.5f} TP={take_profit:.5f}")

            result = oanda.place_order(instrument, units, stop_loss, take_profit)

            # Always log the full API response so we can debug failures
            print(f"[FBOT] ORDER RESPONSE: {json.dumps(result)[:500] if result else 'None/Error'}")

            if result:
                tx = result.get("orderFillTransaction", {})
                trade_id = tx.get("tradeOpened", {}).get("tradeID")
                fill_price = float(tx.get("price", price))
                db_id = db.log_trade(
                    instrument, action, units, fill_price, trade_id,
                    signal["reasoning"], stop_loss, take_profit
                )
                print(f"[FBOT] {action.upper()} PLACED {abs(units)} {instrument} @ {fill_price:.5f} "
                      f"| SL: {stop_loss:.5f} | TP: {take_profit:.5f} | db_id={db_id}")
            else:
                print(f"[FBOT] {instrument}: order FAILED — check errors table")

        except Exception as e:
            db.log_error(f"trader.{instrument}", str(e))
            print(f"[FBOT] EXCEPTION {instrument}: {e}")


def check_open_trades():
    """
    Exit monitor: reconcile open DB trades with OANDA.
    Force-close trades older than MAX_TRADE_DURATION_MINUTES.
    """
    open_db = db.get_open_trades()
    if not open_db:
        return

    oanda_open = {t["id"]: t for t in oanda.get_open_trades()}
    now = datetime.now(timezone.utc)
    max_age = timedelta(minutes=MAX_TRADE_DURATION_MINUTES)

    for trade in open_db:
        oanda_id = trade.get("oanda_trade_id")
        if not oanda_id:
            continue

        # Force-close if exceeded max duration
        opened_at = trade.get("opened_at")
        if opened_at:
            try:
                opened_dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
                if (now - opened_dt) > max_age:
                    age_min = int((now - opened_dt).total_seconds() // 60)
                    print(f"[FBOT] TIMEOUT {trade['instrument']} open {age_min}min — force closing")
                    close_result = oanda.close_trade(oanda_id)
                    print(f"[FBOT] CLOSE RESPONSE: {json.dumps(close_result)[:300] if close_result else 'None/Error'}")
                    # Use fill price from close response (reliable), fall back to live price
                    exit_price = None
                    if close_result:
                        tx = close_result.get("orderFillTransaction", {})
                        if tx.get("price"):
                            exit_price = float(tx["price"])
                    if not exit_price:
                        exit_price = oanda.get_price(trade["instrument"])
                    if exit_price:
                        db.close_trade(trade["id"], exit_price)
                        entry = trade["entry_price"]
                        side = trade.get("side", "buy")
                        pnl_pct = ((exit_price - entry) / entry * 100) * (1 if side == "buy" else -1)
                        outcome = "WIN" if pnl_pct > 0 else "LOSS"
                        print(f"[FBOT] TIMEOUT {outcome} {trade['instrument']} | {pnl_pct:+.2f}%")
                        _log_learning(trade["instrument"], trade, exit_price, pnl_pct)
                    continue
            except Exception as e:
                db.log_error("check_open.timeout", str(e))

        if oanda_id not in oanda_open:
            # Trade closed by TP or SL
            price = oanda.get_price(trade["instrument"])
            if price:
                db.close_trade(trade["id"], price)
                entry = trade["entry_price"]
                side = trade.get("side", "buy")
                pnl_pct = ((price - entry) / entry * 100) * (1 if side == "buy" else -1)
                outcome = "WIN" if pnl_pct > 0 else "LOSS"
                print(f"[FBOT] {outcome} {trade['instrument']} | "
                      f"entry={entry:.5f} exit={price:.5f} | {pnl_pct:+.2f}%")
                _log_learning(trade["instrument"], trade, price, pnl_pct)


def _log_learning(instrument, trade, exit_price, pnl_pct):
    closed = db.get_closed_trades_for_instrument(instrument, limit=20)
    if not closed:
        return
    wins = sum(1 for t in closed if t.get("pnl", 0) and t["pnl"] > 0)
    win_rate = wins / len(closed) if closed else 0
    new_threshold = db.get_adaptive_threshold(instrument, DEFAULT_CONFIDENCE_THRESHOLD)
    outcome = "WIN" if pnl_pct > 0 else "LOSS"
    detail = (f"win_rate={win_rate:.1%} over {len(closed)} trades | "
              f"pnl={pnl_pct:+.2f}% | threshold now={new_threshold:.2f}")
    db.log_learning_event(instrument, outcome, detail)
    print(f"[LEARN] {instrument}: {detail}")


def run_learn():
    print("[FBOT] Running learning cycle...")
    result = learn_from_trades(db.get_all_trades(limit=100))
    if result:
        print(f"[FBOT] Brain updated: {result['summary'][:80]}...")
    else:
        print("[FBOT] Not enough data to learn yet")
