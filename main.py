#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     MAFIO BOT — LIQUIDITY HUNTER PRO                        ║
║                     🎯 اصطياد الانفجارات قبل حدوثها                          ║
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
from typing import Dict, List, Optional, Any
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

# ==================== إعدادات ====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
GROUP_ID = os.getenv("GROUP_ID", "")

CHECK_INTERVAL = 30
MAX_SYMBOLS = 30
MIN_VOLUME_USD = 500_000

TIER_SETTINGS = {
    "big": {"vdelta_min": 0.55, "vol_min": 5_000_000, "label": "Big Cap 🏦"},
    "mid": {"vdelta_min": 0.52, "vol_min": 500_000, "label": "Mid Cap 📊"},
    "small": {"vdelta_min": 0.50, "vol_min": 100_000, "label": "Small Cap 🚀"},
}

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

# ==================== HTTP Client ====================

class HTTPClient:
    def __init__(self):
        self.ssl = ssl.create_default_context()
        self.ssl.check_hostname = False
        self.ssl.verify_mode = ssl.CERT_NONE
        self.calls = 0
        self.last_reset = time.time()
        self._cache = {}
        self._cache_time = {}
    
    async def get(self, url: str, params: dict = None, cache_ttl: int = 0) -> Optional[Any]:
        cache_key = f"{url}:{str(params)}"
        now = time.time()
        
        if cache_ttl > 0 and cache_key in self._cache:
            if now - self._cache_time.get(cache_key, 0) < cache_ttl:
                return self._cache[cache_key]
        
        if params:
            query = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{url}?{query}"
        
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, 
                lambda: urllib.request.urlopen(url, context=self.ssl, timeout=15)
            )
            data = json.loads(resp.read().decode('utf-8'))
            
            if cache_ttl > 0:
                self._cache[cache_key] = data
                self._cache_time[cache_key] = now
            
            self.calls += 1
            if now - self.last_reset >= 60:
                log.info(f"📡 API: {self.calls}/min")
                self.calls = 0
                self.last_reset = now
            
            return data
        except Exception as e:
            log.debug(f"GET error: {e}")
            return None
    
    async def post_json(self, url: str, data: dict) -> bool:
        """إرسال POST - منفصلة وواضحة"""
        try:
            json_data = json.dumps(data).encode('utf-8')
            headers = {'Content-Type': 'application/json'}
            req = urllib.request.Request(url, data=json_data, headers=headers, method='POST')
            
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, context=self.ssl, timeout=10)
            )
            return resp.getcode() == 200
        except Exception as e:
            log.debug(f"POST error: {e}")
            return False

# ==================== هياكل البيانات ====================

class SignalType(Enum):
    WATCH = "👁️"
    ENTRY = "🎯"
    GOLDEN = "🏆"

@dataclass
class MarketData:
    symbol: str
    price: float = 0.0
    vdelta: float = 0.5
    tps: float = 0.0
    ats: float = 0.0
    volume_spike: float = 1.0
    last_update: float = 0.0
    volume_history: deque = field(default_factory=lambda: deque(maxlen=10))

@dataclass
class WatchItem:
    symbol: str
    entry_time: float
    initial_price: float
    initial_ats: float

# ==================== البوت ====================

class MafioBot:
    def __init__(self):
        self.http = HTTPClient()
        self.cache: Dict[str, MarketData] = {}
        self.watchlist: Dict[str, WatchItem] = {}
        self.btc_change = 0.0
        self.market_state = "SAFE"
        self.symbols: set = set()
        self.signals_count = 0
        
    def fmt_price(self, p: float) -> str:
        if p < 0.0001:
            return f"{p:.8f}"
        if p < 1:
            return f"{p:.6f}"
        if p < 1000:
            return f"{p:.4f}"
        return f"{p:,.2f}"
    
    async def send_telegram(self, msg: str):
        """إرسال رسالة - ثابتة الآن"""
        if not TELEGRAM_TOKEN or len(TELEGRAM_TOKEN) < 10:
            log.info(f"[TELEGRAM] {msg[:80]}...")
            return
        
        targets = [c for c in [CHAT_ID, GROUP_ID] if c]
        
        for chat_id in targets:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            success = await self.http.post_json(url, {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "Markdown"
            })
            if not success:
                log.error(f"Failed to send to {chat_id}")
            await asyncio.sleep(0.3)
    
    async def fetch_symbols(self) -> List[dict]:
        data = await self.http.get("https://api.mexc.com/api/v3/ticker/24hr", cache_ttl=30)
        if not data:
            return []
        
        filtered = []
        for item in data:
            sym = item.get("symbol", "")
            if not sym.endswith("USDT") or any(k in sym for k in LEVERAGE_KEYWORDS) or sym in EXCLUDED:
                continue
            
            try:
                vol = float(item.get("quoteVolume", 0))
                change = float(item.get("priceChangePercent", 0))
                
                if vol < MIN_VOLUME_USD or abs(change) > 30:
                    continue
                
                filtered.append({
                    "symbol": sym,
                    "price": float(item.get("lastPrice", 0)),
                    "volume": vol,
                    "change": change
                })
            except:
                continue
        
        filtered.sort(key=lambda x: -x["volume"])
        return filtered[:MAX_SYMBOLS]
    
    async def analyze_symbol(self, s: dict) -> Optional[dict]:
        symbol = s["symbol"]
        
        # تريدز
        trades = await self.http.get(
            "https://api.mexc.com/api/v3/trades",
            {"symbol": symbol, "limit": 50},
            cache_ttl=15
        )
        if not trades or len(trades) < 5:
            return None
        
        # حساب سريع
        buy_vol = total_vol = 0.0
        for t in trades:
            try:
                val = float(t["price"]) * float(t["qty"])
                total_vol += val
                if not t.get("m", False):
                    buy_vol += val
            except:
                continue
        
        if total_vol <= 0:
            return None
        
        vdelta = buy_vol / total_vol
        ats = total_vol / len(trades)
        
        # فلتر
        tier = "big" if s["volume"] >= 5_000_000 else "mid" if s["volume"] >= 500_000 else "small"
        if vdelta < TIER_SETTINGS[tier]["vdelta_min"]:
            return None
        
        # Order Book
        ob = await self.http.get(
            "https://api.mexc.com/api/v3/depth",
            {"symbol": symbol, "limit": 10},
            cache_ttl=10
        )
        
        ob_ratio = 1.0
        if ob:
            try:
                bids = sum(float(b[0]) * float(b[1]) for b in ob.get("bids", [])[:5])
                asks = sum(float(a[0]) * float(a[1]) for a in ob.get("asks", [])[:5])
                ob_ratio = bids / asks if asks > 0 else 1.0
            except:
                pass
        
        # كاش
        if symbol not in self.cache:
            self.cache[symbol] = MarketData(symbol=symbol)
        
        md = self.cache[symbol]
        md.price = s["price"]
        md.vdelta = round(vdelta, 3)
        md.ats = round(ats, 2)
        
        if md.volume_history:
            avg = sum(md.volume_history) / len(md.volume_history)
            md.volume_spike = round(s["volume"] / avg, 2) if avg > 0 else 1.0
        md.volume_history.append(s["volume"])
        md.last_update = time.time()
        
        # نقاط
        score = 0
        sigs = []
        
        if md.volume_spike >= 2.0:
            score += 25
            sigs.append(f"💥 {md.volume_spike}x")
        elif md.volume_spike >= 1.5:
            score += 15
            sigs.append(f"🔥 {md.volume_spike}x")
        
        if vdelta >= 0.75:
            score += 25
            sigs.append(f"💪 {vdelta*100:.0f}%")
        elif vdelta >= 0.60:
            score += 15
            sigs.append(f"✅ {vdelta*100:.0f}%")
        
        if ob_ratio >= 2.0:
            score += 15
            sigs.append(f"📊 {ob_ratio:.1f}:1")
        
        if score < 40:
            return None
        
        sector = next((sec for sec, coins in SECTORS.items() if symbol in coins), "أخرى")
        
        return {
            "symbol": symbol,
            "price": s["price"],
            "vdelta": vdelta,
            "ats": ats,
            "score": score,
            "sigs": sigs,
            "sector": sector,
            "tier": tier,
            "is_strong": score >= 55
        }
    
    async def send_signal(self, r: dict, is_entry: bool = False):
        """إرسال إشارة"""
        sym_clean = r["symbol"].replace("USDT", "")
        
        if is_entry:
            msg = (
                f"🎯 *ENTRY — {sym_clean}*\n"
                f"💵 `{self.fmt_price(r['price'])}` | قوة: `{r['score']}`\n"
                f"{' | '.join(r['sigs'][:3])}\n"
                f"🎯 +8% | +15% | +25%\n"
                f"🛡️ SL: -5%"
            )
        else:
            msg = (
                f"👁️ *WATCH — {sym_clean}*\n"
                f"💵 `{self.fmt_price(r['price'])}` | قوة: `{r['score']}`\n"
                f"{' | '.join(r['sigs'][:3])}\n"
                f"⏳ انتظر التأكيد..."
            )
        
        await self.send_telegram(msg)
        self.signals_count += 1
        log.info(f"{'🎯 ENTRY' if is_entry else '👁️ WATCH'} | {r['symbol']} | score={r['score']}")
    
    async def process(self, results: List[Optional[dict]]):
        """معالجة النتائج"""
        now = time.time()
        
        for r in results:
            if not r:
                continue
            
            sym = r["symbol"]
            
            # WATCH جديد
            if sym not in self.watchlist and not r["is_strong"]:
                self.watchlist[sym] = WatchItem(
                    symbol=sym,
                    entry_time=now,
                    initial_price=r["price"],
                    initial_ats=r["ats"]
                )
                await self.send_signal(r, False)
            
            # ENTRY (تأكيد)
            elif sym in self.watchlist and r["is_strong"]:
                watch = self.watchlist[sym]
                elapsed = (now - watch.entry_time) / 60
                
                if elapsed >= 2:
                    await self.send_signal(r, True)
                    del self.watchlist[sym]
    
    async def main(self):
        log.info("🚀 Bot started")
        
        await self.send_telegram("🚀 *Bot Started*")
        
        while True:
            try:
                # جلب
                symbols = await self.fetch_symbols()
                if not symbols:
                    await asyncio.sleep(10)
                    continue
                
                self.symbols = {s["symbol"] for s in symbols}
                
                # تحليل متوازي
                tasks = [self.analyze_symbol(s) for s in symbols]
                results = await asyncio.gather(*tasks)
                
                # معالجة
                valid = [r for r in results if r]
                if valid:
                    await self.process(valid)
                
                log.info(f"✅ Cycle: {len(valid)} signals | Total: {self.signals_count}")
                
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                log.error(f"Error: {e}")
                await asyncio.sleep(10)

# ==================== تشغيل ====================

if __name__ == "__main__":
    bot = MafioBot()
    asyncio.run(bot.main())
