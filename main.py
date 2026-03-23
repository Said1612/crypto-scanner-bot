#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAFIO BOT v3.0 - ATS Based Signals
WATCH (50$/100$) -> ENTRY (100$/200$+)
"""

import os
import sys
import json
import time
import asyncio
import logging
import urllib.request
import ssl
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# ==================== Settings ====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
GROUP_ID = os.getenv("GROUP_ID", "")

CHECK_INTERVAL = 30

# ATS thresholds by tier
TIER_CONFIG = {
    "small": {
        "max_vol": 1_000_000,
        "label": "Small",
        "watch_ats": 50,
        "entry_ats": 100,
        "vdelta_min": 0.50
    },
    "big": {
        "min_vol": 1_000_000,
        "label": "Big",
        "watch_ats": 100,
        "entry_ats": 200,
        "vdelta_min": 0.55
    }
}

SECTORS = {
    "Meme": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "WIFUSDT", "BONKUSDT"],
    "AI": ["FETUSDT", "AGIXUSDT", "WLDUSDT", "ARKMUSDT", "RENDERUSDT"],
    "Layer1": ["SOLUSDT", "AVAXUSDT", "ADAUSDT", "NEARUSDT", "SUIUSDT"],
    "DeFi": ["LINKUSDT", "AAVEUSDT", "UNIUSDT", "MKRUSDT"],
}

EXCLUDED = {"BTCUSDT", "ETHUSDT", "BNBUSDT"}
LEVERAGE_KEYWORDS = ["3L", "3S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN"]

# ==================== Logging ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
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
    
    async def get(self, url: str, params: dict = None) -> Optional[Any]:
        if params:
            url += "?" + "&".join([f"{k}={v}" for k, v in params.items()])
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, 
                lambda: urllib.request.urlopen(url, context=self.ssl, timeout=15)
            )
            self.calls += 1
            return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            log.debug(f"GET error: {e}")
            return None
    
    async def post(self, url: str, data: dict) -> bool:
        try:
            json_data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(
                url, 
                data=json_data, 
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, context=self.ssl, timeout=10)
            )
            return resp.getcode() == 200
        except:
            return False

# ==================== Data Structures ====================

@dataclass
class SymbolState:
    symbol: str
    price: float = 0.0
    volume: float = 0.0
    vdelta: float = 0.5
    tps: float = 0.0
    ats: float = 0.0
    watch_time: float = 0.0
    watch_ats: float = 0.0
    tier: str = "small"
    sector: str = "Other"

# ==================== Bot ====================

class MafioBot:
    def __init__(self):
        self.http = HTTPClient()
        self.states: Dict[str, SymbolState] = {}
        self.watchlist: Dict[str, float] = {}
        self.last_sent: Dict[str, float] = {}
    
    def get_tier(self, vol: float) -> str:
        return "big" if vol >= 1_000_000 else "small"
    
    def get_sector(self, symbol: str) -> str:
        for sector, coins in SECTORS.items():
            if symbol in coins:
                return sector
        return "Other"
    
    def fmt_price(self, p: float) -> str:
        if p < 0.0001:
            return f"{p:.8f}"
        if p < 1:
            return f"{p:.6f}"
        if p < 1000:
            return f"{p:.4f}"
        return f"{p:,.2f}"
    
    async def send_telegram(self, msg: str):
        if not TELEGRAM_TOKEN or len(TELEGRAM_TOKEN) < 10:
            log.info(f"[TELEGRAM] {msg[:60]}...")
            return
        
        targets = [c for c in [CHAT_ID, GROUP_ID] if c]
        for chat_id in targets:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            await self.http.post(url, {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "Markdown"
            })
            await asyncio.sleep(0.3)
    
    async def fetch_tickers(self) -> List[dict]:
        data = await self.http.get("https://api.mexc.com/api/v3/ticker/24hr")
        if not data:
            return []
        
        filtered = []
        for item in data:
            sym = item.get("symbol", "")
            if not sym.endswith("USDT"):
                continue
            if any(k in sym for k in LEVERAGE_KEYWORDS) or sym in EXCLUDED:
                continue
            
            try:
                vol = float(item.get("quoteVolume", 0))
                if vol < 100_000:
                    continue
                
                filtered.append({
                    "symbol": sym,
                    "price": float(item.get("lastPrice", 0)),
                    "volume": vol,
                    "change": float(item.get("priceChangePercent", 0))
                })
            except:
                continue
        
        filtered.sort(key=lambda x: -x["volume"])
        return filtered[:20]
    
    async def analyze_trades(self, symbol: str) -> Optional[dict]:
        trades = await self.http.get(
            "https://api.mexc.com/api/v3/trades",
            {"symbol": symbol, "limit": 100}
        )
        if not trades or len(trades) < 10:
            return None
        
        buy_vol = total_vol = 0.0
        now_ms = int(time.time() * 1000)
        recent = 0
        
        for t in trades:
            try:
                val = float(t["price"]) * float(t["qty"])
                total_vol += val
                if not t.get("m", False):
                    buy_vol += val
                if now_ms - int(t["time"]) <= 60000:
                    recent += 1
            except:
                continue
        
        if total_vol <= 0:
            return None
        
        return {
            "vdelta": buy_vol / total_vol,
            "ats": total_vol / len(trades),
            "tps": recent / 60.0
        }
    
    def can_send(self, symbol: str) -> bool:
        now = time.time()
        if symbol in self.last_sent:
            if now - self.last_sent[symbol] < 600:
                return False
        self.last_sent[symbol] = now
        return True
    
    async def send_watch(self, s: SymbolState):
        cfg = TIER_CONFIG[s.tier]
        
        msg = (
            f"[WATCH] {s.symbol.replace('USDT', '')} | {cfg['label']}\n"
            f"Price: {self.fmt_price(s.price)}\n"
            f"VDelta: {s.vdelta*100:.0f}% | TPS: {s.tps:.2f}\n"
            f"ATS: ${s.ats:.0f} (target: ${cfg['entry_ats']})\n"
            f"Wait 3-5 min for confirmation..."
        )
        
        await self.send_telegram(msg)
        log.info(f"WATCH | {s.symbol} | ATS=${s.ats:.0f}")
    
    async def send_entry(self, s: SymbolState):
        cfg = TIER_CONFIG[s.tier]
        
        ats_change = ((s.ats / s.watch_ats) - 1) * 100 if s.watch_ats > 0 else 0
        
        t1 = s.price * 1.10
        t2 = s.price * 1.20
        t3 = s.price * 1.35
        sl = s.price * 0.95
        
        msg = (
            f"[ENTRY] {s.symbol.replace('USDT', '')} | {cfg['label']}\n"
            f"Price: {self.fmt_price(s.price)}\n"
            f"VDelta: {s.vdelta*100:.0f}% | TPS: {s.tps:.2f}\n"
            f"ATS: ${s.ats:.0f} (+{ats_change:.0f}%) [Target: ${cfg['entry_ats']}+]\n"
            f"ENTER NOW!\n"
            f"SL: {self.fmt_price(sl)} (-5%)\n"
            f"T1: {self.fmt_price(t1)} (+10%)\n"
            f"T2: {self.fmt_price(t2)} (+20%)\n"
            f"T3: {self.fmt_price(t3)} (+35%)"
        )
        
        await self.send_telegram(msg)
        log.info(f"ENTRY | {s.symbol} | ATS=${s.ats:.0f} | +{ats_change:.0f}%")
    
    async def process_cycle(self):
        tickers = await self.fetch_tickers()
        now = time.time()
        
        for t in tickers:
            symbol = t["symbol"]
            stats = await self.analyze_trades(symbol)
            if not stats:
                continue
            
            vol = t["volume"]
            tier = self.get_tier(vol)
            cfg = TIER_CONFIG[tier]
            
            # Filter VDelta
            if stats["vdelta"] < cfg["vdelta_min"]:
                continue
            
            ats = stats["ats"]
            
            # WATCH logic
            if cfg["watch_ats"] <= ats < cfg["entry_ats"]:
                if symbol not in self.watchlist and self.can_send(symbol):
                    self.states[symbol] = SymbolState(
                        symbol=symbol,
                        price=t["price"],
                        volume=vol,
                        vdelta=stats["vdelta"],
                        tps=stats["tps"],
                        ats=ats,
                        watch_time=now,
                        watch_ats=ats,
                        tier=tier,
                        sector=self.get_sector(symbol)
                    )
                    self.watchlist[symbol] = now
                    await self.send_watch(self.states[symbol])
            
            # ENTRY logic
            elif ats >= cfg["entry_ats"] and symbol in self.watchlist:
                elapsed = (now - self.watchlist[symbol]) / 60
                
                if 2 <= elapsed <= 10:
                    s = self.states[symbol]
                    s.price = t["price"]
                    s.vdelta = stats["vdelta"]
                    s.tps = stats["tps"]
                    s.ats = ats
                    
                    await self.send_entry(s)
                    del self.watchlist[symbol]
    
    async def main(self):
        log.info("Mafio Bot v3.0 Started")
        await self.send_telegram("Bot Started")
        
        while True:
            try:
                await self.process_cycle()
                log.info(f"Cycle complete | API calls: {self.http.calls}")
                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                log.error(f"Error: {e}")
                await asyncio.sleep(10)

# ==================== Run ====================

if __name__ == "__main__":
    bot = MafioBot()
    asyncio.run(bot.main())
