
import os
import textwrap
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NEWS_API_KEY     = os.getenv("NEWS_API_KEY", "")
TRUMP_API        = "https://trumpcode.washinmura.jp"

OUT_DIR = "output_cards"
CARD_W, CARD_H = 1280, 720
BG      = "#0B1220"
PANEL   = "#121A2B"
PANEL_2 = "#182235"
TEXT    = "#EAF2FF"
MUTED   = "#94A3B8"
ACCENT  = "#4F8CFF"
GREEN   = "#22C55E"
YELLOW  = "#F59E0B"
RED     = "#EF4444"
LINE    = "#22304A"

TZ_TW = ZoneInfo("Asia/Taipei")
TZ_ET = ZoneInfo("America/New_York")

def now_str():
    tw = datetime.now(TZ_TW).strftime("%Y-%m-%d %H:%M")
    et = datetime.now(TZ_ET).strftime("%H:%M ET")
    return f"{tw} TWN  /  {et}"

def get_font(size=32, bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try: return ImageFont.truetype(path, size=size)
            except: pass
    return ImageFont.load_default()

FONT_XL = get_font(48, True)
FONT_LG = get_font(32, True)
FONT_MD = get_font(24, False)
FONT_SM = get_font(20, False)
FONT_XS = get_font(16, False)


import os
import textwrap
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NEWS_API_KEY     = os.getenv("NEWS_API_KEY", "")
TRUMP_API        = "https://trumpcode.washinmura.jp"

OUT_DIR = "output_cards"
CARD_W, CARD_H = 1280, 720
BG      = "#0B1220"
PANEL   = "#121A2B"
PANEL_2 = "#182235"
TEXT    = "#EAF2FF"
MUTED   = "#94A3B8"
ACCENT  = "#4F8CFF"
GREEN   = "#22C55E"
YELLOW  = "#F59E0B"
RED     = "#EF4444"
LINE    = "#22304A"

TZ_TW = ZoneInfo("Asia/Taipei")
TZ_ET = ZoneInfo("America/New_York")

def now_str():
    tw = datetime.now(TZ_TW).strftime("%Y-%m-%d %H:%M")
    et = datetime.now(TZ_ET).strftime("%H:%M ET")
    return f"{tw} TWN  /  {et}"

def get_font(size=32, bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try: return ImageFont.truetype(path, size=size)
            except: pass
    return ImageFont.load_default()

FONT_XL = get_font(48, True)
FONT_LG = get_font(32, True)
FONT_MD = get_font(24, False)
FONT_SM = get_font(20, False)
FONT_XS = get_font(16, False)
def send_telegram_text(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg); return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
        try:
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk, "parse_mode": "Markdown"}, timeout=20)
        except Exception as e:
            print(f"[TG err] {e}")

def send_telegram_photo(path, caption=""):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[local] {path}"); return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            data = {"chat_id": TELEGRAM_CHAT_ID}
            if caption: data["caption"] = caption
            resp = requests.post(url, data=data, files={"photo": ("card.png", f, "image/png")}, timeout=60)
            j = resp.json()
            if not j.get("ok"):
                print(f"[TG photo err] {j}")
    except Exception as e:
        print(f"[TG photo err] {e}")

def get_trump_signal():
    try:
        r = requests.get(f"{TRUMP_API}/api/signals", timeout=15)
        data = r.json()
        latest = (data.get("signals") or [{}])[0]
        direction   = latest.get("direction", "NEUTRAL")
        confidence  = float(latest.get("confidence", 0.5))
        signal_type = latest.get("signal", "NEUTRAL")
        score = int(confidence*15) if direction=="LONG" else -int(confidence*15) if direction=="SHORT" else 0
        reasoning = f"{direction} ({signal_type}) {confidence:.0%}"
        if data.get("today_post_count", -1) == 0:
            score += 5; reasoning += " | Zero-post day ⚡"
        if "TARIFF" in str(signal_type).upper():
            score -= 8; reasoning += " | Tariff risk ⚠️"
        return {"score": score, "direction": direction, "confidence": confidence, "reasoning": reasoning}
    except:
        return {"score": 0, "direction": "NEUTRAL", "confidence": 0, "reasoning": "skipped"}

def get_news_sentiment(ticker):
    if not NEWS_API_KEY: return {"score": 0, "headlines": [], "count": 0}
    pos = ["beat","surge","record","growth","upgrade","buy","strong","profit","bullish","rally","breakthrough","contract","partnership"]
    neg = ["miss","drop","fall","downgrade","sell","loss","bearish","cut","warn","risk","decline","fraud","lawsuit"]
    try:
        r = requests.get("https://newsapi.org/v2/everything", params={
            "q": ticker, "language": "en", "sortBy": "publishedAt",
            "pageSize": 10, "apiKey": NEWS_API_KEY
        }, timeout=15)
        articles = r.json().get("articles", [])
        score = 0; headlines = []
        for art in articles[:5]:
            t = art.get("title","").lower()
            score += sum(1 for kw in pos if kw in t)
            score -= sum(1 for kw in neg if kw in t)
            headlines.append(art.get("title","")[:90])
        return {"score": score, "headlines": headlines[:3], "count": len(articles)}
    except:
        return {"score": 0, "headlines": [], "count": 0}

def get_dynamic_tickers():
    tickers = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://finviz.com/screener.ashx?v=111&s=ta_unusualvolume&f=cap_smallover&o=-volume&r=1"
        r = requests.get(url, headers=headers, timeout=15)
        from html.parser import HTMLParser
        class P(HTMLParser):
            def __init__(self):
                super().__init__(); self.tickers=[]; self.cap=False
            def handle_starttag(self, tag, attrs):
                d = dict(attrs)
                if tag=="a" and "quote.ashx" in d.get("href",""):
                    self.cap=True
            def handle_data(self, data):
                if self.cap and data.strip() and len(data.strip())<=6:
                    self.tickers.append(data.strip()); self.cap=False
        p = P(); p.feed(r.text)
        tickers = list(dict.fromkeys(p.tickers))[:80]
        print(f"[Finviz] 動態抓到 {len(tickers)} 檔")
    except Exception as e:
        print(f"[Finviz err] {e}")
    if not tickers:
        tickers = [
            "NVDA","MSFT","AAPL","GOOGL","META","AMZN","TSLA","AMD","AVGO","ORCL",
            "POET","SOUN","BBAI","IONQ","RGTI","HIMS","CELH","HOOD","SOFI","SMCI",
            "AFRM","UPST","DKNG","RKLB","LUNR","ASTS","ACHR","JOBY","APP","RDDT"
        ]
        print(f"[fallback] 預設清單 {len(tickers)} 檔")
    return tickers
def compute_rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(length).mean()
    loss = (-delta.clip(upper=0)).rolling(length).mean()
    return 100 - (100 / (1 + gain / loss.replace(0, 1e-10)))

def compute_atr(high, low, close, length=14):
    tr = pd.concat([(high-low),(high-close.shift()).abs(),(low-close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(length).mean()

def classify_action(result):
    score = result["total_score"]
    rsi   = result["rsi"]
    pct   = result["pct_from_52w_high"]
    if result.get("pullback_signal"): return "⚡ 回落入場"
    if score >= 70 and rsi < 68:      return "✅ 強力買入"
    if score >= 55 and rsi < 72:      return "👀 考慮買入"
    if rsi >= 72:                      return "⚠️ 過熱觀望"
    if pct < -20:                      return "🔻 趨勢偏弱"
    return "➡️ 持續觀察"

def analyze_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo", interval="1d")
        if df.empty or len(df) < 30: return None
        df["RSI"]   = compute_rsi(df["Close"])
        df["ATR"]   = compute_atr(df["High"], df["Low"], df["Close"])
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        latest = df.iloc[-1]
        close  = float(latest["Close"])
        rsi    = float(latest["RSI"])  if not pd.isna(latest["RSI"])  else 50.0
        atr    = float(latest["ATR"])  if not pd.isna(latest["ATR"])  else close*0.02
        hist_1y  = stock.history(period="1y")
        high_52w = float(hist_1y["High"].max()) if not hist_1y.empty else close
        pct_from_52w_high = (close - high_52w) / high_52w * 100
        info   = stock.info
        pe     = info.get("trailingPE")
        eps_g  = info.get("earningsGrowth")
        sector = info.get("sector", "Unknown")
        avg_vol   = df["Volume"].iloc[-21:-1].mean()
        vol_spike = float(latest["Volume"]) / avg_vol if avg_vol > 0 else 1.0
        pct_5d    = (close - float(df.iloc[-6]["Close"])) / float(df.iloc[-6]["Close"]) * 100 if len(df) >= 6 else 0
        tech_score = fund_score = 0
        signals = []
        pullback_signal = False
        if 45 < rsi < 70:   tech_score += 15; signals.append(f"RSI {rsi:.0f} 健康")
        elif rsi >= 70:      tech_score += 5;  signals.append(f"RSI {rsi:.0f} 偏熱")
        elif rsi < 35:       tech_score += 12; signals.append(f"RSI {rsi:.0f} 超賣反彈")
        if float(latest["EMA20"]) > float(latest["EMA50"]):
            tech_score += 10; signals.append("EMA20>EMA50 多頭")
        if close > float(latest["EMA20"]):
            tech_score += 8; signals.append("站上EMA20")
        if 1 < pct_5d < 20:
            tech_score += 5; signals.append(f"近5日 +{pct_5d:.1f}%")
        if vol_spike >= 3.0:
            tech_score = min(tech_score+12, 55); signals.append(f"爆量 {vol_spike:.1f}x ⚡")
        elif vol_spike >= 2.0:
            tech_score = min(tech_score+8,  55); signals.append(f"量增 {vol_spike:.1f}x")
        elif vol_spike >= 1.5:
            tech_score = min(tech_score+4,  55); signals.append(f"量放 {vol_spike:.1f}x")
        peak     = float(df["Close"].rolling(60).max().iloc[-1])
        drawdown = (close - peak) / peak * 100
        if drawdown <= -30:
            recent_low = float(df["Close"].tail(10).min())
            recovery   = (close - recent_low) / recent_low * 100
            if recovery >= 10 and rsi > 38:
                tech_score += 20; pullback_signal = True
                signals.append(f"⚡ 高點回落{drawdown:.0f}% 反彈+{recovery:.0f}%")
                signals.append("POET型態確認")
            elif recovery >= 5:
                tech_score += 8
                signals.append(f"回落{drawdown:.0f}% 初彈+{recovery:.0f}%（待確認）")
        if eps_g and eps_g > 0.15: fund_score += 15; signals.append(f"EPS+{eps_g*100:.0f}%")
        elif eps_g and eps_g > 0:  fund_score += 8;  signals.append(f"EPS+{eps_g*100:.0f}%")
        if pe and 0 < pe < 30:     fund_score += 10; signals.append(f"P/E {pe:.1f}")
        elif pe and 30 <= pe < 60: fund_score += 5;  signals.append(f"P/E {pe:.1f}")
        if pct_from_52w_high > -10: fund_score += 5; signals.append(f"距52週高{pct_from_52w_high:.1f}%")
        stop_loss     = close - 1.5 * atr
        stop_loss_pct = (stop_loss - close) / close * 100
        return {
            "ticker": ticker, "close": close, "rsi": rsi, "atr": atr,
            "tech_score": tech_score, "fund_score": fund_score,
            "total_score": tech_score + fund_score,
            "signals": signals[:5], "stop_loss": stop_loss,
            "stop_loss_pct": stop_loss_pct, "sector": sector,
            "pct_5d": pct_5d, "pct_from_52w_high": pct_from_52w_high,
            "vol_spike": vol_spike, "pullback_signal": pullback_signal,
        }
    except Exception as e:
        print(f"[分析失敗] {ticker}: {e}"); return None
<<<<<<< HEAD
=======

def rounded_box(draw, xy, fill, radius=24, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def draw_text(draw, xy, text, font, fill=None):
    draw.text(xy, text, font=font, fill=fill or TEXT)

def make_canvas():
    img = Image.new("RGB", (CARD_W, CARD_H), BG)
    return img
def save_overview_card(results, trump):
    img  = make_canvas()
    draw = ImageDraw.Draw(img)
    rounded_box(draw, [40,40,CARD_W-40,CARD_H-40], PANEL, radius=28, outline=LINE, width=2)
    draw_text(draw, (70,70),  "US STOCK DAILY SCAN", FONT_XL)
    draw_text(draw, (70,140), datetime.now().strftime("%Y-%m-%d  %H:%M"), FONT_SM, MUTED)
    rounded_box(draw, [70,190,550,320], PANEL_2, radius=22)
    draw_text(draw, (95,215),  "Market Context", FONT_MD, MUTED)
    draw_text(draw, (95,255),  f"Trump: {trump['direction']}", FONT_LG)
    draw_text(draw, (95,295),  f"Confidence {trump['confidence']:.0%}", FONT_SM, MUTED)
    rounded_box(draw, [580,190,1210,320], PANEL_2, radius=22)
    draw_text(draw, (605,215), "Today's Bias", FONT_MD, MUTED)
    top = results[0]["total_score"] if results else 0
    bias = "🟢 BULLISH" if top >= 70 else "🟡 NEUTRAL" if top >= 55 else "🔴 CAUTION"
    draw_text(draw, (605,255), bias, FONT_LG)
    draw_text(draw, (70,370),  "Top Picks", FONT_LG)
    y = 430
    for i, r in enumerate(results[:5], 1):
        rounded_box(draw, [70,y,1210,y+70], PANEL_2, radius=18)
        tag = "⚡" if r.get("mode")=="breakout" else "📊"
        draw_text(draw, (95,y+20),   f"#{i} {tag}", FONT_MD, MUTED)
        draw_text(draw, (175,y+18),  r["ticker"],   FONT_MD)
        draw_text(draw, (340,y+18),  f"Score {r['total_score']}/100", FONT_MD, ACCENT)
        draw_text(draw, (620,y+18),  f"${r['close']:.2f}", FONT_MD)
        draw_text(draw, (900,y+18),  classify_action(r), FONT_MD, GREEN)
        y += 84
    draw_text(draw, (70,660), "For research only – not investment advice", FONT_XS, MUTED)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "00_overview.png")
    img.save(path); return path

def save_stock_card(rank, result):
    img  = make_canvas()
    draw = ImageDraw.Draw(img)
    rounded_box(draw, [40,40,CARD_W-40,CARD_H-40], PANEL, radius=28, outline=LINE, width=2)
    tag = "⚡ BREAKOUT" if result.get("mode")=="breakout" else "📊 BLUECHIP"
    draw_text(draw, (70,70), f"#{rank}  {result['ticker']}  {tag}", FONT_XL)
    draw_text(draw, (1030,82), f"{result['total_score']}/100", FONT_LG, ACCENT)
    rounded_box(draw, [70,170,390,300], PANEL_2, radius=22)
    draw_text(draw, (95,195),  "Price",       FONT_SM, MUTED)
    draw_text(draw, (95,235),  f"${result['close']:.2f}", FONT_LG)
    rounded_box(draw, [430,170,750,300], PANEL_2, radius=22)
    draw_text(draw, (455,195), "Stop Loss",   FONT_SM, MUTED)
    draw_text(draw, (455,235), f"${result['stop_loss']:.2f}", FONT_LG)
    rsi_color = GREEN if result["rsi"] < 68 else YELLOW
    rounded_box(draw, [790,170,1110,300], PANEL_2, radius=22)
    draw_text(draw, (815,195), "RSI",         FONT_SM, MUTED)
    draw_text(draw, (815,235), f"{result['rsi']:.0f}", FONT_LG, rsi_color)
    rounded_box(draw, [70,330,540,530], PANEL_2, radius=22)
    draw_text(draw, (95,355),  "Snapshot",    FONT_MD, MUTED)
    draw_text(draw, (95,400),  f"Sector  {result['sector']}", FONT_SM)
    draw_text(draw, (95,435),  f"5D Chg  {result['pct_5d']:+.1f}%", FONT_SM)
    draw_text(draw, (95,470),  f"vs 52W Hi  {result['pct_from_52w_high']:.1f}%", FONT_SM)
    draw_text(draw, (95,505),  f"Vol Spike  {result['vol_spike']:.1f}x", FONT_SM)
    rounded_box(draw, [570,330,1210,590], PANEL_2, radius=22)
    draw_text(draw, (595,355), "Why It Made the List", FONT_MD, MUTED)
    y = 400
    for sig in result["signals"][:5]:
        for line in textwrap.wrap(f"• {sig}", width=38):
            draw_text(draw, (595,y), line, FONT_SM); y += 34
        y += 4
    rounded_box(draw, [70,545,1210,650], "#10233D", radius=22, outline=ACCENT, width=2)
    draw_text(draw, (95,572),  "Decision",         FONT_SM, MUTED)
    draw_text(draw, (95,605),  classify_action(result), FONT_LG, ACCENT)
    if result.get("pullback_signal"):
        draw_text(draw, (550,605), f"ATR Stop: {result['stop_loss_pct']:.1f}%", FONT_SM, YELLOW)
    draw_text(draw, (70,670),  "For research only – not investment advice", FONT_XS, MUTED)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{rank:02d}_{result['ticker']}.png")
    img.save(path); return path

def generate_report_images(results, trump):
    paths = [save_overview_card(results, trump)]
    for i, r in enumerate(results[:5], 1):
        paths.append(save_stock_card(i, r))
    return paths

def build_caption(results, trump):
    if not results: return "No picks today."
    top = results[0]
    return (f"📊 {top['ticker']} #{1} Score:{top['total_score']}/100"
            f"Trump: {trump['direction']} {trump['confidence']:.0%}")

def run_scan():
    print(f"[{datetime.now().strftime('%H:%M')}] Trump signal...")
    trump = get_trump_signal()
    print(f"  → {trump['direction']} / score {trump['score']}")

    results = []

    print("[掃描] 龍頭股...")
    for ticker in WATCHLIST:
        r = analyze_stock(ticker, mode="normal")
        if r and r["total_score"] >= 25:
            news = get_news_sentiment(ticker)
            r["total_score"] += trump["score"] + max(-15, min(15, news["score"]*3))
            results.append(r)

    print("[掃描] 爆發股（POET 類型）...")
    breakout_hits = []
    for ticker in BREAKOUT_WATCHLIST:
        r = analyze_stock(ticker, mode="breakout")
        if r and r["total_score"] >= 20:
            news = get_news_sentiment(ticker)
            r["total_score"] += trump["score"] + max(-15, min(15, news["score"]*3))
            breakout_hits.append(r)

    breakout_hits.sort(key=lambda x: x["total_score"], reverse=True)
    results.sort(key=lambda x: x["total_score"], reverse=True)

    # 前3龍頭 + 前2爆發股 混合推薦
    final = results[:3] + breakout_hits[:2]
    final.sort(key=lambda x: x["total_score"], reverse=True)

    print(f"[結果] 龍頭 {len(results)} 檔，爆發 {len(breakout_hits)} 檔，推薦 {len(final)} 檔")

    if not final:
        send_telegram_text("📊 今日掃描完成，暫無達標標的。")
        return

    image_paths = generate_report_images(final, trump)
    caption     = build_caption(final, trump)
    send_telegram_photos(image_paths, caption=caption)
    print("[完成] 圖片已發送到 Telegram")
    for p in image_paths:
        print(f"  {p}")

if __name__ == "__main__":
    run_scan()
>>>>>>> 5691df04ce8cf2d1d0a02fb81afa4207b46556ad
