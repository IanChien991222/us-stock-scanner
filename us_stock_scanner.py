import os
import re
import math
import textwrap
from datetime import datetime
from zoneinfo import ZoneInfo

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

OUT_DIR = "output_cards"
TZ = ZoneInfo("Asia/Taipei")

CARD_W = 1600
CARD_H = 900

BG = "#08101E"
PANEL = "#0F172A"
PANEL_2 = "#14213A"
PANEL_3 = "#0D1B30"
TEXT = "#EAF2FF"
MUTED = "#94A3B8"
ACCENT = "#60A5FA"
ACCENT_2 = "#38BDF8"
GREEN = "#22C55E"
YELLOW = "#F59E0B"
RED = "#EF4444"
LINE = "#22304A"
WHITE = "#FFFFFF"


def get_font(size=28, bold=False):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Bold.otf" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


FONT_XXL = get_font(72, True)
FONT_XL = get_font(56, True)
FONT_LG = get_font(40, True)
FONT_MD = get_font(30, False)
FONT_SM = get_font(24, False)
FONT_XS = get_font(20, False)
FONT_XXS = get_font(16, False)


def send_telegram_text(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=20)
    except Exception as e:
        print(f"Telegram 文字訊息發送失敗: {e}")
        print(message)


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
        try:
            with open(path, "rb") as f:
                resp = requests.post(url, data=data, files={"photo": f}, timeout=60)
            try:
                result = resp.json()
                if not result.get("ok"):
                    print("Telegram 發圖失敗:", result)
            except Exception:
                print("Telegram 發圖失敗:", resp.text)
        except Exception as e:
            print(f"Telegram 圖片發送失敗 {path}: {e}")


def get_trump_signal():
    try:
        r = requests.get(f"{TRUMP_API}/api/signals", timeout=15)
        data = r.json()
        signals = data.get("signals", [])
        latest = signals[0] if signals else {}
        signal_type = latest.get("signal", "NEUTRAL")
        direction = latest.get("direction", "NEUTRAL")
        confidence = float(latest.get("confidence", 0.5))
        score = 0
        if direction == "LONG":
            score = int(confidence * 10)
        elif direction == "SHORT":
            score = -int(confidence * 10)

        reasoning = [f"Trump signal: {direction} ({signal_type})"]
        if data.get("today_post_count", -1) == 0:
            score += 3
            reasoning.append("Zero-post day bonus")
        if "TARIFF" in str(signal_type).upper():
            score -= 5
            reasoning.append("Tariff risk downgrade")

        return {
            "score": score,
            "direction": direction,
            "confidence": confidence,
            "reasoning": reasoning,
        }
    except Exception:
        return {
            "score": 0,
            "direction": "NEUTRAL",
            "confidence": 0,
            "reasoning": ["Trump signal skipped"],
        }


def get_news_sentiment(ticker: str):
    if not NEWS_API_KEY:
        return {"score": 0, "headlines": [], "count": 0}

    pos = ["beat", "surge", "record", "growth", "upgrade", "buy", "strong", "profit", "bullish", "rally"]
    neg = ["miss", "drop", "fall", "downgrade", "sell", "loss", "bearish", "cut", "warn", "risk"]

    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": ticker,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 8,
                "apiKey": NEWS_API_KEY,
            },
            timeout=15,
        )
        articles = r.json().get("articles", [])
        score = 0
        headlines = []
        for art in articles[:5]:
            title = art.get("title", "").lower()
            score += sum(1 for kw in pos if kw in title)
            score -= sum(1 for kw in neg if kw in title)
            headlines.append(art.get("title", "")[:88])
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
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(length).mean()


def rounded_box(draw, xy, fill, radius=28, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_text(draw, xy, text, font, fill=TEXT):
    draw.text(xy, text, font=font, fill=fill)


def wrap_lines(text, width=28):
    return textwrap.wrap(text, width=width)


def score_to_color(score):
    if score >= 74:
        return GREEN
    if score >= 60:
        return YELLOW
    return MUTED


def classify_action(result):
    score = result["total_score"]
    rsi = result["rsi"]
    setup = result["setup_type"]
    dist = result["pct_from_52w_high"]

    if setup == "Breakout" and score >= 68 and rsi < 70:
        return "突破候選｜可追蹤進場點"
    if setup == "Pullback" and score >= 62 and rsi < 68:
        return "回檔承接｜等靠近 EMA20"
    if setup == "Momentum" and score >= 62 and rsi < 72:
        return "趨勢延續｜可續強觀察"
    if rsi >= 72:
        return "過熱排除｜不追價"
    if dist < -18:
        return "弱勢觀察｜等待轉強"
    return "保留名單｜需更多催化"


def get_setup_type(close, ema20, ema50, rsi, pct_5d, pct_from_52w_high, vol_ratio):
    if close > ema20 > ema50 and -8 <= pct_from_52w_high <= -1 and 48 <= rsi <= 68 and vol_ratio >= 1.1:
        return "Breakout"
    if ema20 > ema50 and close >= ema20 * 0.985 and 42 <= rsi <= 60:
        return "Pullback"
    if close > ema20 and ema20 > ema50 and pct_5d > 2 and 50 <= rsi <= 70:
        return "Momentum"
    if rsi >= 72:
        return "Overheat"
    return "Neutral"


def fetch_us_universe():
    sources = [
        ("https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt", "nasdaq"),
        ("https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt", "other"),
    ]
    symbols = []

    for url, source in sources:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        lines = [x.strip() for x in r.text.splitlines() if x.strip()]
        header = lines[0].split("|")
        rows = [line.split("|") for line in lines[1:] if "File Creation Time" not in line]
        df = pd.DataFrame(rows, columns=header)

        if source == "nasdaq":
            df = df.rename(columns={"Symbol": "Ticker", "ETF": "ETF", "Test Issue": "TestIssue"})
        else:
            df = df.rename(columns={"ACT Symbol": "Ticker", "ETF": "ETF", "Test Issue": "TestIssue"})

        df = df[df["Ticker"].notna()]
        df["Ticker"] = df["Ticker"].astype(str).str.strip()

        if "ETF" in df.columns:
            df = df[df["ETF"] == "N"]
        if "TestIssue" in df.columns:
            df = df[df["TestIssue"] == "N"]

        df = df[df["Ticker"].str.match(r"^[A-Z\.]+$", na=False)]
        df = df[~df["Ticker"].str.contains(r"\$", regex=True, na=False)]
        df = df[~df["Ticker"].str.contains(r"\^", regex=True, na=False)]

        symbols.extend(df["Ticker"].tolist())

    deduped = sorted(set(symbols))
    return deduped


def basic_prefilter(tickers, limit=700):
    passed = []
    batch_size = 80

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.download(
                tickers=batch,
                period="1mo",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
        except Exception:
            continue

        for ticker in batch:
            try:
                if data.empty:
                    continue

                if isinstance(data.columns, pd.MultiIndex):
                    if ticker not in data.columns.get_level_values(0):
                        continue
                    tdf = data[ticker].dropna()
                else:
                    tdf = data.dropna()

                if len(tdf) < 15:
                    continue

                close = float(tdf["Close"].iloc[-1])
                avg_vol = float(tdf["Volume"].tail(20).mean())
                dollar_vol = close * avg_vol

                if close < 8:
                    continue
                if avg_vol < 500_000:
                    continue
                if dollar_vol < 15_000_000:
                    continue

                passed.append(ticker)
            except Exception:
                continue

        if len(passed) >= limit:
            break

    return sorted(set(passed))[:limit]


def analyze_stock(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo", interval="1d", auto_adjust=False)
        if df.empty or len(df) < 60:
            return None

        df["RSI"] = compute_rsi(df["Close"])
        df["ATR"] = compute_atr(df["High"], df["Low"], df["Close"])
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["AVG20V"] = df["Volume"].rolling(20).mean()

        latest = df.iloc[-1]
        close = float(latest["Close"])
        rsi = float(latest["RSI"]) if not pd.isna(latest["RSI"]) else 50
        atr = float(latest["ATR"]) if not pd.isna(latest["ATR"]) else close * 0.02
        ema20 = float(latest["EMA20"])
        ema50 = float(latest["EMA50"])
        avg20v = float(latest["AVG20V"]) if not pd.isna(latest["AVG20V"]) else 0
        volume = float(latest["Volume"])
        vol_ratio = volume / avg20v if avg20v > 0 else 1

        hist_1y = stock.history(period="1y", auto_adjust=False)
        high_52w = float(hist_1y["High"].max()) if not hist_1y.empty else close
        low_52w = float(hist_1y["Low"].min()) if not hist_1y.empty else close
        pct_from_52w_high = (close - high_52w) / high_52w * 100 if high_52w else 0
        pct_above_52w_low = (close - low_52w) / low_52w * 100 if low_52w else 0

        pct_5d = 0
        pct_20d = 0
        if len(df) >= 6:
            pct_5d = (close - float(df.iloc[-6]["Close"])) / float(df.iloc[-6]["Close"]) * 100
        if len(df) >= 21:
            pct_20d = (close - float(df.iloc[-21]["Close"])) / float(df.iloc[-21]["Close"]) * 100

        info = stock.info
        pe = info.get("trailingPE")
        eps_g = info.get("earningsGrowth")
        rev_g = info.get("revenueGrowth")
        sector = info.get("sector", "Unknown")
        market_cap = info.get("marketCap", 0)

        setup_type = get_setup_type(close, ema20, ema50, rsi, pct_5d, pct_from_52w_high, vol_ratio)

        tech_score = 0
        fund_score = 0
        setup_bonus = 0
        signals = []

        if 45 <= rsi <= 68:
            tech_score += 16
            signals.append(f"RSI {rsi:.0f} 位於健康區間")
        elif 68 < rsi < 72:
            tech_score += 8
            signals.append(f"RSI {rsi:.0f} 偏熱但未失控")
        elif rsi < 40:
            tech_score += 6
            signals.append(f"RSI {rsi:.0f} 處於偏弱/反彈區")

        if close > ema20:
            tech_score += 8
            signals.append("現價站上 EMA20")
        if ema20 > ema50:
            tech_score += 12
            signals.append("EMA20 上穿 EMA50，多頭結構")
        if 1 <= pct_5d <= 9:
            tech_score += 6
            signals.append(f"近 5 日漲幅 {pct_5d:+.1f}%")
        if 3 <= pct_20d <= 18:
            tech_score += 6
            signals.append(f"近 20 日趨勢 {pct_20d:+.1f}%")
        if vol_ratio >= 1.3:
            tech_score += 6
            signals.append(f"量能放大 {vol_ratio:.1f}x")
        if -10 <= pct_from_52w_high <= -1:
            tech_score += 6
            signals.append(f"接近 52 週高點 {pct_from_52w_high:.1f}%")

        if eps_g and eps_g > 0.15:
            fund_score += 12
            signals.append(f"EPS 年增 {eps_g*100:.0f}%")
        elif eps_g and eps_g > 0:
            fund_score += 6
            signals.append(f"EPS 年增 {eps_g*100:.0f}%")

        if rev_g and rev_g > 0.10:
            fund_score += 8
            signals.append(f"營收成長 {rev_g*100:.0f}%")

        if pe and 0 < pe < 35:
            fund_score += 8
            signals.append(f"P/E {pe:.1f} 仍可接受")
        elif pe and 35 <= pe < 60:
            fund_score += 4
            signals.append(f"P/E {pe:.1f} 偏高但仍可追蹤")

        if market_cap and market_cap > 10_000_000_000:
            fund_score += 4

        if setup_type == "Breakout":
            setup_bonus += 12
        elif setup_type == "Pullback":
            setup_bonus += 10
        elif setup_type == "Momentum":
            setup_bonus += 10
        elif setup_type == "Overheat":
            setup_bonus -= 8

        stop_loss = max(close - 1.5 * atr, ema20 * 0.97)
        stop_loss_pct = (stop_loss - close) / close * 100

        total_score = tech_score + fund_score + setup_bonus

        return {
            "ticker": ticker,
            "pool": "US Universe",
            "close": close,
            "rsi": rsi,
            "atr": atr,
            "ema20": ema20,
            "ema50": ema50,
            "tech_score": tech_score,
            "fund_score": fund_score,
            "setup_bonus": setup_bonus,
            "total_score": total_score,
            "signals": signals[:6],
            "stop_loss": stop_loss,
            "stop_loss_pct": stop_loss_pct,
            "sector": sector,
            "pct_5d": pct_5d,
            "pct_20d": pct_20d,
            "pct_from_52w_high": pct_from_52w_high,
            "pct_above_52w_low": pct_above_52w_low,
            "setup_type": setup_type,
        }
    except Exception as e:
        print(f"分析 {ticker} 失敗: {e}")
        return None


def make_canvas():
    img = Image.new("RGB", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(img)
    return img, draw


def save_overview_card(results, trump, grouped, universe_size, prefiltered_size):
    img, draw = make_canvas()

    rounded_box(draw, (32, 32, CARD_W - 32, CARD_H - 32), PANEL, radius=34, outline=LINE, width=2)
    draw_text(draw, (70, 60), "US STOCK UNIVERSE SCAN", FONT_XXL)
    draw_text(draw, (72, 140), datetime.now(TZ).strftime("%Y/%m/%d %H:%M 台北時間"), FONT_SM, MUTED)

    rounded_box(draw, (70, 200, 500, 370), PANEL_2, radius=28)
    draw_text(draw, (100, 230), "市場訊號", FONT_SM, MUTED)
    draw_text(draw, (100, 280), f"Trump: {trump['direction']}", FONT_LG)
    draw_text(draw, (100, 330), f"Confidence {trump['confidence']:.0%}", FONT_SM, MUTED)

    rounded_box(draw, (540, 200, 980, 370), PANEL_2, radius=28)
    draw_text(draw, (570, 230), "掃描規模", FONT_SM, MUTED)
    draw_text(draw, (570, 280), f"Universe {universe_size}", FONT_LG)
    draw_text(draw, (570, 330), f"Prefilter {prefiltered_size}", FONT_SM, MUTED)

    rounded_box(draw, (1020, 200, 1530, 370), PANEL_2, radius=28)
    draw_text(draw, (1050, 230), "今日節奏", FONT_SM, MUTED)
    top_score = results[0]["total_score"] if results else 0
    bias = "偏進攻" if top_score >= 72 else "中性偏多" if top_score >= 60 else "保守觀察"
    draw_text(draw, (1050, 280), bias, FONT_LG)
    draw_text(draw, (1050, 330), "Breakout / Pullback / Momentum", FONT_SM, MUTED)

    sections = [
        ("突破候選", grouped["Breakout"][:2]),
        ("回檔承接", grouped["Pullback"][:2]),
        ("趨勢延續", grouped["Momentum"][:2]),
    ]

    y = 430
    for title, picks in sections:
        draw_text(draw, (70, y), title, FONT_LG)
        y += 58
        if not picks:
            rounded_box(draw, (70, y, 1530, y + 78), PANEL_3, radius=22)
            draw_text(draw, (100, y + 24), "今日無明確候選", FONT_MD, MUTED)
            y += 98
            continue

        for item in picks:
            rounded_box(draw, (70, y, 1530, y + 84), PANEL_3, radius=22)
            draw_text(draw, (96, y + 22), item["ticker"], FONT_MD, WHITE)
            draw_text(draw, (250, y + 22), item["sector"], FONT_SM, MUTED)
            draw_text(draw, (620, y + 22), f"Score {item['total_score']}/100", FONT_MD, score_to_color(item["total_score"]))
            draw_text(draw, (920, y + 22), f"Price ${item['close']:.2f}", FONT_MD)
            draw_text(draw, (1160, y + 22), classify_action(item), FONT_MD, ACCENT_2)
            y += 100

    draw_text(draw, (70, 850), "For research only — not investment advice", FONT_XS, MUTED)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "00_overview.png")
    img.save(path)
    return path


def save_stock_card(rank, result):
    img, draw = make_canvas()
    rounded_box(draw, (32, 32, CARD_W - 32, CARD_H - 32), PANEL, radius=34, outline=LINE, width=2)

    draw_text(draw, (70, 60), f"#{rank} {result['ticker']}", FONT_XXL)
    draw_text(draw, (340, 80), result["sector"], FONT_SM, MUTED)
    draw_text(draw, (1320, 76), f"{result['total_score']}/100", FONT_LG, score_to_color(result["total_score"]))

    rounded_box(draw, (70, 190, 470, 360), PANEL_2, radius=28)
    draw_text(draw, (100, 220), "現價", FONT_SM, MUTED)
    draw_text(draw, (100, 275), f"${result['close']:.2f}", FONT_LG)

    rounded_box(draw, (520, 190, 920, 360), PANEL_2, radius=28)
    draw_text(draw, (550, 220), "防守位", FONT_SM, MUTED)
    draw_text(draw, (550, 275), f"${result['stop_loss']:.2f}", FONT_LG)
    draw_text(draw, (550, 322), f"{result['stop_loss_pct']:.1f}% from close", FONT_XS, MUTED)

    rounded_box(draw, (970, 190, 1370, 360), PANEL_2, radius=28)
    draw_text(draw, (1000, 220), "RSI / Setup", FONT_SM, MUTED)
    draw_text(draw, (1000, 275), f"{result['rsi']:.0f}", FONT_LG, GREEN if result["rsi"] < 68 else YELLOW)
    draw_text(draw, (1085, 282), result["setup_type"], FONT_XS, MUTED)

    rounded_box(draw, (70, 410, 690, 700), PANEL_2, radius=28)
    draw_text(draw, (100, 442), "關鍵快照", FONT_MD, MUTED)
    draw_text(draw, (100, 505), f"5D Change: {result['pct_5d']:+.1f}%", FONT_SM)
    draw_text(draw, (100, 555), f"20D Change: {result['pct_20d']:+.1f}%", FONT_SM)
    draw_text(draw, (100, 605), f"From 52W High: {result['pct_from_52w_high']:.1f}%", FONT_SM)
    draw_text(draw, (100, 655), f"Above 52W Low: {result['pct_above_52w_low']:.1f}%", FONT_SM)

    rounded_box(draw, (740, 410, 1530, 700), PANEL_2, radius=28)
    draw_text(draw, (770, 442), "入選原因", FONT_MD, MUTED)
    y = 500
    for sig in result["signals"][:4]:
        for line in wrap_lines(f"• {sig}", 34):
            draw_text(draw, (770, y), line, FONT_SM)
            y += 38
        y += 8

    rounded_box(draw, (70, 740, 1530, 840), "#0B2A4D", radius=28, outline=ACCENT, width=3)
    draw_text(draw, (100, 768), "決策建議", FONT_SM, MUTED)
    draw_text(draw, (100, 804), classify_action(result), FONT_LG, ACCENT_2)

    draw_text(draw, (70, 860), "For research only — not investment advice", FONT_XS, MUTED)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{rank:02d}_{result['ticker']}.png")
    img.save(path)
    return path


def generate_report_images(results, trump, universe_size, prefiltered_size):
    grouped = {
        "Breakout": [r for r in results if r["setup_type"] == "Breakout"],
        "Pullback": [r for r in results if r["setup_type"] == "Pullback"],
        "Momentum": [r for r in results if r["setup_type"] == "Momentum"],
    }

    priority = grouped["Breakout"][:2] + grouped["Pullback"][:2] + grouped["Momentum"][:2]
    seen = set()
    final_picks = []
    for r in priority + results:
        if r["ticker"] not in seen:
            seen.add(r["ticker"])
            final_picks.append(r)
        if len(final_picks) >= 5:
            break

    paths = [save_overview_card(results, trump, grouped, universe_size, prefiltered_size)]
    for i, r in enumerate(final_picks, 1):
        paths.append(save_stock_card(i, r))
    return paths, final_picks


def build_caption(final_picks, trump, universe_size, prefiltered_size):
    if not final_picks:
        return "📊 今日無明確候選，建議保守觀察。"

    top = final_picks[0]
    return (
        f"📊 美股 Universe 掃描完成\n"
        f"Universe: {universe_size} | Prefilter: {prefiltered_size}\n"
        f"Top Pick: {top['ticker']} ({top['total_score']}/100)\n"
        f"Setup: {top['setup_type']} | {classify_action(top)}\n"
        f"市場狀態: {trump['direction']} | 信心 {trump['confidence']:.0%}"
    )


def run_scan():
    print(f"[{datetime.now(TZ).strftime('%H:%M')}] Build universe...")
    universe = fetch_us_universe()
    print(f"  → universe size: {len(universe)}")

    print(f"[{datetime.now(TZ).strftime('%H:%M')}] Prefilter...")
    candidates = basic_prefilter(universe, limit=700)
    print(f"  → candidates after prefilter: {len(candidates)}")

    print(f"[{datetime.now(TZ).strftime('%H:%M')}] Trump signal...")
    trump = get_trump_signal()
    print(f"  → {trump['direction']} / score {trump['score']}")

    results = []
    for idx, ticker in enumerate(candidates, 1):
        if idx % 50 == 0:
            print(f"  analyzed {idx}/{len(candidates)}")

        result = analyze_stock(ticker)
        if not result:
            continue

        news = get_news_sentiment(ticker)
        news_score = max(-12, min(12, news["score"] * 3))
        result["news"] = news
        result["news_score"] = news_score
        result["total_score"] += trump["score"] + news_score

        if result["setup_type"] in {"Breakout", "Pullback", "Momentum"} and result["total_score"] >= 48:
            results.append(result)

    results.sort(key=lambda x: x["total_score"], reverse=True)

    if not results:
        send_telegram_text("📊 今日無明確候選，建議保守觀察。")
        return

    image_paths, final_picks = generate_report_images(
        results=results,
        trump=trump,
        universe_size=len(universe),
        prefiltered_size=len(candidates),
    )
    caption = build_caption(final_picks, trump, len(universe), len(candidates))
    send_telegram_photos(image_paths, caption=caption)

    print("已生成圖片：")
    for p in image_paths:
        print(p)


if __name__ == "__main__":
    run_scan()
