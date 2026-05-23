import yfinance as yf
import pandas as pd
try:
    import pandas_ta as ta
except ImportError:
    ta = None
import requests
from datetime import datetime
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
TRUMP_API = "https://trumpcode.washinmura.jp"

WATCHLIST = [
    "NVDA","MSFT","AAPL","GOOGL","META","AMZN","TSLA",
    "AMD","AVGO","ORCL","CRM","ADBE","NFLX","TSM",
    "JPM","V","MA","UNH","LLY","WMT"
]

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
    for chunk in chunks:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown"
        }, timeout=10)

def get_trump_signal() -> dict:
    try:
        r = requests.get(f"{TRUMP_API}/api/signals", timeout=10)
        data = r.json()
        signals = data.get("signals", [])
        latest = signals[0] if signals else {}
        signal_type = latest.get("signal", "NEUTRAL")
        direction = latest.get("direction", "NEUTRAL")
        confidence = float(latest.get("confidence", 0.5))
        score = int(confidence * 15) if direction == "LONG" else -int(confidence * 15) if direction == "SHORT" else 0
        reasoning = [f"川普訊號：{direction} ({signal_type})"]
        if data.get("today_post_count", -1) == 0:
            score += 5
            reasoning.append("零貼文日加分")
        if "TARIFF" in str(signal_type).upper():
            score -= 8
            reasoning.append("關稅訊號降權")
        return {"score": score, "direction": direction, "confidence": confidence, "reasoning": reasoning}
    except Exception:
        return {"score": 0, "direction": "NEUTRAL", "confidence": 0, "reasoning": ["川普訊號略過"]}

def get_news_sentiment(ticker: str) -> dict:
    if not NEWS_API_KEY:
        return {"score": 0, "headlines": [], "count": 0}
    pos = ["beat","surge","record","growth","upgrade","buy","strong","profit","bullish","rally"]
    neg = ["miss","drop","fall","downgrade","sell","loss","bearish","cut","warn","risk"]
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": ticker,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 10,
                "apiKey": NEWS_API_KEY
            },
            timeout=10
        )
        articles = r.json().get("articles", [])
        score = 0
        headlines = []
        for art in articles[:5]:
            title = art.get("title", "").lower()
            score += sum(1 for kw in pos if kw in title)
            score -= sum(1 for kw in neg if kw in title)
            headlines.append(art.get("title", "")[:80])
        return {"score": score, "headlines": headlines[:3], "count": len(articles)}
    except Exception:
        return {"score": 0, "headlines": [], "count": 0}

def compute_rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(length).mean()
    loss = (-delta.clip(upper=0)).rolling(length).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))

def compute_atr(high, low, close, length=14):
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(length).mean()

def analyze_stock(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="3mo", interval="1d")
        if df.empty or len(df) < 30:
            return None

        if ta:
            df["RSI"] = ta.rsi(df["Close"], length=14)
            df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)
            df["EMA20"] = ta.ema(df["Close"], length=20)
            df["EMA50"] = ta.ema(df["Close"], length=50)
            macd_df = ta.macd(df["Close"])
            df["MACD_h"] = macd_df["MACDh_12_26_9"] if macd_df is not None else 0
        else:
            df["RSI"] = compute_rsi(df["Close"])
            df["ATR"] = compute_atr(df["High"], df["Low"], df["Close"])
            df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
            df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
            df["MACD_h"] = 0

        latest, prev = df.iloc[-1], df.iloc[-2]
        close = float(latest["Close"])
        rsi = float(latest["RSI"]) if not pd.isna(latest["RSI"]) else 50
        atr = float(latest["ATR"]) if not pd.isna(latest["ATR"]) else close * 0.02
        macd_h = float(latest["MACD_h"]) if not pd.isna(latest["MACD_h"]) else 0
        prev_m = float(prev["MACD_h"]) if not pd.isna(prev["MACD_h"]) else 0

        hist_1y = stock.history(period="1y")
        high_52w = float(hist_1y["High"].max()) if not hist_1y.empty else close
        pct_from_52w_high = (close - high_52w) / high_52w * 100

        info = stock.info
        pe = info.get("trailingPE")
        eps_g = info.get("earningsGrowth")
        sector = info.get("sector", "Unknown")

        tech_score, fund_score = 0, 0
        signals = []

        if 45 < rsi < 70:
            tech_score += 15
            signals.append(f"RSI {rsi:.0f} 健康")
        elif rsi >= 70:
            tech_score += 5
            signals.append(f"RSI {rsi:.0f} 偏熱")
        elif rsi < 35:
            tech_score += 10
            signals.append(f"RSI {rsi:.0f} 超賣")

        if float(latest["EMA20"]) > float(latest["EMA50"]):
            tech_score += 10
            signals.append("EMA20 > EMA50")

        if close > float(latest["EMA20"]):
            tech_score += 8
            signals.append("站上 EMA20")

        if macd_h > 0 and prev_m <= 0:
            tech_score += 7
            signals.append("MACD 金叉")
        elif macd_h > 0:
            tech_score += 4
            signals.append("MACD 正值")

        pct_5d = (close - float(df.iloc[-6]["Close"])) / float(df.iloc[-6]["Close"]) * 100 if len(df) >= 6 else 0
        if 1 < pct_5d < 10:
            tech_score += 5
            signals.append(f"近5日 +{pct_5d:.1f}%")

        avg_vol = df["Volume"].iloc[-21:-1].mean()
        vol_spike = float(latest["Volume"]) / avg_vol if avg_vol > 0 else 1
        if vol_spike >= 1.5:
            tech_score = min(tech_score + 5, 40)
            signals.append(f"量增 {vol_spike:.1f}x")

        if eps_g and eps_g > 0.15:
            fund_score += 15
            signals.append(f"EPS 年增 {eps_g*100:.0f}%")
        elif eps_g and eps_g > 0:
            fund_score += 8
            signals.append(f"EPS 年增 {eps_g*100:.0f}%")

        if pe and 0 < pe < 30:
            fund_score += 10
            signals.append(f"P/E {pe:.1f}")
        elif pe and 30 <= pe < 50:
            fund_score += 5
            signals.append(f"P/E {pe:.1f}")

        if pct_from_52w_high > -10:
            fund_score += 5
            signals.append(f"距52週高點 {pct_from_52w_high:.1f}%")

        stop_loss = close - 1.5 * atr
        stop_loss_pct = (stop_loss - close) / close * 100

        return {
            "ticker": ticker,
            "close": close,
            "rsi": rsi,
            "atr": atr,
            "tech_score": tech_score,
            "fund_score": fund_score,
            "total_score": tech_score + fund_score,
            "signals": signals,
            "stop_loss": stop_loss,
            "stop_loss_pct": stop_loss_pct,
            "sector": sector,
            "pct_5d": pct_5d,
            "pct_from_52w_high": pct_from_52w_high
        }
    except Exception:
        return None

def format_report(results, trump):
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    lines = [
        "📊 美股每日掃描報告",
        "━━━━━━━━━━━━━━━━━━",
        f"🗓 {now}（台灣時間）",
        f"📡 川普訊號：{trump['direction']}（信心 {trump['confidence']:.0%}）",
        *trump["reasoning"],
        "━━━━━━━━━━━━━━━━━━",
        ""
    ]

    for i, r in enumerate(results[:5], 1):
        lines.extend([
            f"#{i} {r['ticker']}｜評分 {r['total_score']}/100",
            f"現價 ${r['close']:.2f}｜RSI {r['rsi']:.0f}｜產業 {r['sector']}",
            "入場邏輯："
        ])
        for sig in r["signals"][:3]:
            lines.append(f"• {sig}")
        lines.extend([
            f"停損：${r['stop_loss']:.2f}（{r['stop_loss_pct']:.1f}%）",
            f"5日：{r['pct_5d']:+.1f}%｜距高點：{r['pct_from_52w_high']:.1f}%",
            "━━━━━━━━━━━━━━━━━━"
        ])

    lines.append("⚠️ 僅供參考，非投資建議")
    return "\n".join(lines)

def run_scan():
    trump = get_trump_signal()
    results = []
    for ticker in WATCHLIST:
        result = analyze_stock(ticker)
        if result and result["total_score"] >= 25:
            news = get_news_sentiment(ticker)
            news_score = max(-15, min(15, news["score"] * 3))
            result["total_score"] += trump["score"] + news_score
            results.append(result)
    results.sort(key=lambda x: x["total_score"], reverse=True)
    send_telegram(format_report(results, trump) if results else "📊 今日無達標標的")

if __name__ == "__main__":
    run_scan()
