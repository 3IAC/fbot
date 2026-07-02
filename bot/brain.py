import json
import requests
import bot.database as db
from bot.config import ANTHROPIC_API_KEY


def analyze_signal(instrument, indicators, recent_trades):
    if not ANTHROPIC_API_KEY:
        return _rule_based_signal(instrument, indicators)

    wins  = [t for t in recent_trades if t.get("pnl", 0) and t["pnl"] > 0]
    losses = [t for t in recent_trades if t.get("pnl", 0) and t["pnl"] <= 0]
    perf = f"Recent: {len(wins)} wins, {len(losses)} losses on {instrument}." if recent_trades else ""

    prompt = f"""You are an expert forex/gold scalp trader analyzing {instrument} on 5-minute bars.

Current market data:
- Price: {indicators.get('price')}
- RSI(14): {indicators.get('rsi')} (>70 overbought, <30 oversold)
- MA9: {indicators.get('ma9')}
- MA20: {indicators.get('ma20')}
- MA50: {indicators.get('ma50')}
- MACD: {indicators.get('macd')}
- Bollinger Upper/Mid/Lower: {indicators.get('bb_upper')} / {indicators.get('bb_mid')} / {indicators.get('bb_lower')}
- ATR(14): {indicators.get('atr')}
- 5-bar change: {indicators.get('price_change_5bar')}%
- Above MA20: {indicators.get('above_ma20')}
{perf}

This is a SCALP strategy: 0.5% stop loss, 1.5% take profit. Only buy on clear momentum setups.

Respond ONLY with valid JSON, no markdown:
{{
  "action": "buy" | "sell" | "hold",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentence explanation",
  "key_signal": "the single most important indicator driving this decision"
}}"""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=20
        )
        if r.status_code == 200:
            text = r.json()["content"][0]["text"].strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            db.log_signal(instrument, result["action"], result["confidence"],
                          result["reasoning"], indicators)
            return result
    except Exception as e:
        db.log_error("brain.analyze_signal", str(e))

    return _rule_based_signal(instrument, indicators)


def _rule_based_signal(instrument, indicators):
    rsi = indicators.get("rsi")
    above_ma20 = indicators.get("above_ma20")
    macd = indicators.get("macd")
    if rsi and rsi < 35 and above_ma20:
        return {"action": "buy", "confidence": 0.65,
                "reasoning": "RSI oversold, price above MA20.", "key_signal": "RSI"}
    elif rsi and rsi > 70:
        return {"action": "sell", "confidence": 0.60,
                "reasoning": "RSI overbought.", "key_signal": "RSI"}
    elif macd and macd > 0 and above_ma20:
        return {"action": "buy", "confidence": 0.55,
                "reasoning": "MACD positive momentum above MA20.", "key_signal": "MACD"}
    return {"action": "hold", "confidence": 0.50,
            "reasoning": "No clear scalp signal.", "key_signal": "none"}


def learn_from_trades(all_trades):
    closed = [t for t in all_trades if t.get("status") == "closed" and t.get("pnl") is not None]
    if len(closed) < 5 or not ANTHROPIC_API_KEY:
        return None
    wins = [t for t in closed if t["pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100
    trade_data = json.dumps([{
        "instrument": t["instrument"], "side": t["side"],
        "pnl_pct": t.get("pnl_pct"), "pnl": t["pnl"]
    } for t in closed[-20:]], indent=2)

    prompt = f"""Analyze forex scalping bot performance. Win rate: {win_rate:.1f}%.

Trades:
{trade_data}

Respond ONLY with valid JSON:
{{
  "summary": "2-3 sentence overall assessment",
  "winning_patterns": "what conditions led to winning trades",
  "losing_patterns": "what conditions led to losing trades",
  "adjustments": "specific strategy adjustments to improve performance"
}}"""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={"model": "claude-haiku-4-5", "max_tokens": 500,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30
        )
        if r.status_code == 200:
            text = r.json()["content"][0]["text"].strip()
            result = json.loads(text.replace("```json", "").replace("```", "").strip())
            db.log_brain(result["summary"], result["winning_patterns"],
                         result["adjustments"], win_rate)
            return result
    except Exception as e:
        db.log_error("brain.learn", str(e))
    return None
