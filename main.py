#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     MAFIO BOT — LIQUIDITY HUNTER PRO                        ║
║                     🎯 اصطياد الانفجارات قبل حدوثها                          ║
║                                                                             ║
║  ✅ محسّن: سرعة عالية + دقة أفضل + إشارات أسرع                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import math
import asyncio
import logging
import urllib.request
import ssl
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Set, Any
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

# ==================== إعدادات محسّنة ====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
GROUP_ID = os.getenv("GROUP_ID", "")

# ⬇️ تقليل التكرار لتقليل الضغط
CHECK_INTERVAL = 30           # كان 12، الآن 30 ثانية
MAX_SYMBOLS = 30              # كان 60، الآن 30 عملة فقط
MIN_VOLUME_USD = 500_000      # حد أدنى للحجم (تصفية مبكرة)

# توقيتات الكاش
CACHE_15M = 120               # 2 دقائق
CACHE_1H = 600                # 10 دقائق

# عتبات الذكاء - أكثر مرونة
VDELTA_MIN = 0.60             # كان 0.65
TPS_SPIKE = 1.5               # كان 2.0
ATS_WHALE = 1500              # كان 2000

# أحجام العملات
TIER_SETTINGS = {
    "big": {"vdelta_min": 0.55, "vol_min": 5_000_000, "label": "Big Cap 🏦"},
    "mid": {"vdelta_min": 0.52, "vol_min": 500_000, "label": "Mid Cap 📊"},
    "small": {"vdelta_min": 0.50, "vol_min": 100_000, "label": "Small Cap 🚀"},
}

# القطاعات
SECTORS = {
    "Meme": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "WIFUSDT", "BONKUSDT", "BOMEUSDT"],
    "AI": ["FETUSDT", "AGIXUSDT", "WLDUSDT", "ARKMUSDT", "RENDERUSDT"],
    "Layer1": ["SOLUSDT", "AVAXUSDT", "ADAUSDT", "NEARUSDT", "SUIUSDT"],
    "DeFi": ["AAVEUSDT", "UNIUSDT", "LINKUSDT", "MKRUSDT"],
    "Gaming": ["GALAUSDT", "AXSUSDT", "SANDUSDT", "IMXUSDT"],
}

EXCLUDED = {"BTCUSDT", "ETHUSDT", "BNBUSDT"}
LEVERAGE_KEYWORDS = ["3L", "3S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN"]

# ==================== Logging ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("MafioBot")

# ==================== HTTP Client محسّن ====================

class SimpleHTTPClient:
    def __init__(self):
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.api_calls = 0
        self.last_reset = time.time()
        self._cache = {}
        self._cache_time = {}
    
    async def get(self, url: str, params: dict = None, cache_ttl: int = 0, retries: int = 2) -> Optional[Any]:
        # كاش للطلبات المتكررة
        cache_key = f"{url}:{str(params)}"
        now = time.time()
        
        if cache_ttl > 0 and cache_key in self._cache:
            if now - self._cache_time.get(cache_key, 0) < cache_ttl:
                return self._cache[cache_key]
        
        if params:
            query = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{url}?{query}"
        
        for attempt in range(retries):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, 
                    lambda: urllib.request.urlopen(url, context=self.ssl_context, timeout=15)
                )
                data = json.loads(response.read().decode('utf-8'))
                
                # حفظ في الكاش
                if cache_ttl > 0:
                    self._cache[cache_key] = data
                    self._cache_time[cache_key] = now
                
                self.api_calls += 1
                if now - self.last_reset >= 60:
                    log.info(f"📡 API: {self.api_calls} req/min")
                    self.api_calls = 0
                    self.last_reset = now
                
                return data
                
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                else:
                    log.debug(f"API failed: {e}")
        
        return None

# ==================== هياكل البيانات ====================

class SignalType(Enum):
    WATCH = "👁️ مراقبة"
    ENTRY = "✅ دخول"
    PRE_EXPLOSION = "🎯 قبل الانفجار"
    GOLDEN = "🏆 ذهبي"

@dataclass
class MarketData:
    symbol: str
    price: float = 0.0
    vdelta: float = 0.5
    tps: float = 0.0
    ats: float = 0.0
    volume_spike: float = 1.0
    ob_imbalance: float = 1.0
    last_update: float = 0.0
    volume_history: deque = field(default_factory=lambda: deque(maxlen=10))

@dataclass
class WatchItem:
    symbol: str
    entry_time: float
    initial_price: float
    initial_ats: float
    sector: str

@dataclass  
class Position:
    symbol: str
    entry_price: float
    peak_price: float
    stop_loss: float
    entry_time: float = 0.0

# ==================== النظام الرئيسي ====================

class MafioBot:
    def __init__(self):
        self.http = SimpleHTTPClient()
        self.data_cache: Dict[str, MarketData] = {}
        self.watchlist: Dict[str, WatchItem] = {}
        self.positions: Dict[str, Position] = {}
        self.btc_change_24tc_change_24h = 0.0
        self.market_state = "SAFE"
        self.active_symbols: Set[str] = set()
        self.signals_sent = 0
        
    def get_tier(self, vol: float) -> str:
        if vol >= 5_000_000:
            return "big"
        elif vol >= 500_000:
            return "mid"
        return "small"
    
    def fmt_price(self, p: float) -> str:
        if p == 0:
            return "0"
        if p < 0.0001:
            return f"{p:.10f}".rstrip("0")
        if p < 1:
            return f"{p:.6f}"
        if p < 1000:
            return f"{p:.4f}"
        return f"{p:,.2f}"
    
    async def send_telegram(self, msg: str):
        if not TELEGRAM_TOKEN or len(TELEGRAM_TOKEN) < 10:
            log.info(f"[TELEGRAM] {msg[:100]}...")
            return
            
        targets = [c for c in [CHAT_ID, GROUP_ID] if c]
        
        for chat_id in targets:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                await self.http.post(url, {
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "Markdown"
                })
                await asyncio.sleep(0.5)  # تجنب الحظر
            except Exception as e:
                log.error(f"Telegram error: {e}")
    
    async def post(self, url: str, json_data: dict) -> bool:
        try:
            data = json.dumps(json_data).encode('utf-8')
            headers = {'Content-Type': 'application/json'}
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, context=self.http.ssl_context, timeout=10)
            )
            return response.getcode() == 200
        except Exception as e:
            log.debug(f"POST error: {e}")
            return False
    
    async def fetch_symbols(self) -> List[dict]:
        """جلب العملات مع تصفية مبكرة"""
        data = await self.http.get(
            "https://api.mexc.com/api/v3/ticker/24hr",
            cache_ttl=30  # كاش 30 ثانية
        )
        if not data:
            return []
        
        filtered = []
        for item in data:
            sym = item.get("symbol", "")
            
            # تصفية سريعة
            if not sym.endswith("USDT"):
                continue
            if any(k in sym for k in LEVERAGE_KEYWORDS):
                continue
            if sym in EXCLUDED:
                continue
            
            try:
                vol = float(item.get("quoteVolume", 0))
                change = float(item.get("priceChangePercent", 0))
                
                # تصفية مبكرة بالحجم
                if vol < MIN_VOLUME_USD:
                    continue
                if abs(change) > 30:  # تجنب المضاربات المجنونة
                    continue
                    
                filtered.append({
                    "symbol": sym,
                    "price": float(item.get("lastPrice", 0)),
                    "volume": vol,
                    "change": change,
                    "score": vol * (1 + abs(change)/100)
                })
            except:
                continue
        
        # ترتيب وأخذ الأفضل
        filtered.sort(key=lambda x: -x["score"])
        return filtered[:MAX_SYMBOLS]
    
    async def analyze_symbol(self, symbol_data: dict) -> Optional[Dict]:
        """تحليل سريع لعملة واحدة"""
        symbol = symbol_data["symbol"]
        price = symbol_data["price"]
        vol = symbol_data["volume"]
        change = symbol_data["change"]
        
        # جلب آخر 50 تريد فقط (طلب واحد)
        trades = await self.http.get(
            "https://api.mexc.com/api/v3/trades",
            {"symbol": symbol, "limit": 50},
            cache_ttl=10
        )
        
        if not trades or len(trades) < 5:
            return None
        
        # حساب سريع
        now_ms = int(time.time() * 1000)
        window_ms = 60000  # دقيقة واحدة
        
        buy_vol = 0.0
        total_vol = 0.0
        recent_trades = 0
        
        for t in trades:
            try:
                p = float(t.get("price", 0))
                q = float(t.get("qty", 0))
                ts = int(t.get("time", 0))
                is_buyer = not t.get("m", False)
                
                val = p * q
                total_vol += val
                if is_buyer:
                    buy_vol += val
                
                if now_ms - ts <= window_ms:
                    recent_trades += 1
            except:
                continue
        
        if total_vol <= 0:
            return None
        
        # المؤشرات
        vdelta = buy_vol / total_vol
        tps = recent_trades / 60.0  # trades per second
        ats = total_vol / len(trades)
        
        # فلتر سريع
        tier = self.get_tier(vol)
        min_vd = TIER_SETTINGS[tier]["vdelta_min"]
        
        if vdelta < min_vd:
            return None
        
        if self.market_state == "DANGER" and vdelta < 0.65:
            return None
        
        # Order Book (اختياري - فقط للمرشحين الجيدين)
        ob = await self.http.get(
            "https://api.mexc.com/api/v3/depth",
            {"symbol": symbol, "limit": 10},
            cache_ttl=5
        )
        
        ob_imbalance = 1.0
        if ob:
            try:
                bids = ob.get("bids", [])
                asks = ob.get("asks", [])
                bid_vol = sum(float(b[0]) * float(b[1]) for b in bids[:5])
                ask_vol = sum(float(a[0]) * float(a[1]) for a in asks[:5])
                ob_imbalance = bid_vol / ask_vol if ask_vol > 0 else 1.0
            except:
                pass
        
        # تحديث الكاش
        if symbol not in self.data_cache:
            self.data_cache[symbol] = MarketData(symbol=symbol)
        
        md = self.data_cache[symbol]
        md.price = price
        md.vdelta = round(vdelta, 3)
        md.tps = round(tps, 2)
        md.ats = round(ats, 2)
        md.ob_imbalance = round(ob_imbalance, 2)
        md.last_update = time.time()
        
        # Volume spike
        if md.volume_history:
            avg = sum(md.volume_history) / len(md.volume_history)
            md.volume_spike = round(vol / avg, 2) if avg > 0 else 1.0
        md.volume_history.append(vol)
        
        # حساب النقاط
        score = 0
        signals = []
        
        if md.volume_spike >= 2.0:
            score += 25
            signals.append(f"💥 حجم {md.volume_spike}x")
        elif md.volume_spike >= 1.5:
            score += 15
            signals.append(f"🔥 حجم {md.volume_spike}x")
        
        if vdelta >= 0.75:
            score += 25
            signals.append(f"💪 VDelta {vdelta*100:.0f}%")
        elif vdelta >= 0.65:
            score += 15
            signals.append(f"✅ VDelta {vdelta*100:.0f}%")
        
        if tps >= 3.0:
            score += 20
            signals.append(f"⚡ TPS {tps:.1f}")
        elif tps >= 1.5:
            score += 10
            signals.append(f"🚀 TPS {tps:.1f}")
        
        if ob_imbalance >= 2.0:
            score += 15
            signals.append(f"📊 OB {ob_imbalance:.1f}:1")
        
        # تحديد نوع الإشارة
        signal_type = None
        if score >= 70:
            signal_type = SignalType.GOLDEN
        elif score >= 55:
            signal_type = SignalType.PRE_EXPLOSION
        elif score >= 40:
            signal_type = SignalType.WATCH
        
        if not signal_type:
            return None
        
        sector = next((s for s, coins in SECTORS.items() if symbol in coins), "أخرى")
        
        return {
            "symbol": symbol,
            "price": price,
            "volume": vol,
            "change": change,
            "vdelta": vdelta,
            "tps": tps,
            "ats": ats,
            "score": score,
            "signals": signals,
            "signal_type": signal_type,
            "sector": sector,
            "tier": tier,
            "ob_imbalance": ob_imbalance
        }
    
    async def process_signals(self, results: List[Optional[Dict]]):
        """معالجة الإشارات وإرسالها"""
        now = time.time()
        
        for result in results:
            if not result:
                continue
            
            symbol = result["symbol"]
            signal_type = result["signal_type"]
            
            # WATCH
            if signal_type == SignalType.WATCH and symbol not in self.watchlist:
                self.watchlist[symbol] = WatchItem(
                    symbol=symbol,
                    entry_time=now,
                    initial_price=result["price"],
                    initial_ats=result["ats"],
                    sector=result["sector"]
                )
                await self.send_watch(result)
            
            # ENTRY
            elif symbol in self.watchlist and signal_type in [SignalType.PRE_EXPLOSION, SignalType.GOLDEN]:
                watch = self.watchlist[symbol]
                elapsed = (now - watch.entry_time) / 60
                
                improved = result["ats"] > watch.initial_ats * 1.3
                
                if elapsed >= 2 and (improved or result["score"] >= 60):
                    await self.send_entry(result, watch)
                    del self.watchlist[symbol]
                    
                    # فتح مركز
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        entry_price=result["price"],
                        peak_price=result["price"],
                        stop_loss=result["price"] * 0.95,
                        entry_time=now
                    )
    
    async def send_watch(self, r: Dict):
        tier_info = TIER_SETTINGS[r["tier"]]
        
        msg = (
            f"👁️ *WATCH — {r['symbol'].replace('USDT', '')}*\n"
            f"━━━━━━━━━━━━━━\n"
            f"💵 السعر: `{self.fmt_price(r['price'])}`\n"
            f"📊 VDelta: `{r['vdelta']*100:.0f}%` | ATS: `{r['ats']:.0f}$`\n"
            f"⚡ TPS: `{r['tps']:.2f}` | القوة: `{r['score']}/100`\n"
            f"🏷️ {tier_info['label']} | `{r['sector']}`\n"
            f"━━━━━━━━━━━━━━\n"
            f"⏳ انتظر التأكيد..."
        )
        
        await self.send_telegram(msg)
        self.signals_sent += 1
        log.info(f"👁️ WATCH | {r['symbol']} | score={r['score']}")
    
    async def send_entry(self, r: Dict, watch: WatchItem):
        t1 = r['price'] * 1.08
        t2 = r['price'] * 1.15
        t3 = r['price'] * 1.25
        sl = r['price'] * 0.95
        
        msg = (
            f"🎯 *ENTRY — {r['symbol'].replace('USDT', '')}*\n"
            f"━━━━━━━━━━━━━━\n"
            f"💵 الدخول: `{self.fmt_price(r['price'])}`\n"
            f"📊 VDelta: `{r['vdelta']*100:.0f}%` | القوة: `{r['score']}/100` 🔥\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎯 الأهداف:\n"
            f"  1️⃣ `{self.fmt_price(t1)}` (+8%)\n"
            f"  2️⃣ `{self.fmt_price(t2)}` (+15%)\n"
            f"  3️⃣ `{self.fmt_price(t3)}` (+25%)\n"
            f"🛡️ Stop: `{self.fmt_price(sl)}` (-5%)\n"
            f"━━━━━━━━━━━━━━\n"
            f"🚀 ادخل الآن!"
        )
        
        await self.send_telegram(msg)
        log.info(f"🎯 ENTRY | {r['symbol']} | score={r['score']}")
    
    async def check_positions(self):
        """فحص المراكز"""
        now = time.time()
        
        for symbol, pos in list(self.positions.items()):
            md = self.data_cache.get(symbol)
            if not md or time.time() - md.last_update > 60:
                continue
            
            price = md.price
            
            # تحديث القمة
            if price > pos.peak_price:
                pos.peak_price = price
                new_sl = pos.peak_price * 0.92
                if new_sl > pos.stop_loss:
                    pos.stop_loss = new_sl
            
            # إغلاق
            if price <= pos.stop_loss:
                pnl = (price - pos.entry_price) / pos.entry_price * 100
                
                msg = (
                    f"{'✅' if pnl > 0 else '❌'} *CLOSED — {symbol.replace('USDT', '')}*\n"
                    f"PnL: `{pnl:+.2f}%` | المدة: `{(now-pos.entry_time)/3600:.1f}h`"
                )
                
                await self.send_telegram(msg)
                del self.positions[symbol]
                log.info(f"CLOSED | {symbol} | PnL={pnl:.2f}%")
    
    async def analyze_btc(self):
        """تحليل سريع لـ BTC"""
        data = await self.http.get(
            "https://api.mexc.com/api/v3/ticker/24hr",
            {"symbol": "BTCUSDT"},
            cache_ttl=60
        )
        
        if data:
            try:
                last = float(data.get("lastPrice", 0))
                open_p = float(data.get("openPrice", last))
                self.btc_change_24h = (last - open_p) / open_p * 100
                
                if self.btc_change_24h <= -3:
                    self.market_state = "DANGER"
                elif self.btc_change_24h <= -1.5:
                    self.market_state = "CAUTION"
                else:
                    self.market_state = "SAFE"
            except:
                pass
    
    async def main_loop(self):
        log.info("🚀 Mafio Bot v2.0 — Optimized")
        
        # أول تشغيل
        await self.analyze_btc()
        
        await self.send_telegram(
            f"🚀 *Bot Started*\n"
            f"📊 عملات: `{MAX_SYMBOLS}` | فاصل: `{CHECK_INTERVAL}s`\n"
            f"₿ BTC: `{self.btc_change_24h:+.2f}%` | `{self.market_state}`"
        )
        
        last_btc_check = 0
        last_position_check = 0
        
        while True:
            try:
                now = time.time()
                
                # BTC كل 5 دقائق
                if now - last_btc_check >= 300:
                    await self.analyze_btc()
                    last_btc_check = now
                
                # المراكز كل دقيقة
                if now - last_position_check >= 60:
                    await self.check_positions()
                    last_position_check = now
                
                # جلب وتحليل العملات
                symbols = await self.fetch_symbols()
                if not symbols:
                    await asyncio.sleep(10)
                    continue
                
                self.active_symbols = {s["symbol"] for s in symbols}
                
                # ⭐ تحليل متوازي سريع
                tasks = [self.analyze_symbol(s) for s in symbols]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # معالجة النتائج
                valid_results = [r for r in results if isinstance(r, dict)]
                
                if valid_results:
                    await self.process_signals(valid_results)
                
                log.info(f"✅ Cycle complete | {len(valid_results)} signals | API: {self.http.api_calls}/min")
                
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                log.error(f"Main error: {e}")
                await asyncio.sleep(10)
    
    def run(self):
        try:
            asyncio.run(self.main_loop())
        except KeyboardInterrupt:
            log.info("⛔ Stopped")

# ==================== التشغيل ====================

if __name__ == "__main__":
    bot = MafioBot()
    bot.run()
