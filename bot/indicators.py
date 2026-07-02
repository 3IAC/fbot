def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i-1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calculate_ma(prices, period):
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 6)


def calculate_macd(prices, fast=12, slow=26):
    if len(prices) < slow:
        return None, None
    def ema(data, p):
        k = 2 / (p + 1)
        v = data[0]
        for x in data[1:]:
            v = x * k + v * (1 - k)
        return v
    return round(ema(prices[-fast:], fast) - ema(prices[-slow:], slow), 6), None


def calculate_bollinger(prices, period=20, std_dev=2):
    if len(prices) < period:
        return None, None, None
    recent = prices[-period:]
    ma = sum(recent) / period
    std = (sum((p - ma) ** 2 for p in recent) / period) ** 0.5
    return round(ma, 6), round(ma + std_dev * std, 6), round(ma - std_dev * std, 6)


def calculate_atr(candles, period=14):
    """Average True Range — useful for forex volatility."""
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["h"]
        l = candles[i]["l"]
        prev_c = candles[i-1]["c"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return round(sum(trs[-period:]) / period, 6)


def get_all_indicators(candles):
    if not candles or len(candles) < 20:
        return {}
    closes = [c["c"] for c in candles]
    rsi   = calculate_rsi(closes)
    ma9   = calculate_ma(closes, 9)
    ma20  = calculate_ma(closes, 20)
    ma50  = calculate_ma(closes, 50) if len(closes) >= 50 else None
    macd, _ = calculate_macd(closes)
    bb_mid, bb_upper, bb_lower = calculate_bollinger(closes)
    atr   = calculate_atr(candles)
    price = closes[-1]
    price_change_5 = round((closes[-1] - closes[-5]) / closes[-5] * 100, 4) if len(closes) >= 5 else None
    return {
        "price": price,
        "rsi": rsi,
        "ma9": ma9,
        "ma20": ma20,
        "ma50": ma50,
        "macd": macd,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_mid": bb_mid,
        "atr": atr,
        "above_ma20": price > ma20 if ma20 else None,
        "above_ma50": price > ma50 if ma50 else None,
        "price_change_5bar": price_change_5,
    }
