# -*- coding: utf-8 -*-
# Build: 20260323-V22-FIXED
"""
╔══════════════════════════════════════════════════════════════╗
║     MAFIO BOT V22 — LIQUIDITY MASTER (FIXED)               ║
║     رصد السيولة حتى في السوق الهابط                       ║
║     تتبع أين تذهب الأموال رغم نزول السوق                   ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any, Set
from collections import deque

# ==================== تعريف المتغيرات المفقودة ====================
btc_trend_4h = 0.0
btcd_trend = "neutral"
_coin_first_seen = {}
_cvd_cache = {}
perf_track = {}
_vol_surge_baseline = {}
_vol_surge_alerted = {}
sector_flow_hot = {}
last_bear_scan = 0.0

# ==================== CONSTANTS (من الكود الأصلي) ====================
STATE_FILE = "/app/mafio_state.json"

REDIS_URL = os.environ.get("REDIS_URL", os.environ.get("UPSTASH_REDIS_REST_URL", ""))
REDIS_TOKEN = os.environ.get("REDIS_TOKEN", os.environ.get("UPSTASH_REDIS_REST_TOKEN", ""))
REDIS_KEY = "mafio_state_v22"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "YOUR_CHAT_ID")
GROUP_ID = os.getenv("GROUP_ID", "")

# ==================== إعدادات السيولة ====================
WATCH_MIN_VOL = 100_000
WATCH_MIN_VDELTA = 0.58
WATCH_MIN_VOL_RATIO = 1.5
WATCH_COOLDOWN = 1800

ENTRY_MIN_VOL = 500_000
ENTRY_MIN_VDELTA = 0.65
ENTRY_MIN_VOL_RATIO = 2.0
ENTRY_MIN_ATS = 100
ENTRY_COOLDOWN = 7200

JOKER_MIN_ATS = 500
JOKER_MIN_VDELTA = 0.70
JOKER_COOLDOWN = 14400

# ==================== المتغيرات العامة ====================
tracked = {}
discovered = {}
btc_change_24h = 0.0
btc_trend_1h = 0.0
eth_change_24h = 0.0
btc_tps_stats = {}
eth_tps_stats = {}
market_state = "SAFE"
last_market_report = 0.0
MARKET_REPORT_EVERY = 21600

_btc_danger_count = 0
_btc_caution_count = 0
_btc_safe_count = 0
hot_sectors = []
hot_symbols = set()
sector_vol_history = {}

candidates = []
changes_map = {}
all_tickers = []

klines_cache = {}

last_tickers = 0.0
last_btc = 0.0
last_sectors = 0.0
last_deep_scan = 0.0
last_stale = 0.0
last_report = 0.0
last_smart_money = 0.0
last_expand = 0.0
last_daily_report = 0.0

daily_market_vol_history = []
market_activity_history = []
breakout_report_sent = {}
tv_script_cache = {}
daily_report_sent_date = ""

lz_alerted = {}
lz_daily_sent_date = ""

hidden_accum_alerted = {}

tps_alerted = {}
last_tps_scan = 0.0
last_whale_check = 0.0
tps_baseline = {}

coin_alerted = {}
coin_signal_count = {}
coin_whale_done = {}
whale_watchlist = {}
whale_confirmed = {}
lz_tps_alerted = {}
lh_alerted = {}
last_lh_scan = 0.0

small_caps = []
last_sc_refresh = 0.0
sc_alerted = {}

stable_vol_history = {}
smart_money_alert = False
smart_money_bonus = 0

price_prev = {}
momentum_alerted = {}
momentum_stage = {}

watchlist = {}

price_snapshot = {}
price_snapshot_time = 0.0

sector_vol_snapshots = {}
sector_change_snapshots = {}
sector_flow_alerted = {}
sector_flow_state = {}
last_sr_alert = 0.0
top10_alerted = {}

coin_vol_history = {}

bottom_price_history = {}
bottom_vol_history = {}
bottom_alerted = {}
explosion_alerted = {}
ath_tracker = {}
ath_alerted = {}
gem_watchlist = {}
daily_gem_count = {"date": "", "count": 0}
last_ath_scan = 0.0
hot_alerted = {}
last_hot_scan = 0.0
rt_vol_baseline = {}
rt_alerted = {}
wl_entry_alerted = {}
wl_price_snapshot = {}
last_wl_check = 0.0

ts_positions = {}
ts_sell_alerted = {}
last_ts_scan = 0.0
daily_signals = {"date": "", "count": 0}
last_rt_scan = 0.0
last_bottom_scan = 0.0

backtest_signals = {}

api_calls_total = 0
api_calls_minute = 0
api_minute_reset = time.time()

session = requests.Session()
session.headers.update({"User-Agent": "MafioBot/22.0"})

# ==================== الدوال المساعدة الأساسية ====================

def fmt_price(p):
    if p == 0:
        return "0"
    if p < 0.0001:
        return "{:.10f}".format(p).rstrip("0")
    if p < 1:
        return "{:.8f}".format(p).rstrip("0")
    if p < 1000:
        return "{:.4f}".format(p).rstrip("0").rstrip(".")
    return "{:,.2f}".format(p)


def fmt_change(c):
    if abs(c) < 0.05:
        return "0.0%"
    return "{:+.1f}%".format(c)


def send(msg, personal_only=False):
    if not TELEGRAM_TOKEN or len(TELEGRAM_TOKEN) < 10:
        log.info("[TELEGRAM] %s", msg[:80])
        return

    targets = [CHAT_ID]
    if GROUP_ID and not personal_only:
        targets.append(GROUP_ID)

    for chat_id in targets:
        if not chat_id or "YOUR" in str(chat_id):
            continue
        try:
            session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=15,
            )
        except Exception as e:
            log.error("Telegram [%s]: %s", chat_id, e)


def safe_get(url, params=None, retries=3):
    global api_calls_total, api_calls_minute, api_minute_reset

    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=10)
            r.raise_for_status()
            api_calls_total += 1
            api_calls_minute += 1
            _now = time.time()
            _elapsed = _now - api_minute_reset
            if _elapsed >= 60:
                _rate = int(api_calls_minute / (_elapsed / 60))
                log.info("📡 API: %d req/min | total: %d", _rate, api_calls_total)
                api_calls_minute = 0
                api_minute_reset = _now
            return r.json()
        except Exception as e:
            wait = 2 ** attempt
            if attempt < retries - 1:
                log.debug("API retry %d/%d: %s", attempt + 1, retries, e)
                time.sleep(wait)
    return None


def get_klines(symbol, interval="15m", limit=50):
    cache_ttl = {"15m": 60, "1h": 300, "4h": 900}.get(interval, 60)
    key = f"{symbol}_{interval}"
    now = time.time()

    if key in klines_cache:
        data, ts = klines_cache[key]
        if now - ts < cache_ttl:
            return data

    raw = safe_get("https://api.mexc.com/api/v3/klines",
                   {"symbol": symbol, "interval": interval, "limit": limit})
    if not raw or len(raw) < 6:
        return None

    try:
        opens = [float(c[1]) for c in raw]
        highs = [float(c[2]) for c in raw]
        lows = [float(c[3]) for c in raw]
        closes = [float(c[4]) for c in raw]
        vols = [float(c[5]) for c in raw]
        result = {
            "opens": opens, "highs": highs, "lows": lows,
            "closes": closes, "vols": vols,
            "avg_vol": sum(vols[:-1]) / max(len(vols[:-1]), 1),
        }
        klines_cache[key] = (result, now)
        return result
    except (IndexError, ValueError, ZeroDivisionError):
        return None


def get_coin_vol_ratio(sym, current_vol):
    hist = coin_vol_history.get(sym, [])
    if len(hist) < 3:
        return 1.0
    avg = sum(hist) / len(hist)
    if avg <= 0:
        return 1.0
    return round(current_vol / avg, 2)


def update_coin_vol_history(vol_map):
    global coin_vol_history
    for sym, vol in vol_map.items():
        if vol <= 0:
            continue
        if sym not in coin_vol_history:
            coin_vol_history[sym] = []
        coin_vol_history[sym].append(vol)
        if len(coin_vol_history[sym]) > 10:
            coin_vol_history[sym].pop(0)


def analyze_tps_ats(sym):
    raw = safe_get("https://api.mexc.com/api/v3/trades",
                   {"symbol": sym, "limit": 100})
    if not raw or not isinstance(raw, list) or len(raw) < 10:
        return None
    try:
        now_ms = int(time.time() * 1000)
        window = 30000
        all_vol = 0.0
        trade_window = 0

        for t in raw:
            price = float(t.get("price", 0))
            qty = float(t.get("qty", 0))
            ts = int(t.get("time", 0))
            val = price * qty
            all_vol += val
            if now_ms - ts <= window:
                trade_window += 1

        if all_vol <= 0:
            return None

        tps = trade_window / 30.0
        ats = all_vol / len(raw)

        # VDelta بسيط
        vdelta = 0.5
        kd = get_klines(sym, "15m", 15)
        if kd and len(kd["closes"]) >= 5:
            buy_vol = 0
            sell_vol = 0
            for i in range(len(kd["closes"])):
                if kd["closes"][i] > kd["opens"][i]:
                    buy_vol += kd["vols"][i]
                elif kd["closes"][i] < kd["opens"][i]:
                    sell_vol += kd["vols"][i]
            total = buy_vol + sell_vol
            if total > 0:
                vdelta = buy_vol / total

        return {
            "tps": round(tps, 2),
            "ats": round(ats, 2),
            "vdelta": round(vdelta, 3),
            "buyer_type": "🐋 حيتان" if ats >= 2000 else ("🐟 متوسط" if ats >= 500 else "🦐 أفراد"),
        }
    except (KeyError, ValueError, ZeroDivisionError, TypeError):
        return None


def get_current_price(sym):
    data = safe_get("https://api.mexc.com/api/v3/ticker/price", {"symbol": sym})
    if data:
        return float(data.get("price", 0))
    return 0.0


def get_tps_label(tps):
    if tps < 0.2:
        return "🐌 ضعيف"
    if tps < 0.5:
        return "🐢 بطيء"
    if tps < 1.0:
        return "🟡 عادي"
    if tps < 3.0:
        return "🟢 جيد"
    if tps < 5.0:
        return "🔥 قوي"
    return "💥 انفجاري"


def get_ats_label(ats):
    if ats < 100:
        return "🦐 أفراد"
    if ats < 500:
        return "🦐 أفراد"
    if ats < 1500:
        return "🐟 متوسط"
    if ats < 5000:
        return "🐋 حيتان"
    return "🐋🔥 حيتان ضخمة"


def add_to_exit_watchlist(sym, entry_price):
    global exit_watchlist
    if 'exit_watchlist' not in globals():
        global exit_watchlist
        exit_watchlist = {}
    exit_watchlist[sym] = {"entry": entry_price, "time": time.time()}


# ==================== نظام رصد السيولة في السوق الهابط ====================

class BearMarketLiquidityHunter:
    def __init__(self):
        self.sector_liquidity = {}
        self.coin_liquidity = {}
        self.bear_signals = []
        self.bear_mode_start = 0
        self.last_bear_scan = 0
        self.is_bear = False

    def is_bear_market(self):
        """تحديد إذا كان السوق هابطاً"""
        if btc_change_24h <= -2.0:
            return True

        if all_tickers:
            falling = 0
            total = 0
            for t in all_tickers:
                try:
                    ch = float(t.get("priceChangePercent", 0))
                    if abs(ch) < 0.5:
                        continue
                    total += 1
                    if ch < 0:
                        falling += 1
                except:
                    pass
            if total > 0 and falling / total > 0.6:
                return True

        return False

    def detect_liquidity_direction(self, vol_now, change_now, price_map):
        """اكتشاف اتجاه السيولة في السوق الهابط"""
        if not self.is_bear_market():
            return []

        now = time.time()
        if now - self.last_bear_scan < 300:
            return []
        self.last_bear_scan = now

        sector_analysis = []

        for sector, coins in SECTORS.items():
            sector_data = {
                "sector": sector,
                "total_vol": 0,
                "rising_coins": [],
                "accum_coins": [],
                "avg_change": 0,
                "avg_vdelta": 0,
                "liquidity_score": 0
            }

            changes = []
            vdeltas = []

            for sym in coins:
                vol = vol_now.get(sym, 0)
                chg = change_now.get(sym, 0)

                if vol < 50000:
                    continue

                sector_data["total_vol"] += vol
                changes.append(chg)

                stats = analyze_tps_ats(sym)
                if stats:
                    vd = stats.get("vdelta", 0.5)
                    vdeltas.append(vd)

                    if chg > 0 and vol > 100000:
                        sector_data["rising_coins"].append({
                            "sym": sym,
                            "chg": chg,
                            "vol": vol,
                            "vdelta": vd,
                            "price": price_map.get(sym, 0)
                        })

                    vol_ratio = get_coin_vol_ratio(sym, vol)
                    if abs(chg) < 2.0 and vol_ratio >= 1.5 and vd >= 0.60:
                        sector_data["accum_coins"].append({
                            "sym": sym,
                            "vol_ratio": vol_ratio,
                            "vdelta": vd,
                            "price": price_map.get(sym, 0)
                        })

            if not changes:
                continue

            sector_data["avg_change"] = sum(changes) / len(changes)
            if vdeltas:
                sector_data["avg_vdelta"] = sum(vdeltas) / len(vdeltas)

            # حساب نقاط السيولة
            if sector_data["avg_vdelta"] >= 0.65:
                sector_data["liquidity_score"] += 30
            elif sector_data["avg_vdelta"] >= 0.60:
                sector_data["liquidity_score"] += 20

            rising_count = len(sector_data["rising_coins"])
            sector_data["liquidity_score"] += rising_count * 8

            accum_count = len(sector_data["accum_coins"])
            sector_data["liquidity_score"] += accum_count * 12

            if sector_data["avg_change"] > -5.0:
                sector_data["liquidity_score"] += 15

            sector_analysis.append(sector_data)

        sector_analysis.sort(key=lambda x: -x["liquidity_score"])
        return sector_analysis[:5]

    def scan_bear_liquidity_signals(self, vol_now, change_now, price_map):
        """مسح إشارات السيولة في السوق الهابط"""
        now = time.time()

        if not self.is_bear_market():
            return

        sectors = self.detect_liquidity_direction(vol_now, change_now, price_map)

        if not sectors:
            return

        for sector in sectors:
            if sector["liquidity_score"] < 30:
                continue

            last_alert = self.sector_liquidity.get(sector["sector"], {}).get("last_alert", 0)
            if now - last_alert < 3600:
                continue

            if sector["sector"] not in self.sector_liquidity:
                self.sector_liquidity[sector["sector"]] = {}
            self.sector_liquidity[sector["sector"]]["last_alert"] = now

            icon = "🐻" if btc_change_24h < -3 else "🌧️"

            msg = f"""
{icon} *رصد سيولة في السوق الهابط* {icon}
━━━━━━━━━━━━━━━━━━
📊 القطاع: *{sector['sector']}*
📉 BTC: `{btc_change_24h:+.1f}%` (السوق نازل)
━━━━━━━━━━━━━━━━━━
💧 *السيولة تتجه إلى هذا القطاع رغم النزول!*
━━━━━━━━━━━━━━━━━━
📈 *عملات ترتفع رغم نزول السوق:*
"""

            for coin in sector["rising_coins"][:5]:
                base = coin["sym"].replace("USDT", "")
                msg += f"  🟢 *{base}* `+{coin['chg']:.1f}%` | VDelta `{coin['vdelta']*100:.0f}%`\n"

            if sector["accum_coins"]:
                msg += "\n🔇 *تجميع خفي (حجم مرتفع + سعر ثابت):*\n"
                for coin in sector["accum_coins"][:3]:
                    base = coin["sym"].replace("USDT", "")
                    msg += f"  👁️ *{base}* | حجم `{coin['vol_ratio']:.1f}×` | VDelta `{coin['vdelta']*100:.0f}%`\n"

            msg += f"""
━━━━━━━━━━━━━━━━━━
💪 قوة السيولة: `{sector['liquidity_score']}/100`
📊 متوسط VDelta القطاع: `{sector['avg_vdelta']*100:.0f}%`
━━━━━━━━━━━━━━━━━━
🎯 *استراتيجية الدخول في السوق الهابط:*
  1️⃣ راقب عملات {sector['sector']} التي ترتفع رغم النزول
  2️⃣ انتظر إشارة ENTRY من النظام
  3️⃣ السوق نازل → استخدم Stop Loss أضيق (-3% فقط)
━━━━━━━━━━━━━━━━━━
⚠️ _السيولة موجودة — لكن السوق نازل، ادخل بحذر!_ 🎯
"""
            send(msg)
            log.info(f"🐻 BEAR LIQUIDITY | {sector['sector']} | score={sector['liquidity_score']}")


# ==================== دالة poll_commands المصححة ====================

_tg_offset = 0
_force_daily_report = False
exit_watchlist = {}
exit_alerted = {}

# تعريف SECTORS مؤقت (سيتم استيراده من الكود الأصلي)
SECTORS = {}  # سيتم ملؤه من الكود الأصلي


def poll_commands():
    """يستمع لأوامر Telegram"""
    global _tg_offset, daily_report_sent_date, vol_now, change_now, price_map

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={_tg_offset}&timeout=3&allowed_updates=message"
        r = requests.get(url, timeout=10)

        if r.status_code == 409:
            log.warning("getUpdates 409 - Webhook conflict")
            requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
            return

        if r.status_code != 200:
            log.warning("getUpdates HTTP %d", r.status_code)
            return

        data = r.json()
        if not data.get("ok"):
            log.warning("getUpdates not ok: %s", data)
            return

        updates = data.get("result", [])
        if updates:
            log.info("📨 getUpdates: %d messages", len(updates))

        for update in updates:
            _tg_offset = update["update_id"] + 1
            msg = update.get("message") or update.get("channel_post") or {}
            text = msg.get("text", "").strip()
            text_lower = text.lower()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            allowed = [str(CHAT_ID)]
            if GROUP_ID and GROUP_ID != "YOUR_GROUP_ID":
                allowed.append(str(GROUP_ID))

            if chat_id not in allowed:
                continue

            # الأوامر الأساسية
            if text_lower in ("/report", "/تقرير"):
                log.info("📤 /report requested")
                send("📄 جاري إعداد التقرير...")
                global all_tickers
                if not all_tickers:
                    try:
                        _r = safe_get("https://api.mexc.com/api/v3/ticker/24hr")
                        if _r:
                            all_tickers = _r
                    except Exception as _e:
                        log.error("Failed to fetch tickers: %s", _e)
                daily_report_sent_date = ""
                send_daily_report(force=True)

            elif text_lower in ("/status", "/حالة"):
                send(f"✅ البوت يعمل | {len(candidates)} عملة | جواهر: {len(gem_watchlist)}")

            elif text_lower in ("/watchlist", "/مراقبة"):
                if not watchlist:
                    send("👁️ قائمة المراقبة فارغة")
                else:
                    _static = [(s, v) for s, v in watchlist.items() if v.get("priority") == "STATIC"]
                    _dynamic = [(s, v) for s, v in watchlist.items() if v.get("priority") != "STATIC"]
                    txt = "👁️ *قائمة المراقبة:*\n"
                    if _static:
                        txt += f"\n📌 *ثابتة ({len(_static)}):*\n"
                        for s, v in _static:
                            base = s.replace("USDT", "")
                            ep = wl_price_snapshot.get(s, 0)
                            txt += f"  · *{base}* | دخول: `{ep}`\n"
                    if _dynamic:
                        txt += f"\n⚡ *ديناميكية ({len(_dynamic)}):*\n"
                        for s, v in _dynamic[:5]:
                            base = s.replace("USDT", "")
                            txt += f"  · *{base}* | {v.get('reason', '')[:30]}\n"
                    send(txt)

            elif text_lower in ("/gems", "/جواهر"):
                if not gem_watchlist:
                    send("💎 لا توجد جواهر حالياً")
                else:
                    txt = "💎 *جواهر مرصودة:*\n"
                    for s, v in list(gem_watchlist.items())[:10]:
                        txt += f"  • *{s.replace('USDT','')}* | مرحلة {v.get('stage',1)}\n"
                    send(txt)

            elif text_lower in ("/btc", "/بتكوين"):
                _icon = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🚨"}.get(market_state, "📊")
                _btps = ""
                if btc_tps_stats:
                    _btps = f"  🐋 TPS:`{btc_tps_stats.get('tps',0):.1f}` ATS:`{btc_tps_stats.get('ats',0):.0f}$` VD:`{btc_tps_stats.get('vdelta',0.5)*100:.0f}%`"
                send(
                    f"₿ *BTC الآن*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{_icon} السوق: *{market_state}*\n"
                    f"24h: `{btc_change_24h:+.2f}%`\n"
                    f"1h:  `{btc_trend_1h:+.2f}%`\n"
                    f"{_btps}"
                )

            elif text_lower in ("/sectors", "/قطاعات"):
                if not hot_sectors:
                    send("📊 لا توجد قطاعات ساخنة حالياً")
                else:
                    txt = "🏆 *أفضل القطاعات الآن:*\n━━━━━━━━━━━━━━━━━━\n"
                    for i, sec in enumerate(hot_sectors[:5], 1):
                        ch = 0
                        icon = "➡️"
                        txt += f"{i}. {icon} *{sec}*\n"
                    send(txt)

            elif text_lower in ("/performance", "/اداء"):
                send("📈 *تقرير الأداء قيد الإعداد...*")

            # ==================== الأوامر الجديدة للسوق الهابط ====================
            elif text_lower in ("/bear", "/سوق_هابط"):
                bear_hunter = BearMarketLiquidityHunter()
                if bear_hunter.is_bear_market():
                    # نحتاج إلى vol_now و change_now و price_map من المتغيرات العامة
                    if 'vol_now' in globals() and 'change_now' in globals() and 'price_map' in globals():
                        sectors = bear_hunter.detect_liquidity_direction(vol_now, change_now, price_map)
                        if sectors:
                            msg = "🐻 *حالة السوق: هابط* 🐻\n━━━━━━━━━━━━━━━━━━\n"
                            msg += f"₿ BTC: `{btc_change_24h:+.1f}%`\n━━━━━━━━━━━━━━━━━━\n"
                            msg += "*السيولة تتجه إلى:*\n"
                            for s in sectors[:3]:
                                msg += f"  🔥 *{s['sector']}* | قوة: `{s['liquidity_score']}/100`\n"
                                msg += f"     عملات صاعدة: {len(s['rising_coins'])} | تجميع: {len(s['accum_coins'])}\n"
                            send(msg)
                        else:
                            send("🐻 السوق هابط لكن لا توجد سيولة واضحة حالياً")
                    else:
                        send("🐻 السوق هابط، جاري جمع البيانات...")
                else:
                    send("🟢 السوق ليس هابطاً حالياً - استخدم /sectors لرؤية القطاعات الساخنة")

            elif text_lower in ("/bearcoins", "/عملات_هابط"):
                bear_hunter = BearMarketLiquidityHunter()
                if bear_hunter.is_bear_market():
                    if 'vol_now' in globals() and 'change_now' in globals() and 'price_map' in globals():
                        sectors = bear_hunter.detect_liquidity_direction(vol_now, change_now, price_map)
                        if sectors:
                            best = sectors[0]
                            opps = bear_hunter.get_bear_opportunities(best["sector"], price_map, vol_now, change_now)
                            if opps:
                                msg = f"🎯 *فرص الدخول في السوق الهابط* 🎯\n"
                                msg += f"━━━━━━━━━━━━━━━━━━\n"
                                msg += f"📊 القطاع: *{best['sector']}*\n"
                                msg += f"📉 BTC: `{btc_change_24h:+.1f}%`\n━━━━━━━━━━━━━━━━━━\n"
                                for opp in opps[:5]:
                                    base = opp["sym"].replace("USDT", "")
                                    msg += f"  • *{base}* `{opp['chg']:+.1f}%` | VD:{opp['vdelta']*100:.0f}% | قوة:{opp['score']}\n"
                                send(msg)
                            else:
                                send("🐻 لا توجد فرص دخول واضحة حالياً")
                        else:
                            send("🐻 لا توجد قطاعات نشطة حالياً")
                    else:
                        send("🐻 جاري جمع البيانات...")
                else:
                    send("🟢 السوق صاعد - استخدم /watchlist لرؤية الفرص")

            elif text_lower in ("/help", "/مساعدة"):
                send(
                    "🤖 *MAFIO-BOT — الأوامر:*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "📊 /status      — حالة البوت\n"
                    "₿ /btc         — سعر BTC والاتجاه\n"
                    "🏆 /sectors     — أفضل القطاعات\n"
                    "👁️ /watchlist   — قائمة المراقبة\n"
                    "📅 /report      — التقرير اليومي\n"
                    "📈 /performance — نسبة نجاح الإشارات\n"
                    "🐻 /bear        — حالة السوق الهابط\n"
                    "🎯 /bearcoins   — فرص الدخول في السوق الهابط\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "💎 /gems        — الجواهر المرصودة\n"
                    "🃏 /joker       — عملات تنتظر الجوكر"
                )

            elif text_lower in ("/stop", "/ايقاف"):
                send("⏸️ تم إيقاف التنبيهات مؤقتاً — اكتب /start للعودة")
                import builtins
                builtins._mafio_paused = True

            elif text_lower in ("/start", "/تشغيل"):
                import builtins
                builtins._mafio_paused = False
                send("✅ التنبيهات تعمل الآن!")

    except Exception as e:
        log.debug("poll_commands error: %s", e)


# ==================== دالة send_daily_report الأساسية ====================

def send_daily_report(force=False):
    global daily_report_sent_date
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now_utc.strftime("%Y-%m-%d")

    if not force and not _force_daily_report:
        if now_utc.hour != 0:
            return
        if daily_report_sent_date == today:
            return

    daily_report_sent_date = today
    send("📊 *DAILY REPORT*\n━━━━━━━━━━━━━━━━━━\nجاري إعداد التقرير...")


# ==================== تعريف SECTORS (من الكود الأصلي) ====================
# يتم وضع تعريف SECTORS الأصلي هنا
SECTORS = {
    "AI": ["FETUSDT", "AGIXUSDT", "WLDUSDT", "ARKMUSDT"],
    "Meme": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "WIFUSDT"],
    "Layer1": ["AVAXUSDT", "ADAUSDT", "SOLUSDT", "NEARUSDT"],
    "DeFi": ["AAVEUSDT", "UNIUSDT", "CAKEUSDT"],
    "Gaming": ["GALAUSDT", "AXSUSDT", "SANDUSDT"],
    "RWA": ["ONDOUSDT", "CFGUSDT"],
    "Storage": ["FILUSDT", "ARUSDT"],
    "DePIN": ["IOTAUSDT", "HNTUSDT"],
}


# ==================== BearMarketLiquidityHunter طرق إضافية ====================

def get_bear_opportunities(self, sector, price_map, vol_now, change_now):
    """الحصول على أفضل فرص الدخول في قطاع معين خلال السوق الهابط"""
    opportunities = []
    coins = SECTORS.get(sector, [])

    for sym in coins:
        vol = vol_now.get(sym, 0)
        chg = change_now.get(sym, 0)
        price = price_map.get(sym, 0)

        if vol < 100000:
            continue

        if chg < -2.0:
            continue

        stats = analyze_tps_ats(sym)
        if not stats:
            continue

        vdelta = stats.get("vdelta", 0)
        ats = stats.get("ats", 0)
        tps = stats.get("tps", 0)

        vol_ratio = get_coin_vol_ratio(sym, vol)

        score = 0
        if vol_ratio >= 2.0:
            score += 25
        elif vol_ratio >= 1.5:
            score += 15

        if vdelta >= 0.70:
            score += 35
        elif vdelta >= 0.65:
            score += 25

        if ats >= 2000:
            score += 25
        elif ats >= 500:
            score += 15

        if chg > 0:
            score += 20
        elif chg > -1.0:
            score += 10

        if score >= 50:
            opportunities.append({
                "sym": sym,
                "price": price,
                "chg": chg,
                "vol_ratio": vol_ratio,
                "vdelta": vdelta,
                "ats": ats,
                "tps": tps,
                "score": score
            })

    opportunities.sort(key=lambda x: -x["score"])
    return opportunities[:10]


# إضافة الطرق إلى الكلاس
BearMarketLiquidityHunter.get_bear_opportunities = get_bear_opportunities

# ==================== إعداد logging ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("mafio_bot.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("MafioBot")

# ==================== دالة run الأساسية ====================

def refresh_tickers():
    global all_tickers, changes_map, candidates, last_tickers
    data = safe_get("https://api.mexc.com/api/v3/ticker/24hr")
    if not data:
        return
    all_tickers = data
    changes_map = {}
    vol_map = {}
    for t in data:
        sym = t.get("symbol", "")
        try:
            ch = float(t["priceChangePercent"])
            vol = float(t["quoteVolume"])
            changes_map[sym] = ch
            vol_map[sym] = vol
        except (KeyError, ValueError):
            pass

    our_coins = set(sym for coins in SECTORS.values() for sym in coins)
    candidates = [
        sym for sym in our_coins
        if sym not in {"BTCUSDT", "ETHUSDT", "BNBUSDT"} and
           vol_map.get(sym, 0) >= 300000 and
           vol_map.get(sym, 0) <= 80000000
    ]
    last_tickers = time.time()
    log.info("📋 Candidates: %d coins", len(candidates))


def analyze_btc():
    global btc_change_24h, btc_trend_1h, btc_trend_4h, market_state, last_btc
    global last_market_report, eth_change_24h, btc_tps_stats, eth_tps_stats

    data = safe_get("https://api.mexc.com/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
    if not data:
        return

    try:
        last_price = float(data.get("lastPrice", 0))
        open_price = float(data.get("openPrice", last_price))
        if open_price > 0:
            btc_change_24h = (last_price - open_price) / open_price * 100
        else:
            btc_change_24h = float(data.get("priceChangePercent", 0))
    except (KeyError, ValueError, TypeError):
        pass

    kd1 = get_klines("BTCUSDT", "1h", 4)
    if kd1 and len(kd1["closes"]) >= 2:
        c = kd1["closes"]
        btc_trend_1h = (c[-1] - c[-2]) / c[-2] * 100 if c[-2] > 0 else 0.0

    kd4 = get_klines("BTCUSDT", "4h", 3)
    if kd4 and len(kd4["closes"]) >= 2:
        c4 = kd4["closes"]
        btc_trend_4h = (c4[-1] - c4[-2]) / c4[-2] * 100 if c4[-2] > 0 else 0.0

    eth_data = safe_get("https://api.mexc.com/api/v3/ticker/24hr", {"symbol": "ETHUSDT"})
    if eth_data:
        try:
            _elp = float(eth_data.get("lastPrice", 0))
            _eop = float(eth_data.get("openPrice", _elp))
            if _eop > 0:
                eth_change_24h = (_elp - _eop) / _eop * 100
        except (KeyError, ValueError, TypeError):
            pass

    _btc_tps = analyze_tps_ats("BTCUSDT")
    if _btc_tps:
        btc_tps_stats = _btc_tps
    _eth_tps = analyze_tps_ats("ETHUSDT")
    if _eth_tps:
        eth_tps_stats = _eth_tps

    last_btc = time.time()


def init_static_watchlist():
    global watchlist, wl_price_snapshot
    if not all_tickers:
        return

    ticker_map = {t["symbol"]: t for t in all_tickers}
    _static = [
        ("AVAXUSDT", "Layer1", "L1 قوي"),
        ("LINKUSDT", "DeFi", "Oracle رائد"),
        ("SOLUSDT", "Layer1", "L1 الأقوى"),
        ("DOGEUSDT", "Meme", "Meme الأكبر"),
        ("PEPEUSDT", "Meme", "Meme ساخن"),
    ]

    for sym, sector, reason in _static:
        if sym in watchlist:
            continue
        t = ticker_map.get(sym)
        if not t:
            continue
        try:
            price = float(t["lastPrice"])
            vol = float(t["quoteVolume"])
            watchlist[sym] = {
                "since": time.time(),
                "reason": reason,
                "vol": vol,
                "sector": sector,
                "priority": "STATIC",
            }
            wl_price_snapshot[sym] = price
        except Exception:
            continue


def auto_expand_sectors():
    pass


def analyze_sectors():
    pass


def refresh_sector_report():
    pass


def scan_sector_activity():
    pass


def update_sector_flow(ticker_map):
    pass


def check_trailing_stops():
    pass


def check_watchlist_entries():
    pass


def scan_instant_movers():
    pass


def scan_realtime_liquidity():
    pass


def scan_hot_market():
    pass


def scan_bottom_accumulation():
    pass


def scan_ath_distance():
    pass


def cleanup():
    pass


def save_state():
    pass


def load_state():
    pass


def track_global_liquidity():
    pass


def flush_signal_queue(max_send=5):
    pass


def scan_pump_dump(price_map, vol_now, change_now):
    pass


def update_pump_dump_history(price_map, vol_now):
    pass


def track_liquidity_flow(vol_now, change_now):
    pass


def check_liquidity_exit(vol_now, price_map):
    pass


def scan_lz_tps_fusion(price_map, vol_now, changes_map):
    pass


def scan_whale_confirmation(price_map):
    pass


def liquidity_hunter(price_map, vol_now, changes_map):
    pass


def liquidity_hunter_small_caps(price_map, vol_now, changes_map):
    pass


def scan_hidden_accumulation(price_map, vol_now, changes_map):
    pass


def get_btc_dominance(vol_now):
    return 50.0


def scan_pre_explosion(price_map, vol_now, change_now):
    pass


def scan_liquidity_radar(vol_now, change_now, price_map):
    pass


def update_adaptive_mode(vol_now, change_now):
    pass


def scan_volume_surge(price_map, vol_now, changes_map):
    pass


def scan_bottom_fisher(price_map, vol_now, changes_map):
    pass


def deep_scan(symbol, price, change, fetch_orderbook=True):
    pass


def calc_vdelta_ma(sym, period=10, interval="15m"):
    return 0.5


def get_btc_dominance(vol_now):
    return 50.0


def check_btc_dominance(vol_now):
    pass


# ==================== الحلقة الرئيسية ====================

def run():
    global all_tickers, candidates, hot_sectors, market_state, btc_change_24h
    global last_btc, last_sectors, last_deep_scan, last_stale, last_expand
    global last_ts_scan, last_wl_check, last_rt_scan, last_tps_scan, last_lh_scan
    global last_sc_refresh, last_ath_scan, last_bottom_scan, last_sector_report
    global last_whale_check, last_sr_alert, price_map, vol_now, change_now
    global last_bear_scan

    log.info("🚀 MAFIO-BOT V22 - LIQUIDITY MASTER يبدأ...")
    log.info("🎯 خاصية جديدة: رصد السيولة حتى في السوق الهابط!")

    time.sleep(15)
    load_state()

    analyze_btc()
    refresh_tickers()
    time.sleep(2)

    refresh_tickers()
    init_static_watchlist()
    auto_expand_sectors()

    analyze_sectors()
    last_sector_report = time.time()

    log.info("✅ Ready | Candidates: %d | Hot: %s", len(candidates), ", ".join(hot_sectors) or "لا يوجد")

    last_deep_scan = 0
    last_lh_scan = 0
    last_sc_refresh = 0
    last_sr_alert = 0
    last_bear_scan = 0

    # إنشاء كائن BearMarketLiquidityHunter
    bear_hunter = BearMarketLiquidityHunter()

    send(
        f"💀 *MAFIO-BOT V22* 💀\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ رصد السيولة حتى في السوق الهابط\n"
        f"✅ تتبع أين تذهب الأموال\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"₿ BTC: `{btc_change_24h:+.2f}%` | السوق: `{market_state}`\n"
        f"🔥 Hot: `{', '.join(hot_sectors) or 'لا يوجد'}`"
    )

    cycle = 0
    flow_cycle = 0

    # متغيرات عامة للاستخدام في الأوامر
    global price_map, vol_now, change_now
    price_map = {}
    vol_now = {}
    change_now = {}

    while True:
        try:
            now = time.time()

            # حفظ الحالة كل 30 دقيقة
            if int(now) % 1800 < 12:
                save_state()

            # فحص الـ Trailing Stop
            if now - last_ts_scan >= 300:
                check_trailing_stops()
                last_ts_scan = now

            # فحص قائمة المراقبة
            if now - last_wl_check >= 60:
                check_watchlist_entries()
                last_wl_check = now

            # مسح السيولة الفورية
            if now - last_rt_scan >= 900:
                scan_instant_movers()
                scan_realtime_liquidity()
                last_rt_scan = now

            # استماع لأوامر Telegram
            poll_commands()

            # تحليل BTC
            if now - last_btc >= 300:
                analyze_btc()
                last_btc = now

            # تحليل القطاعات
            if now - last_sectors >= 600:
                analyze_sectors()
                last_sectors = now

            # تحديث تقرير القطاعات
            refresh_sector_report()

            # ==================== فحص السيولة في السوق الهابط ====================
            if now - last_bear_scan >= 300:
                bear_hunter.is_bear = bear_hunter.is_bear_market()
                if bear_hunter.is_bear:
                    bear_hunter.scan_bear_liquidity_signals(vol_now, change_now, price_map)
                last_bear_scan = now

            # جلب بيانات السوق
            tickers_now = safe_get("https://api.mexc.com/api/v3/ticker/24hr")
            if not tickers_now:
                time.sleep(12)
                continue

            all_tickers = tickers_now

            # تحديث الخرائط
            for t in tickers_now:
                sym = t.get("symbol", "")
                try:
                    last = float(t["lastPrice"])
                    open_ = float(t.get("openPrice", last))
                    real_change = (last - open_) / open_ * 100 if open_ > 0 else float(t["priceChangePercent"])
                    price_map[sym] = last
                    change_now[sym] = real_change
                    vol_now[sym] = float(t["quoteVolume"])
                except (KeyError, ValueError):
                    pass

            changes_map.update(change_now)
            update_coin_vol_history(vol_now)

            # تحديث قائمة المرشحين
            if now - last_tickers >= 1800:
                refresh_tickers()
                last_tickers = now

            # تحديث تدفق القطاعات
            ticker_map = {t["symbol"]: t for t in tickers_now}
            update_sector_flow(ticker_map)
            flow_cycle += 1

            if flow_cycle >= 5:
                analyze_sector_flow()
                flow_cycle = 0

            # مسح السيولة
            if now - last_tps_scan >= 300:
                scan_liquidity_radar(vol_now, change_now, price_map)
                scan_pre_explosion(price_map, vol_now, change_now)
                last_tps_scan = now

            if now - last_lh_scan >= 300:
                liquidity_hunter(price_map, vol_now, changes_map)
                last_lh_scan = now

            if now - last_sc_refresh >= 3600:
                refresh_small_caps()
                last_sc_refresh = now

            # الفحص العميق
            if now - last_deep_scan >= 3600:
                pre_scored = []
                for sym in candidates:
                    if sym in tracked:
                        continue
                    price = price_map.get(sym, 0)
                    change = changes_map.get(sym, 0)
                    vol = vol_now.get(sym, 0)
                    if price <= 0:
                        continue
                    pre_score = (vol / 1_000_000) * 0.5 + max(change, 0) * 0.3
                    pre_scored.append((sym, price, change, pre_score))

                pre_scored.sort(key=lambda x: -x[3])
                scanned = 0
                for rank, (sym, price, change, _) in enumerate(pre_scored[:50]):
                    fetch_ob = (rank < 20)
                    deep_scan(sym, price, change, fetch_orderbook=fetch_ob)
                    scanned += 1
                    if scanned % 10 == 0:
                        time.sleep(0.5)
                last_deep_scan = now
                log.info("✅ Deep Scan | %d coins", scanned)

            # إرسال التقرير اليومي
            send_daily_report()

            # تنظيف
            if now - last_stale >= 3600:
                cleanup()
                last_stale = now

            cycle += 1
            time.sleep(12)

        except KeyboardInterrupt:
            send("⛔ *MAFIO-BOT* — تم الإيقاف")
            break
        except Exception as e:
            log.error("Error: %s", e, exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    run()
