#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     MAFIO BOT — LIQUIDITY HUNTER PRO                        ║
║                     🎯 اصطياد الانفجارات قبل حدوثها                          ║
║                                                                             ║
║  🔥 استراتيجيات متعددة: TPS/ATS + Liquidity Zones + Pre-Explosion           ║
║  🧠 ذكاء: VDelta MA + CVD + Order Book + Multi-Timeframe                    ║
║  ⚡ سرعة: Async + WebSocket + Smart Cache                                   ║
║  🛡️ حماية: Trailing Stop + ATR + Risk Management                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import math
import asyncio
import aiohttp
import websockets
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Set, Any
from collections import deque, defaultdict
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

# ==================== إعدادات النظام ====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
GROUP_ID = os.getenv("GROUP_ID", "")

# توقيتات
CHECK_INTERVAL = 12
WEBSOCKET_RECONNECT = 30
CACHE_15M = 60
CACHE_1H = 300
CACHE_4H = 900

# عتبات الذكاء
VDELTA_MIN = 0.65
VDELTA_STRONG = 0.75
TPS_SPIKE = 2.0
ATS_WHALE = 2000
ATS_MIN = 100

# أحجام العملات
TIER_SETTINGS = {
    "big": {"vdelta_min": 0.60, "ats_min": 200, "vol_min": 10_000_000, "label": "Big Cap 🏦"},
    "mid": {"vdelta_min": 0.58, "ats_min": 100, "vol_min": 1_000_000, "label": "Mid Cap 📊"},
    "small": {"vdelta_min": 0.55, "ats_min": 50, "vol_min": 100_000, "label": "Small Cap 🚀"},
}

# القطاعات
SECTORS = {
    "Meme": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "WIFUSDT", "BONKUSDT", "BOMEUSDT", "WIFUSDT"],
    "AI": ["FETUSDT", "AGIXUSDT", "WLDUSDT", "ARKMUSDT", "RENDERUSDT", "VIRTUSDT", "NEUROUSDT"],
    "Layer1": ["SOLUSDT", "AVAXUSDT", "ADAUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT", "INJUSDT"],
    "DeFi": ["AAVEUSDT", "UNIUSDT", "LINKUSDT", "CAKEUSDT", "MKRUSDT", "LDOUSDT"],
    "DePIN": ["IOTAUSDT", "HNTUSDT", "LPTUSDT", "GRASSUSDT"],
    "Gaming": ["GALAUSDT", "AXSUSDT", "SANDUSDT", "IMXUSDT", "PIXELUSDT"],
    "RWA": ["ONDOUSDT", "CFGUSDT", "MANTRAUSDT"],
    "Storage": ["FILUSDT", "ARUSDT", "STORJUSDT"],
}

EXCLUDED = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "USDTUSDC", "EURUSDT"}
STABLECOINS = {"USDC", "BUSD", "FDUSD", "DAI", "TUSD", "USDD", "USDE"}
LEVERAGE_KEYWORDS = ["3L", "3S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN"]

# ==================== Logging ====================

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

# ==================== هياكل البيانات ====================

class SignalType(Enum):
    WATCH = "👁️ مراقبة"
    ENTRY = "✅ دخول"
    PRE_EXPLOSION = "🎯 قبل الانفجار"
    EXPLOSION = "💥 انفجار"
    GOLDEN = "🏆 ذهبي"

@dataclass
class MarketData:
    symbol: str
    price: float = 0.0
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    last_update: float = 0.0
    
    # مؤشرات حية
    tps: float = 0.0
    ats: float = 0.0
    vdelta: float = 0.5
    ob_imbalance: float = 1.0
    volume_spike: float = 1.0
    
    # التاريخ
    trades_buffer: deque = field(default_factory=lambda: deque(maxlen=100))
    price_history: deque = field(default_factory=lambda: deque(maxlen=50))
    volume_history: deque = field(default_factory=lambda: deque(maxlen=20))

@dataclass
class WatchItem:
    symbol: str
    entry_time: float
    initial_price: float
    initial_ats: float
    initial_vdelta: float
    sector: str
    tier: str

@dataclass  
class Position:
    symbol: str
    entry_price: float
    peak_price: float
    stop_loss: float
    trailing_active: bool = False
    entry_time: float = 0.0

# ==================== النظام الرئيسي ====================

class MafioBot:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.data_cache: Dict[str, MarketData] = {}
        self.watchlist: Dict[str, WatchItem] = {}
        self.positions: Dict[str, Position] = {}
        self.klines_cache: Dict[str, Tuple[Any, float]] = {}
        
        # حالة السوق
        self.btc_change_24h = 0.0
        self.btc_trend_1h = 0.0
        self.market_state = "SAFE"
        self.hot_sectors: List[str] = []
        
        # إحصائيات
        self.signals_sent = 0
        self.api_calls = 0
        self.last_api_reset = time.time()
        
        # WebSocket
        self.ws_connected = False
        self.active_symbols: Set[str] = set()
        
    async def init(self):
        """تهيئة الجلسة"""
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100),
            timeout=aiohttp.ClientTimeout(total=10)
        )
        log.info("🚀 Mafio Bot initialized")
        
    def get_tier(self, vol: float) -> str:
        """تحديد حجم العملة"""
        if vol >= 10_000_000:
            return "big"
        elif vol >= 1_000_000:
            return "mid"
        return "small"
    
    def fmt_price(self, p: float) -> str:
        """تنسيق السعر"""
        if p == 0:
            return "0"
        if p < 0.0001:
            return f"{p:.10f}".rstrip("0")
        if p < 1:
            return f"{p:.8f}".rstrip("0")
        if p < 1000:
            return f"{p:.4f}".rstrip("0").rstrip(".")
        return f"{p:,.2f}"
    
    async def send_telegram(self, msg: str, personal_only: bool = False):
        """إرسال رسالة Telegram"""
        if not TELEGRAM_TOKEN or len(TELEGRAM_TOKEN) < 10:
            log.info(f"[TELEGRAM] {msg[:80]}")
            return
            
        targets = [CHAT_ID]
        if GROUP_ID and not personal_only:
            targets.append(GROUP_ID)
            
        for chat_id in targets:
            if not chat_id:
                continue
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                async with self.session.post(url, json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "Markdown"
                }) as resp:
                    if resp.status != 200:
                        log.error(f"Telegram error: {await resp.text()}")
            except Exception as e:
                log.error(f"Send error: {e}")
    
    async def safe_get(self, url: str, params: dict = None, retries: int = 3) -> Optional[Any]:
        """طلب API آمن"""
        for attempt in range(retries):
            try:
                async with self.session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        self.api_calls += 1
                        now = time.time()
                        if now - self.last_api_reset >= 60:
                            log.info(f"📡 API: {self.api_calls} req/min")
                            self.api_calls = 0
                            self.last_api_reset = now
                        return await resp.json()
            except Exception as e:
                wait = 2 ** attempt
                log.debug(f"API retry {attempt+1}/{retries}: {e}")
                await asyncio.sleep(wait)
        return None
    
    async def fetch_top_symbols(self) -> List[str]:
        """جلب أفضل 100 عملة"""
        url = "https://api.mexc.com/api/v3/ticker/24hr"
        data = await self.safe_get(url)
        if not data:
            return []
            
        symbols = []
        for item in data:
            sym = item.get("symbol", "")
            if not sym.endswith("USDT"):
                continue
            if any(k in sym for k in LEVERAGE_KEYWORDS):
                continue
            if sym in EXCLUDED:
                continue
                
            try:
                vol = float(item.get("quoteVolume", 0))
                change = float(item.get("priceChangePercent", 0))
                # فلترة العملات المشبوهة
                if vol < 100_000 or vol > 100_000_000:
                    continue
                if abs(change) > 50:  # تجنب pump & dump
                    continue
                symbols.append((sym, vol * (1 + abs(change)/100)))
            except:
                continue
                
        symbols.sort(key=lambda x: -x[1])
        return [s[0] for s in symbols[:80]]
    
    async def get_klines(self, symbol: str, interval: str = "15m", limit: int = 50) -> Optional[Dict]:
        """جلب بيانات الشموع مع كاش"""
        key = f"{symbol}_{interval}"
        now = time.time()
        
        if key in self.klines_cache:
            data, ts = self.klines_cache[key]
            cache_ttl = {"15m": CACHE_15M, "1h": CACHE_1H, "4h": CACHE_4H}.get(interval, CACHE_15M)
            if now - ts < cache_ttl:
                return data
        
        url = "https://api.mexc.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        raw = await self.safe_get(url, params)
        
        if not raw or len(raw) < 6:
            return None
            
        try:
            result = {
                "opens": [float(c[1]) for c in raw],
                "highs": [float(c[2]) for c in raw],
                "lows": [float(c[3]) for c in raw],
                "closes": [float(c[4]) for c in raw],
                "vols": [float(c[5]) for c in raw],
                "avg_vol": sum([float(c[5]) for c in raw[:-1]]) / max(len(raw)-1, 1)
            }
            self.klines_cache[key] = (result, now)
            return result
        except:
            return None
    
    def calc_vdelta_ma(self, symbol: str, period: int = 10) -> float:
        """حساب VDelta Moving Average"""
        kd = self.data_cache.get(symbol)
        if not kd:
            return 0.5
            
        # استخدام Klines إذا متاح
        klines = asyncio.run(self.get_klines(symbol, "15m", period + 5))
        if klines and len(klines["closes"]) >= period:
            closes = klines["closes"]
            opens = klines["opens"]
            vols = klines["vols"]
            
            buy_vol = sum(vols[i] for i in range(len(closes)) if closes[i] > opens[i])
            total_vol = sum(vols)
            
            if total_vol > 0:
                return round(buy_vol / total_vol, 3)
        
        # Fallback: استخدام trades buffer
        if not kd.trades_buffer:
            return 0.5
            
        buy_val = sum(t.get("value", 0) for t in kd.trades_buffer if not t.get("is_sell", False))
        total_val = sum(t.get("value", 0) for t in kd.trades_buffer)
        
        return round(buy_val / total_val, 3) if total_val > 0 else 0.5
    
    def calc_cvd(self, symbol: str) -> Dict:
        """حساب Cumulative Volume Delta"""
        kd = asyncio.run(self.get_klines(symbol, "1h", 24))
        if not kd or len(kd["closes"]) < 10:
            return {"trend": "flat", "slope": 0, "pct_change": 0}
        
        closes = kd["closes"]
        opens = kd["opens"]
        vols = kd["vols"]
        
        cvd_values = []
        cumulative = 0.0
        
        for i in range(len(closes)):
            vol = vols[i]
            if closes[i] > opens[i]:
                delta = vol
            elif closes[i] < opens[i]:
                delta = -vol
            else:
                delta = 0
            cumulative += delta
            cvd_values.append(cumulative)
        
        if len(cvd_values) < 5:
            return {"trend": "flat", "slope": 0, "pct_change": 0}
        
        recent = cvd_values[-12:]
        first_half = sum(recent[:6]) / 6
        second_half = sum(recent[6:]) / 6
        slope = second_half - first_half
        
        if abs(first_half) > 0:
            pct_change = (second_half - first_half) / abs(first_half) * 100
        else:
            pct_change = 0
        
        if slope > 0 and pct_change > 5:
            trend = "rising"
        elif slope < 0 and pct_change < -5:
            trend = "falling"
        else:
            trend = "flat"
        
        return {"trend": trend, "slope": round(slope, 2), "pct_change": round(pct_change, 1)}
    
    async def analyze_tps_ats(self, symbol: str) -> Optional[Dict]:
        """تحليل TPS/ATS/VDelta"""
        url = "https://api.mexc.com/api/v3/trades"
        data = await self.safe_get(url, {"symbol": symbol, "limit": 100})
        
        if not data or len(data) < 10:
            return None
        
        try:
            now_ms = int(time.time() * 1000)
            window_ms = 30000  # 30 ثانية
            
            all_vol = 0.0
            trade_window = 0
            sizes = []
            
            for t in data:
                price = float(t.get("price", 0))
                qty = float(t.get("qty", 0))
                ts = int(t.get("time", 0))
                val = price * qty
                
                all_vol += val
                sizes.append(val)
                
                if now_ms - ts <= window_ms:
                    trade_window += 1
            
            if all_vol <= 0:
                return None
            
            tps = trade_window / 30.0
            ats = all_vol / len(data)
            
            # حساب VDelta
            vdelta = self.calc_vdelta_ma(symbol)
            
            # تحديد نوع المشتري
            if ats >= ATS_WHALE:
                buyer_type = "🐋 حيتان ضخمة"
            elif ats >= 1000:
                buyer_type = "🐋 حيتان"
            elif ats >= 200:
                buyer_type = "🐟 متوسط"
            else:
                buyer_type = "🦐 أفراد"
            
            return {
                "tps": round(tps, 2),
                "ats": round(ats, 2),
                "vdelta": vdelta,
                "buyer_type": buyer_type,
                "trade_count": len(data)
            }
        except Exception as e:
            log.debug(f"TPS analysis error: {e}")
            return None
    
    async def get_order_book(self, symbol: str) -> Optional[Dict]:
        """جلب Order Book"""
        url = "https://api.mexc.com/api/v3/depth"
        data = await self.safe_get(url, {"symbol": symbol, "limit": 20})
        
        if not data:
            return None
        
        try:
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            bid_vol = sum(float(b[0]) * float(b[1]) for b in bids[:10])
            ask_vol = sum(float(a[0]) * float(a[1]) for a in asks[:10])
            
            total = bid_vol + ask_vol
            imbalance = bid_vol / ask_vol if ask_vol > 0 else 99
            
            return {
                "bid": bid_vol,
                "ask": ask_vol,
                "imbalance": round(imbalance, 2),
                "signal": "strong_buy" if imbalance >= 2 else "buy" if imbalance >= 1.5 else "neutral"
            }
        except:
            return None
    
    async def analyze_btc(self):
        """تحليل حالة BTC"""
        url = "https://api.mexc.com/api/v3/ticker/24hr"
        data = await self.safe_get(url, {"symbol": "BTCUSDT"})
        
        if not data:
            return
        
        try:
            last = float(data.get("lastPrice", 0))
            open_p = float(data.get("openPrice", last))
            self.btc_change_24h = (last - open_p) / open_p * 100 if open_p > 0 else 0
        except:
            pass
        
        # تحليل 1h
        kd = await self.get_klines("BTCUSDT", "1h", 3)
        if kd and len(kd["closes"]) >= 2:
            self.btc_trend_1h = (kd["closes"][-1] - kd["closes"][-2]) / kd["closes"][-2] * 100
        
        # تحديد حالة السوق
        if self.btc_change_24h <= -3:
            self.market_state = "DANGER"
        elif self.btc_change_24h <= -1.5:
            self.market_state = "CAUTION"
        else:
            self.market_state = "SAFE"
    
    def unified_filter(self, symbol: str, vdelta: float, ats: float, vol: float, change: float, tier: str) -> Tuple[bool, str]:
        """الفلتر الذكي الموحد"""
        settings = TIER_SETTINGS[tier]
        
        # 1. VDelta check
        min_vd = settings["vdelta_min"]
        if vdelta < min_vd:
            return False, f"VDelta {vdelta*100:.0f}% < {min_vd*100:.0f}%"
        
        # 2. Market state check
        if self.market_state == "DANGER" and vdelta < 0.70:
            return False, "السوق DANGER + VDelta ضعيف"
        
        # 3. Trend check
        if change < -8:
            return False, f"ترند هابط قوي {change:.1f}%"
        
        if change > 20:
            return False, f"Pump مكتمل {change:.1f}%"
        
        # 4. Volume check
        if vol < settings["vol_min"]:
            return False, f"حجم ناقص {vol/1000:.0f}K"
        
        # 5. CVD check
        cvd = self.calc_cvd(symbol)
        if cvd["trend"] == "falling" and cvd["pct_change"] < -10:
            return False, f"CVD هابط {cvd['pct_change']:.0f}%"
        
        return True, "OK"
    
    def detect_pre_explosion(self, symbol: str, data: MarketData, stats: Dict) -> Optional[SignalType]:
        """كشف ما قبل الانفجار"""
        score = 0
        signals = []
        
        # 1. Volume spike
        vol_ratio = data.volume_spike
        if vol_ratio >= 3.0:
            score += 30
            signals.append(f"💥 حجم {vol_ratio:.1f}x")
        elif vol_ratio >= 2.0:
            score += 20
            signals.append(f"🔥 حجم {vol_ratio:.1f}x")
        elif vol_ratio >= 1.5:
            score += 10
            signals.append(f"📈 حجم {vol_ratio:.1f}x")
        
        # 2. VDelta strength
        vdelta = stats["vdelta"]
        if vdelta >= 0.80:
            score += 25
            signals.append(f"💪 VDelta {vdelta*100:.0f}%")
        elif vdelta >= 0.70:
            score += 15
            signals.append(f"✅ VDelta {vdelta*100:.0f}%")
        
        # 3. TPS acceleration
        tps = stats["tps"]
        if tps >= 5.0:
            score += 20
            signals.append(f"⚡ TPS {tps:.1f}")
        elif tps >= 2.0:
            score += 10
            signals.append(f"🚀 TPS {tps:.1f}")
        
        # 4. Order Book Imbalance
        if data.ob_imbalance >= 2.0:
            score += 15
            signals.append(f"📊 OB {data.ob_imbalance:.1f}:1")
        elif data.ob_imbalance >= 1.5:
            score += 8
            signals.append(f"📊 OB {data.ob_imbalance:.1f}:1")
        
        # 5. CVD rising
        cvd = self.calc_cvd(symbol)
        if cvd["trend"] == "rising":
            score += 10
            signals.append(f"📈 CVD +{cvd['pct_change']:.0f}%")
        
        # تحديد نوع الإشارة
        if score >= 80:
            return SignalType.GOLDEN, score, signals
        elif score >= 65:
            return SignalType.PRE_EXPLOSION, score, signals
        elif score >= 50:
            return SignalType.WATCH, score, signals
        
        return None, 0, []
    
    async def scan_symbol(self, symbol: str, ticker_data: Dict):
        """فحص عملة واحدة"""
        try:
            price = float(ticker_data.get("lastPrice", 0))
            vol = float(ticker_data.get("quoteVolume", 0))
            change = float(ticker_data.get("priceChangePercent", 0))
            
            if vol < 100_000:
                return
            
            tier = self.get_tier(vol)
            sector = next((s for s, coins in SECTORS.items() if symbol in coins), "غير محدد")
            
            # تحليل TPS/ATS
            stats = await self.analyze_tps_ats(symbol)
            if not stats:
                return
            
            # تحديث الكاش
            if symbol not in self.data_cache:
                self.data_cache[symbol] = MarketData(symbol=symbol)
            
            data = self.data_cache[symbol]
            data.price = price
            data.tps = stats["tps"]
            data.ats = stats["ats"]
            data.vdelta = stats["vdelta"]
            
            # حساب volume spike
            if data.volume_history:
                avg_vol = sum(data.volume_history) / len(data.volume_history)
                data.volume_spike = vol / avg_vol if avg_vol > 0 else 1.0
            data.volume_history.append(vol)
            
            # Order Book
            ob = await self.get_order_book(symbol)
            if ob:
                data.ob_imbalance = ob["imbalance"]
            
            # الفلتر الموحد
            passed, reason = self.unified_filter(symbol, stats["vdelta"], stats["ats"], vol, change, tier)
            if not passed:
                log.debug(f"FILTER: {symbol} | {reason}")
                return
            
            # كشف Pre-Explosion
            signal_type, score, signals = self.detect_pre_explosion(symbol, data, stats)
            
            if not signal_type:
                return
            
            # منطق WATCH → ENTRY
            now = time.time()
            
            if signal_type == SignalType.WATCH and symbol not in self.watchlist:
                # إضافة للمراقبة
                self.watchlist[symbol] = WatchItem(
                    symbol=symbol,
                    entry_time=now,
                    initial_price=price,
                    initial_ats=stats["ats"],
                    initial_vdelta=stats["vdelta"],
                    sector=sector,
                    tier=tier
                )
                await self.send_watch_alert(symbol, price, stats, sector, tier, score, signals)
                
            elif symbol in self.watchlist and signal_type in [SignalType.PRE_EXPLOSION, SignalType.GOLDEN]:
                # تأكيد الدخول
                watch = self.watchlist[symbol]
                elapsed_min = (now - watch.entry_time) / 60
                
                # تحسن في المؤشرات؟
                ats_improved = stats["ats"] > watch.initial_ats * 1.5
                vdelta_improved = stats["vdelta"] > watch.initial_vdelta + 0.05
                
                if elapsed_min >= 3 and (ats_improved or vdelta_improved or score >= 70):
                    await self.send_entry_alert(symbol, price, stats, watch, score, signals, ats_improved, vdelta_improved)
                    del self.watchlist[symbol]
                    # فتح مركز
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        entry_price=price,
                        peak_price=price,
                        stop_loss=price * 0.95,
                        entry_time=now
                    )
                    
        except Exception as e:
            log.debug(f"Scan error {symbol}: {e}")
    
    async def send_watch_alert(self, symbol: str, price: float, stats: Dict, sector: str, tier: str, score: int, signals: List[str]):
        """إرسال تنبيه مراقبة"""
        tier_info = TIER_SETTINGS[tier]
        
        msg = (
            f"👁️ *WATCH ALERT — راقب هذه العملة*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 *{symbol.replace('USDT', '')}* — {tier_info['label']}\n"
            f"💵 السعر: `{self.fmt_price(price)}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 VDelta: `{stats['vdelta']*100:.0f}%` | ATS: `{stats['ats']:.0f}$`\n"
            f"⚡ TPS: `{stats['tps']:.2f}` | {stats['buyer_type']}\n"
            f"🏷️ القطاع: `{sector}`\n"
            f"💪 القوة: `{score}/100`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📡 *المؤشرات:*\n" + "\n".join(f"  • {s}" for s in signals[:4]) + "\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏳ _انتظر 3-5 دقائق للتأكيد..._"
        )
        
        await self.send_telegram(msg)
        self.signals_sent += 1
        log.info(f"WATCH | {symbol} | score={score} | ATS={stats['ats']:.0f}$")
    
    async def send_entry_alert(self, symbol: str, price: float, stats: Dict, watch: WatchItem, score: int, 
                              signals: List[str], ats_improved: bool, vdelta_improved: bool):
        """إرسال تنبيه دخول"""
        # حساب الأهداف والوقف
        target_1 = price * 1.10
        target_2 = price * 1.20
        target_3 = price * 1.35
        stop_loss = price * 0.95
        
        improvements = []
        if ats_improved:
            improvements.append(f"ATS +{((stats['ats']/watch.initial_ats)-1)*100:.0f}%")
        if vdelta_improved:
            improvements.append(f"VDelta +{(stats['vdelta']-watch.initial_vdelta)*100:.0f}%")
        
        imp_text = " | ".join(improvements) if improvements else "تأكيد قوي"
        
        msg = (
            f"🎯 *ENTRY CONFIRMED — ادخل الآن!*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💥 *{symbol.replace('USDT', '')}* — تأكيد الدخول!\n"
            f"💵 السعر: `{self.fmt_price(price)}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 التحسن: `{imp_text}`\n"
            f"⚡ TPS: `{stats['tps']:.2f}` | ATS: `{stats['ats']:.0f}$`\n"
            f"💚 VDelta: `{stats['vdelta']*100:.0f}%` | {stats['buyer_type']}\n"
            f"💪 القوة: `{score}/100` 🔥\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *الأهداف:*\n"
            f"  1️⃣ `{self.fmt_price(target_1)}` (+10%)\n"
            f"  2️⃣ `{self.fmt_price(target_2)}` (+20%)\n"
            f"  3️⃣ `{self.fmt_price(target_3)}` (+35%)\n"
            f"🛡️ *Stop Loss:* `{self.fmt_price(stop_loss)}` (-5%)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ *ادخل الآن — السيولة تتدفق!* 🚀"
        )
        
        await self.send_telegram(msg)
        log.info(f"ENTRY | {symbol} | score={score} | ATS={stats['ats']:.0f}$")
    
    async def check_positions(self):
        """فحص المراكز المفتوحة (Trailing Stop)"""
        now = time.time()
        
        for symbol, pos in list(self.positions.items()):
            data = self.data_cache.get(symbol)
            if not data:
                continue
            
            current_price = data.price
            
            # تحديث القمة
            if current_price > pos.peak_price:
                pos.peak_price = current_price
                # رفع الستوب
                new_stop = pos.peak_price * 0.90  # 10% trailing
                if new_stop > pos.stop_loss:
                    pos.stop_loss = new_stop
                    pos.trailing_active = True
            
            # فحص الستوب
            if current_price <= pos.stop_loss:
                # إغلاق المركز
                pnl = (current_price - pos.entry_price) / pos.entry_price * 100
                emoji = "✅" if pnl > 0 else "❌"
                
                msg = (
                    f"🔴 *POSITION CLOSED*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📍 *{symbol.replace('USDT', '')}*\n"
                    f"💵 دخول: `{self.fmt_price(pos.entry_price)}`\n"
                    f"💰 خروج: `{self.fmt_price(current_price)}`\n"
                    f"📊 النتيجة: `{pnl:+.2f}%` {emoji}\n"
                    f"⏱️ المدة: `{(now-pos.entry_time)/3600:.1f}h`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{'✅ ربح محمي!' if pnl > 0 else '❌ وقف الخسارة'}"
                )
                
                await self.send_telegram(msg)
                del self.positions[symbol]
                log.info(f"CLOSED | {symbol} | PnL={pnl:.2f}%")
    
    async def websocket_listener(self, symbols: List[str]):
        """WebSocket للبيانات اللحظية"""
        streams = "/".join([f"{s.lower()}@trade" for s in symbols[:50]])
        uri = f"wss://wbs.mexc.com/ws?streams={streams}"
        
        while True:
            try:
                async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                    log.info(f"🔗 WebSocket connected: {len(symbols[:50])} symbols")
                    self.ws_connected = True
                    
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            if "data" not in data:
                                continue
                            
                            trade = data["data"]
                            symbol = trade.get("s", "").upper()
                            
                            if symbol not in self.data_cache:
                                self.data_cache[symbol] = MarketData(symbol=symbol)
                            
                            # تحديث بيانات التريد
                            price = float(trade.get("p", 0))
                            qty = float(trade.get("q", 0))
                            is_buyer_maker = trade.get("m", False)
                            
                            data = self.data_cache[symbol]
                            data.price = price
                            data.trades_buffer.append({
                                "price": price,
                                "qty": qty,
                                "is_sell": is_buyer_maker,
                                "value": price * qty,
                                "time": time.time()
                            })
                            
                        except Exception as e:
                            log.debug(f"WS message error: {e}")
                            
            except Exception as e:
                log.error(f"WebSocket error: {e}")
                self.ws_connected = False
                await asyncio.sleep(WEBSOCKET_RECONNECT)
    
    async def main_loop(self):
        """الحلقة الرئيسية"""
        await self.init()
        
        # جلب العملات الأولية
        symbols = await self.fetch_top_symbols()
        self.active_symbols = set(symbols[:60])
        log.info(f"🎯 Monitoring {len(self.active_symbols)} symbols")
        
        # تشغيل WebSocket
        ws_task = asyncio.create_task(self.websocket_listener(list(self.active_symbols)))
        
        # تحليل BTC أولي
        await self.analyze_btc()
        
        # إرسال رسالة بدء
        await self.send_telegram(
            f"🚀 *Mafio Bot — Started*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 العملات: `{len(self.active_symbols)}`\n"
            f"₿ BTC: `{self.btc_change_24h:+.2f}%` | `{self.market_state}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ WebSocket: `Active`\n"
            f"🎯 Mode: `Liquidity Hunter`"
        )
        
        last_btc_check = 0
        last_position_check = 0
        
        while True:
            try:
                now = time.time()
                
                # تحديث BTC كل 5 دقائق
                if now - last_btc_check >= 300:
                    await self.analyze_btc()
                    last_btc_check = now
                
                # فحص المراكز كل دقيقة
                if now - last_position_check >= 60:
                    await self.check_positions()
                    last_position_check = now
                
                # جلب بيانات 24h
                ticker_data = await self.safe_get("https://api.mexc.com/api/v3/ticker/24hr")
                if ticker_data:
                    ticker_map = {t["symbol"]: t for t in ticker_data if t["symbol"] in self.active_symbols}
                    
                    # فحص كل عملة
                    tasks = [self.scan_symbol(sym, ticker_map[sym]) for sym in ticker_map if sym in self.active_symbols]
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                log.error(f"Main loop error: {e}")
                await asyncio.sleep(10)
    
    def run(self):
        """تشغيل البوت"""
        try:
            asyncio.run(self.main_loop())
        except KeyboardInterrupt:
            log.info("⛔ Stopped by user")
            asyncio.run(self.send_telegram("⛔ *Mafio Bot — Stopped*"))
        except Exception as e:
            log.error(f"Fatal error: {e}")

# ==================== التشغيل ====================

if __name__ == "__main__":
    bot = MafioBot()
    bot.run()
