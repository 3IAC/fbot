import os
from dotenv import load_dotenv
load_dotenv()

OANDA_API_KEY    = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENV        = os.getenv("OANDA_ENV", "practice")   # "practice" or "live"

if OANDA_ENV == "live":
    OANDA_BASE_URL = "https://api-fxtrade.oanda.com"
    OANDA_STREAM_URL = "https://stream-fxtrade.oanda.com"
else:
    OANDA_BASE_URL = "https://api-fxpractice.oanda.com"
    OANDA_STREAM_URL = "https://stream-fxpractice.oanda.com"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Instruments: EUR/USD, GBP/USD, XAU/USD (gold)
INSTRUMENTS = ["EUR_USD", "GBP_USD", "XAU_USD"]

# Scalping parameters
UNITS_EUR_USD  = 1000     # 1 micro lot EUR/USD
UNITS_GBP_USD  = 1000
UNITS_XAU_USD  = 1        # 1 oz gold

STOP_LOSS_PCT   = 0.005   # 0.5%
TAKE_PROFIT_PCT = 0.015   # 1.5%
MAX_OPEN_TRADES = 10

SCAN_INTERVAL_MINUTES = 5
LEARN_INTERVAL_HOURS  = 6
DEFAULT_CONFIDENCE_THRESHOLD = 0.35

DB_PATH = os.getenv("DB_PATH", "fbot.db")
DASHBOARD_PORT = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "5000")))
