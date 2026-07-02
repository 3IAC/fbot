import sqlite3
import json
import os
from datetime import datetime, timezone
from bot.config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument TEXT NOT NULL,
            side TEXT NOT NULL,
            units REAL NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            status TEXT DEFAULT 'open',
            oanda_trade_id TEXT,
            ai_reasoning TEXT,
            stop_loss REAL,
            take_profit REAL,
            opened_at TEXT NOT NULL,
            closed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument TEXT NOT NULL,
            action TEXT NOT NULL,
            confidence REAL,
            reasoning TEXT,
            indicators TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS brain_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary TEXT,
            patterns TEXT,
            adjustments TEXT,
            win_rate REAL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument TEXT,
            price REAL,
            rsi REAL,
            ma20 REAL,
            ma50 REAL,
            created_at TEXT NOT NULL
        );
        """)


def _now():
    return datetime.now(timezone.utc).isoformat()


def log_trade(instrument, side, units, entry_price, oanda_trade_id,
              ai_reasoning, stop_loss, take_profit):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO trades (instrument, side, units, entry_price, oanda_trade_id,
                                ai_reasoning, stop_loss, take_profit, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (instrument, side, units, entry_price, oanda_trade_id,
              ai_reasoning, stop_loss, take_profit, _now()))
        return cur.lastrowid


def close_trade(trade_id, exit_price, oanda_pnl=None):
    with get_conn() as conn:
        trade = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not trade:
            return
        pnl = oanda_pnl if oanda_pnl is not None else (exit_price - trade["entry_price"]) * trade["units"]
        pnl_pct = (exit_price - trade["entry_price"]) / trade["entry_price"] * 100
        conn.execute("""
            UPDATE trades SET exit_price=?, pnl=?, pnl_pct=?, status='closed', closed_at=?
            WHERE id=?
        """, (exit_price, round(pnl, 6), round(pnl_pct, 4), _now(), trade_id))


def get_open_trades():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status='open' ORDER BY opened_at DESC"
        ).fetchall()]


def get_all_trades(limit=100):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", (limit,)
        ).fetchall()]


def get_closed_trades_for_instrument(instrument, limit=50):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE instrument=? AND status='closed' ORDER BY closed_at DESC LIMIT ?",
            (instrument, limit)
        ).fetchall()]


def get_adaptive_threshold(instrument, default=0.35):
    trades = get_closed_trades_for_instrument(instrument, limit=50)
    if len(trades) < 10:
        return default
    wins = [t for t in trades if t.get("pnl", 0) and t["pnl"] > 0]
    win_rate = len(wins) / len(trades)
    if win_rate >= 0.55:
        return max(0.30, default - 0.02)
    elif win_rate < 0.40:
        return min(0.60, default + 0.05)
    return default


def log_signal(instrument, action, confidence, reasoning, indicators):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO signals (instrument, action, confidence, reasoning, indicators, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (instrument, action, confidence, reasoning, json.dumps(indicators), _now()))


def log_brain(summary, patterns, adjustments, win_rate):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO brain_log (summary, patterns, adjustments, win_rate, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (summary, patterns, adjustments, win_rate, _now()))


def log_error(source, message):
    with get_conn() as conn:
        conn.execute("INSERT INTO errors (source, message, created_at) VALUES (?, ?, ?)",
                     (source, str(message)[:2000], _now()))
    print(f"[ERROR] {source}: {message}")


def save_snapshot(instrument, price, rsi, ma20, ma50):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO snapshots (instrument, price, rsi, ma20, ma50, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (instrument, price, rsi, ma20, ma50, _now()))


def get_stats():
    with get_conn() as conn:
        trades = conn.execute("SELECT * FROM trades WHERE status='closed'").fetchall()
        if not trades:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0}
        wins = [t for t in trades if t["pnl"] and t["pnl"] > 0]
        total_pnl = sum(t["pnl"] for t in trades if t["pnl"])
        return {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(trades) - len(wins),
            "win_rate": round(len(wins) / len(trades) * 100, 1),
            "total_pnl": round(total_pnl, 4),
        }


def get_latest_brain():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM brain_log ORDER BY created_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None


def get_recent_signals(limit=20):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()]
