"""
FBOT — Autonomous Forex/Gold scalping bot using OANDA practice API.
Trades EUR/USD, GBP/USD, XAU/USD on 5-minute bars 24/7.
"""
import sys
import os
import time
import signal
import threading
from datetime import datetime, timezone

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

import bot.database as db
from bot.trader import run_scan, run_learn, check_open_trades
from bot.config import SCAN_INTERVAL_MINUTES, LEARN_INTERVAL_HOURS, DASHBOARD_PORT, OANDA_ENV

_shutdown = threading.Event()


def scan_job():
    try:
        run_scan()
    except Exception as e:
        db.log_error("main.scan_job", str(e))


def exit_job():
    try:
        check_open_trades()
    except Exception as e:
        db.log_error("main.exit_job", str(e))


def learn_job():
    try:
        run_learn()
    except Exception as e:
        db.log_error("main.learn_job", str(e))


def start_dashboard():
    try:
        from dashboard.app import app
        port = int(os.environ.get("PORT", DASHBOARD_PORT))
        print(f"[FBOT] Dashboard starting on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        db.log_error("main.dashboard", str(e))


def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║           FBOT — Forex & Gold Scalping Bot               ║
║      EUR/USD · GBP/USD · XAU/USD  ·  24/7 OANDA         ║
╚══════════════════════════════════════════════════════════╝
""")
    mode = "PRACTICE (paper)" if OANDA_ENV == "practice" else "⚠️  LIVE"
    print(f"Mode: {mode}")
    print(f"Scan interval: every {SCAN_INTERVAL_MINUTES} minutes")
    print()

    db.init_db()

    scheduler = BackgroundScheduler(
        executors={"default": ThreadPoolExecutor(4)},
        timezone="UTC"
    )
    scheduler.add_job(scan_job, "interval", minutes=SCAN_INTERVAL_MINUTES,
                      id="scanner", next_run_time=datetime.now(timezone.utc))
    scheduler.add_job(exit_job, "interval", minutes=2, id="exit_monitor")
    scheduler.add_job(learn_job, "interval", hours=LEARN_INTERVAL_HOURS, id="learner")
    scheduler.start()
    print("[FBOT] Scheduler started. First scan running now...")

    dash_thread = threading.Thread(target=start_dashboard, daemon=True)
    dash_thread.start()

    def _handle_signal(sig, frame):
        print("\n[FBOT] Shutdown signal received")
        _shutdown.set()
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while not _shutdown.is_set():
        time.sleep(5)


if __name__ == "__main__":
    main()
