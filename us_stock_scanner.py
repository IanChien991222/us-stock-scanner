import os
import math
import textwrap
from datetime import datetime

import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
TRUMP_API = "https://trumpcode.washinmura.jp"

WATCHLIST = [
    "NVDA","MSFT","AAPL","GOOGL","META","AMZN","TSLA",
    "AMD","AVGO","ORCL","CRM","ADBE","NFLX","TSM",
    "JPM","V","MA","UNH","LLY","WMT"
]

OUT_DIR = "output_cards"
CARD_W = 1280
CARD_H = 720

BG = "#0B1220"
PANEL = "#121A2B"
PANEL_2 = "#182235"
TEXT = "#EAF2FF"
MUTED = "#94A3B8"
ACCENT = "#4F8CFF"
GREEN = "#22C55E"
YELLOW = "#F59E0B"
RED = "#EF4444"
LINE = "#22304A"

def get_font(size=32, bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc"
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()

FONT_XL = get_font(52, True)
FONT_LG = get_font(34, True)
FONT_MD = get_font(26, False)
FONT_SM = get_font(22, False)
FONT_XS = get_font(18, False)

def send_telegram_text(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=20)

def send_telegram_photos(image_paths, caption=""):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("未設定 Telegram，圖片已生成：")
        for p in image_paths:
            print(p)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    for i, path in enumerate(image_paths):
        data = {"chat_id": TELEGRAM_CHAT_ID}
        if i == 0 and caption:
            data["caption"] = caption
        with open(path, "rb") as f:
            files = {"photo": f}
            resp = requests.post(url, data=data, files=files, timeout=60)
            try:
                j = resp.json()
                if not j.get("ok"):
                    print("Telegram 發圖失敗:", j)
            except Exception:
                print("Telegram 發圖失敗:", resp.text)

def get_trump_signal() -> dict:
    try:
        r = requests.get(f"{TRUMP_API}/api/signals", timeout=15)
        data = r.json()
        signals = data.get("signals", [])
        latest = signals[0] if signals else {}
        signal_type = latest.get("signal", "NEUTRAL")
        direction = latest.get("direction", "NEUTRAL")
        confidence = float(latest.get("confidence", 0.5))
        score = int(confidence * 15) if direction == "LONG" else -int(confidence * 15) if direction == "SHORT" else 0
        reasoning = [f"Trump signal: {direction} ({signal_type})"]
        if data.get("today_post_count", -1) == 0:
            score += 5
            reasoning.append("Zero-post day bonus")
        if "TARIFF" in str(signal_type).upper():
            score -= 8
            reasoning.append("Tariff risk downgrade")
        return {
            "score": score,
            "direction": direction,
            "confidence": confidence,
            "reasoning": reasoning
        }
    except Exception:
        return {
            "score": 0,
            "direction": "NEUTRAL",
            "confidence": 0,
            "reasoning": ["Trump signal skipped"]
        }

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
            timeout=15
        )
        articles = r.json().get("articles", [])
        score = 0
        headlines = []
        for art in articles[:5]:
            title = art.get("title", "").lower()
            score += sum(1 for kw in pos if kw in title)
            score -= sum(1 for kw in neg if kw in title)
            headlines.append(art.get("title", "")[:90])
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

def classify_action(result):
    score = result["total_score"]
    rsi = result["rsi"]
    pct_from_high = result["pct_from_52w_high"]

    if score >= 70 and rsi < 68:
        return "優先研究｜可分批布局"
    if score >= 60 and rsi < 72:
        return "次優先｜等回檔再看"
    if rsi >= 70:
        return "觀察名單｜偏熱不追"
    if pct_from_high < -18:
        return "觀察名單｜等待轉強"
    return "保留觀察｜風險偏高"

def analyze_stock(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="3mo", interval="1d")
        if df.empty or len(df) < 30:
            return None

        df["RSI"] = compute_rsi(df["Close"])
        df["ATR"] = compute_atr(df["High"], df["Low"], df["Close"])
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

        latest = df.iloc[-1]
        close = float(latest["Close"])
        rsi = float(latest["RSI"]) if not pd.isna(latest["RSI"]) else 50
        atr = float(latest["ATR"]) if not pd.isna(latest["ATR"]) else close * 0.02

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
            signals.append(f"RSI {rsi:.0f} 在健康區間")
        elif rsi >= 70:
            tech_score += 5
            signals.append(f"RSI {rsi:.0f} 偏熱")
        elif rsi < 35:
            tech_score += 10
            signals.append(f"RSI {rsi:.0f} 超賣反彈區")

        if float(latest["EMA20"]) > float(latest["EMA50"]):
            tech_score += 10
            signals.append("EMA20 站上 EMA50，多頭排列")

        if close > float(latest["EMA20"]):
            tech_score += 8
            signals.append("現價站上 EMA20")

        pct_5d = (close - float(df.iloc[-6]["Close"])) / float(df.iloc[-6]["Close"]) * 100 if len(df) >= 6 else 0
        if 1 < pct_5d < 10:
            tech_score += 5
            signals.append(f"近 5 日漲幅 {pct_5d:+.1f}%")

        avg_vol = df["Volume"].iloc[-21:-1].mean()
        vol_spike = float(latest["Volume"]) / avg_vol if avg_vol > 0 else 1
        if vol_spike >= 1.5:
            tech_score = min(tech_score + 5, 40)
            signals.append(f"成交量放大 {vol_spike:.1f}x")

        if eps_g and eps_g > 0.15:
            fund_score += 15
            signals.append(f"EPS 年增 {eps_g*100:.0f}%")
        elif eps_g and eps_g > 0:
            fund_score += 8
            signals.append(f"EPS 年增 {eps_g*100:.0f}%")

        if pe and 0 < pe < 30:
            fund_score += 10
            signals.append(f"P/E {pe:.1f} 屬合理估值")
        elif pe and 30 <= pe < 50:
            fund_score += 5
            signals.append(f"P/E {pe:.1f} 偏高但可接受")

        if pct_from_52w_high > -10:
            fund_score += 5
            signals.append(f"距 52 週高點僅 {pct_from_52w_high:.1f}%")

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
            "signals": signals[:5],
            "stop_loss": stop_loss,
            "stop_loss_pct": stop_loss_pct,
            "sector": sector,
            "pct_5d": pct_5d,
            "pct_from_52w_high": pct_from_52w_high,
        }
    except Exception as e:
        print(f"分析 {ticker} 失敗: {e}")
        return None

def rounded_box(draw, xy, fill, radius=24, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def draw_text(draw, xy, text, font, fill=TEXT):
    draw.text(xy, text, font=font, fill=fill)

def metric_color(value, good_high=True, warn_threshold=None):
    if warn_threshold is None:
        return GREEN
    if good_high:
        if value >= warn_threshold:
            return GREEN
        return YELLOW
    else:
        if value <= warn_threshold:
            return GREEN
        return YELLOW

def make_canvas():
    img = Image.new("RGB", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(img)
    return img, draw

def save_overview_card(results, trump):
    img, draw = make_canvas()

    rounded_box(draw, (40, 40, CARD_W-40, CARD_H-40), PANEL, radius=28, outline=LINE, width=2)
    draw_text(draw, (70, 70), "US STOCK DAILY SCAN", FONT_XL)
    draw_text(draw, (70, 140), datetime.now().strftime("%Y/%m/%d %H:%M"), FONT_SM, MUTED)

    rounded_box(draw, (70, 190, 550, 320), PANEL_2, radius=22)
    draw_text(draw, (95, 215), "Market Context", FONT_MD, MUTED)
    draw_text(draw, (95, 255), f"Trump Signal: {trump['direction']}", FONT_LG)
    draw_text(draw, (95, 295), f"Confidence: {trump['confidence']:.0%}", FONT_SM, MUTED)

    rounded_box(draw, (580, 190, 1210, 320), PANEL_2, radius=22)
    draw_text(draw, (605, 215), "Today's Bias", FONT_MD, MUTED)
    top_score = results[0]["total_score"] if results else 0
    bias = "偏進攻" if top_score >= 70 else "中性偏多" if top_score >= 60 else "保守觀察"
    draw_text(draw, (605, 255), bias, FONT_LG)
    draw_text(draw, (605, 295), "Top ideas ranked by blended score", FONT_SM, MUTED)

    draw_text(draw, (70, 370), "Top Picks", FONT_LG)
    y = 430
    for i, r in enumerate(results[:5], 1):
        rounded_box(draw, (70, y, 1210, y+70), PANEL_2, radius=18)
        draw_text(draw, (95, y+20), f"#{i}", FONT_MD, MUTED)
        draw_text(draw, (160, y+18), r["ticker"], FONT_MD)
        draw_text(draw, (320, y+18), f"Score {r['total_score']}/100", FONT_MD, ACCENT)
        draw_text(draw, (620, y+18), f"Price ${r['close']:.2f}", FONT_MD)
        draw_text(draw, (900, y+18), classify_action(r), FONT_MD, GREEN if "布局" in classify_action(r) else YELLOW)
        y += 84

    draw_text(draw, (70, 660), "For research only — not investment advice", FONT_XS, MUTED)

    path = os.path.join(OUT_DIR, "00_overview.png")
    img.save(path)
    return path

def wrap_lines(text, width=24):
    return textwrap.wrap(text, width=width)

def save_stock_card(rank, result):
    img, draw = make_canvas()
    rounded_box(draw, (40, 40, CARD_W-40, CARD_H-40), PANEL, radius=28, outline=LINE, width=2)

    draw_text(draw, (70, 70), f"#{rank} {result['ticker']}", FONT_XL)
    draw_text(draw, (1030, 82), f"{result['total_score']}/100", FONT_LG, ACCENT)

    rounded_box(draw, (70, 170, 390, 300), PANEL_2, radius=22)
    draw_text(draw, (95, 195), "Price", FONT_SM, MUTED)
    draw_text(draw, (95, 235), f"${result['close']:.2f}", FONT_LG)

    rounded_box(draw, (430, 170, 750, 300), PANEL_2, radius=22)
    draw_text(draw, (455, 195), "Stop Loss", FONT_SM, MUTED)
    draw_text(draw, (455, 235), f"${result['stop_loss']:.2f}", FONT_LG)

    rounded_box(draw, (790, 170, 1110, 300), PANEL_2, radius=22)
    draw_text(draw, (815, 195), "RSI", FONT_SM, MUTED)
    rsi_color = GREEN if result["rsi"] < 68 else YELLOW
    draw_text(draw, (815, 235), f"{result['rsi']:.0f}", FONT_LG, rsi_color)

    rounded_box(draw, (70, 330, 540, 510), PANEL_2, radius=22)
    draw_text(draw, (95, 355), "Snapshot", FONT_MD, MUTED)
    draw_text(draw, (95, 400), f"Sector: {result['sector']}", FONT_SM)
    draw_text(draw, (95, 435), f"5D Change: {result['pct_5d']:+.1f}%", FONT_SM)
    draw_text(draw, (95, 470), f"From 52W High: {result['pct_from_52w_high']:.1f}%", FONT_SM)

    rounded_box(draw, (570, 330, 1210, 590), PANEL_2, radius=22)
    draw_text(draw, (595, 355), "Why It Made the List", FONT_MD, MUTED)
    y = 400
    for sig in result["signals"][:3]:
        for line in wrap_lines(f"• {sig}", 34):
            draw_text(draw, (595, y), line, FONT_SM)
            y += 34
        y += 8

    rounded_box(draw, (70, 540, 1210, 650), fill="#10233D", radius=22, outline=ACCENT, width=2)
    draw_text(draw, (95, 572), "Decision", FONT_SM, MUTED)
    draw_text(draw, (95, 605), classify_action(result), FONT_LG, ACCENT)

    draw_text(draw, (70, 670), "For research only — not investment advice", FONT_XS, MUTED)

    path = os.path.join(OUT_DIR, f"{rank:02d}_{result['ticker']}.png")
    img.save(path)
    return path

def generate_report_images(results, trump):
    os.makedirs(OUT_DIR, exist_ok=True)
    paths = [save_overview_card(results, trump)]
    for i, r in enumerate(results[:5], 1):
        paths.append(save_stock_card(i, r))
    return paths

def build_caption(results, trump):
    if not results:
        return "今日無達標標的。"
    top = results[0]
    return (
        f"📊 美股每日掃描完成\n"
        f"Top Pick: {top['ticker']} ({top['total_score']}/100)\n"
        f"市場狀態: {trump['direction']} | 信心 {trump['confidence']:.0%}\n"
        f"模式: 多張儀表板卡片"
    )

def run_scan():
    trump = get_trump_signal()
    results = []

    for ticker in WATCHLIST:
        result = analyze_stock(ticker)
        if result and result["total_score"] >= 25:
            news = get_news_sentiment(ticker)
            news_score = max(-15, min(15, news["score"] * 3))
            result["total_score"] += trump["score"] + news_score
            result["news"] = news
            results.append(result)

    results.sort(key=lambda x: x["total_score"], reverse=True)

    if not results:
        send_telegram_text("📊 今日無達標標的，建議觀察為主。")
        return

    image_paths = generate_report_images(results, trump)
    caption = build_caption(results, trump)
    send_telegram_photos(image_paths, caption=caption)
    print("已生成圖片：")
    for p in image_paths:
        print(p)

if __name__ == "__main__":
    run_scan()