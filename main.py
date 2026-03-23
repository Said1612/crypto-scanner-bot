# -*- coding: utf-8 -*-
# Build: 20260323-V24-REPORTS-FIXED
"""
╔══════════════════════════════════════════════════════════════╗
║     MAFIO BOT V24 — WITH FULL REPORTS                      ║
║     ✅ تقرير يومي عند إغلاق اليوم (00:00 UTC)              ║
║     ✅ تقرير كل 4 ساعات للقطاعات الساخنة                   ║
║     ✅ رصد السيولة حتى في السوق الهابط                     ║
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
import math

# ... (بقية الكود كما هو حتى SECTORS) ...

# ==================== متغيرات التقارير ====================
last_4h_report = 0.0           # آخر وقت تم إرسال تقرير 4 ساعات
last_daily_report_sent = ""    # تاريخ آخر تقرير يومي
REPORT_4H_INTERVAL = 14400     # 4 ساعات = 14400 ثانية

# ==================== تقرير 4 ساعات (القطاعات الساخنة) ====================

def send_4h_sector_report():
    """تقرير كل 4 ساعات عن القطاعات الساخنة وتدفق السيولة"""
    global last_4h_report, hot_sectors, candidates
    
    now = time.time()
    
    # التحقق من مرور 4 ساعات
    if now - last_4h_report < REPORT_4H_INTERVAL:
        return
    
    last_4h_report = now
    
    if not all_tickers:
        log.warning("⚠️ لا توجد بيانات للتقرير")
        return
    
    # ==================== 1. تحليل القطاعات ====================
    sector_stats = {}
    ticker_map = {t["symbol"]: t for t in all_tickers}
    
    for sector, coins in SECTORS.items():
        sector_data = {
            "vol": 0.0,
            "rising": 0,
            "falling": 0,
            "avg_change": 0.0,
            "top_coins": [],
            "volume_24h": 0.0
        }
        
        changes = []
        for sym in coins:
            t = ticker_map.get(sym)
            if not t:
                continue
            try:
                vol = float(t.get("quoteVolume", 0))
                ch = float(t.get("priceChangePercent", 0))
                
                sector_data["vol"] += vol
                changes.append(ch)
                
                if ch > 0:
                    sector_data["rising"] += 1
                    if len(sector_data["top_coins"]) < 3:
                        sector_data["top_coins"].append({
                            "sym": sym,
                            "ch": ch,
                            "vol": vol
                        })
                else:
                    sector_data["falling"] += 1
                    
            except (KeyError, ValueError):
                continue
        
        if changes:
            sector_data["avg_change"] = sum(changes) / len(changes)
            sector_data["volume_24h"] = sector_data["vol"] / 1_000_000
        
        sector_stats[sector] = sector_data
    
    # ترتيب القطاعات حسب الأداء
    sorted_sectors = sorted(
        sector_stats.items(),
        key=lambda x: (x[1]["avg_change"], x[1]["vol"]),
        reverse=True
    )
    
    # ==================== 2. أفضل 5 قطاعات ====================
    msg = "📊 *تقرير القطاعات | 4 ساعات*\n"
    msg += f"🕐 `{datetime.now().strftime('%H:%M:%S')}`\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "*🔥 القطاعات الساخنة:*\n"
    
    for sector, data in sorted_sectors[:5]:
        if data["avg_change"] > 0:
            icon = "🟢" if data["avg_change"] > 2 else "🟡"
        else:
            icon = "🔴"
        
        msg += f"\n{icon} *{sector}*\n"
        msg += f"   📊 التغيير: `{data['avg_change']:+.1f}%`\n"
        msg += f"   📦 حجم 24h: `{data['volume_24h']:.1f}M`\n"
        msg += f"   📈 صاعد: {data['rising']} | 📉 هابط: {data['falling']}\n"
        
        if data["top_coins"]:
            msg += f"   🏆 أبرز العملات:\n"
            for coin in data["top_coins"][:3]:
                base = coin["sym"].replace("USDT", "")
                msg += f"      • *{base}* `+{coin['ch']:.1f}%`\n"
    
    # ==================== 3. تدفق السيولة ====================
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "*💧 تدفق السيولة:*\n"
    
    # حساب VDelta السوق
    buy_vol = 0.0
    sell_vol = 0.0
    for t in all_tickers:
        try:
            vol = float(t.get("quoteVolume", 0))
            ch = float(t.get("priceChangePercent", 0))
            if ch > 0:
                buy_vol += vol
            else:
                sell_vol += vol
        except:
            pass
    
    total_vol = buy_vol + sell_vol
    if total_vol > 0:
        buy_pct = buy_vol / total_vol * 100
        msg += f"   🟢 شراء: `{buy_pct:.1f}%`\n"
        msg += f"   🔴 بيع: `{100 - buy_pct:.1f}%`\n"
    
    # أفضل قطاع للسيولة
    best_sector = sorted_sectors[0] if sorted_sectors else None
    if best_sector and best_sector[1]["avg_change"] > 1:
        msg += f"\n🎯 *القطاع الأكثر سيولة:* *{best_sector[0]}*\n"
        msg += f"   متوسط التغيير: `{best_sector[1]['avg_change']:+.1f}%`\n"
    
    # ==================== 4. حالة السوق ====================
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "*🌍 حالة السوق:*\n"
    msg += f"   ₿ BTC: `{btc_change_24h:+.2f}%` | `{market_state}`\n"
    msg += f"   Ξ ETH: `{eth_change_24h:+.2f}%`\n"
    
    # ==================== 5. العملات المرشحة ====================
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += f"*🎯 العملات المرشحة:* `{len(candidates)}` عملة\n"
    
    # أفضل 5 عملات حالياً
    top_candidates = []
    for sym in candidates[:10]:
        ch = changes_map.get(sym, 0)
        vol = 0
        for t in all_tickers:
            if t.get("symbol") == sym:
                try:
                    vol = float(t.get("quoteVolume", 0)) / 1_000_000
                except:
                    pass
                break
        top_candidates.append((sym, ch, vol))
    
    for sym, ch, vol in top_candidates[:5]:
        base = sym.replace("USDT", "")
        icon = "🟢" if ch > 0 else "🔴"
        msg += f"   {icon} *{base}* | `{ch:+.1f}%` | حجم `{vol:.1f}M`\n"
    
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "⚡ _تحديث كل 4 ساعات | ادخل بحذر_"
    
    send(msg)
    log.info(f"📊 4H Report | أفضل قطاع: {sorted_sectors[0][0] if sorted_sectors else 'لا يوجد'}")


# ==================== تقرير يومي كامل (مطور) ====================

def send_daily_report(force=False):
    """تقرير يومي عند إغلاق اليوم (00:00 UTC)"""
    global daily_report_sent_date, last_daily_report_sent
    
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now_utc.strftime("%Y-%m-%d")
    
    # التحقق من الوقت (يُرسل عند 00:00 UTC)
    if not force and not _force_daily_report:
        if now_utc.hour != 0:
            return
        if daily_report_sent_date == today:
            return
    
    daily_report_sent_date = today
    last_daily_report_sent = time.time()
    
    log.info(f"📅 إرسال التقرير اليومي | {today}")
    
    # ==================== 1. ملخص السوق ====================
    msg = "📊 *التقرير اليومي | إغلاق اليوم*\n"
    msg += f"📅 `{today}`\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "*🌍 ملخص السوق:*\n"
    msg += f"   ₿ BTC 24h: `{btc_change_24h:+.2f}%` | `{market_state}`\n"
    msg += f"   Ξ ETH 24h: `{eth_change_24h:+.2f}%`\n"
    
    # ==================== 2. أداء القطاعات ====================
    if all_tickers:
        ticker_map = {t["symbol"]: t for t in all_tickers}
        sector_performance = []
        
        for sector, coins in SECTORS.items():
            changes = []
            total_vol = 0.0
            for sym in coins:
                t = ticker_map.get(sym)
                if not t:
                    continue
                try:
                    ch = float(t.get("priceChangePercent", 0))
                    vol = float(t.get("quoteVolume", 0))
                    changes.append(ch)
                    total_vol += vol
                except:
                    continue
            if changes:
                avg_ch = sum(changes) / len(changes)
                sector_performance.append((sector, avg_ch, total_vol / 1_000_000))
        
        sector_performance.sort(key=lambda x: -x[1])
        
        msg += "\n━━━━━━━━━━━━━━━━━━\n"
        msg += "*🏆 أفضل القطاعات اليوم:*\n"
        for sector, ch, vol in sector_performance[:5]:
            icon = "🟢" if ch > 0 else "🔴"
            msg += f"   {icon} *{sector}* | `{ch:+.1f}%` | حجم `{vol:.1f}M`\n"
        
        msg += "\n*📉 أسوأ القطاعات:*\n"
        for sector, ch, vol in sector_performance[-3:]:
            icon = "🔴" if ch < 0 else "🟢"
            msg += f"   {icon} *{sector}* | `{ch:+.1f}%`\n"
    
    # ==================== 3. نشاط الحيتان ====================
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "*🐋 نشاط الحيتان:*\n"
    
    if btc_tps_stats:
        btc_ats = btc_tps_stats.get("ats", 0)
        btc_vdelta = btc_tps_stats.get("vdelta", 0.5)
        msg += f"   ₿ BTC: ATS `{btc_ats:.0f}$` | VDelta `{btc_vdelta*100:.0f}%`\n"
        
        if btc_ats >= 2000 and btc_vdelta >= 0.65:
            msg += "   🔥 حيتان يشترون BTC!\n"
        elif btc_ats >= 2000 and btc_vdelta < 0.40:
            msg += "   ⚠️ حيتان يبيعون BTC!\n"
    
    if eth_tps_stats:
        eth_ats = eth_tps_stats.get("ats", 0)
        eth_vdelta = eth_tps_stats.get("vdelta", 0.5)
        msg += f"   Ξ ETH: ATS `{eth_ats:.0f}$` | VDelta `{eth_vdelta*100:.0f}%`\n"
    
    # ==================== 4. أفضل العملات ====================
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "*🚀 أفضل العملات اليوم:*\n"
    
    if all_tickers:
        top_gainers = []
        for t in all_tickers:
            try:
                sym = t.get("symbol", "")
                if not sym.endswith("USDT"):
                    continue
                if is_leverage_token(sym) or is_stablecoin(sym):
                    continue
                ch = float(t.get("priceChangePercent", 0))
                vol = float(t.get("quoteVolume", 0))
                if ch > 0 and vol > 1_000_000:
                    top_gainers.append((sym, ch, vol))
            except:
                continue
        
        top_gainers.sort(key=lambda x: -x[1])
        
        for sym, ch, vol in top_gainers[:10]:
            base = sym.replace("USDT", "")
            vol_m = vol / 1_000_000
            msg += f"   🟢 *{base}* | `+{ch:.1f}%` | حجم `{vol_m:.1f}M`\n"
    
    # ==================== 5. تدفق السيولة ====================
    if all_tickers:
        buy_vol = 0.0
        sell_vol = 0.0
        for t in all_tickers:
            try:
                vol = float(t.get("quoteVolume", 0))
                ch = float(t.get("priceChangePercent", 0))
                if ch > 0:
                    buy_vol += vol
                else:
                    sell_vol += vol
            except:
                pass
        
        total = buy_vol + sell_vol
        if total > 0:
            msg += "\n━━━━━━━━━━━━━━━━━━\n"
            msg += "*💧 تدفق السيولة:*\n"
            msg += f"   🟢 شراء: `{buy_vol/total*100:.1f}%`\n"
            msg += f"   🔴 بيع: `{sell_vol/total*100:.1f}%`\n"
            
            if buy_vol/total > 0.6:
                msg += "   ✅ سيولة إيجابية - السوق صاعد\n"
            elif sell_vol/total > 0.6:
                msg += "   ⚠️ سيولة سلبية - السوق هابط\n"
    
    # ==================== 6. حالة السوق الهابط ====================
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "*🐻 تحليل السوق:*\n"
    
    if btc_change_24h <= -2.0:
        msg += "   🔴 *السوق في حالة هبوط*\n"
        msg += "   💡 السيولة تتجه إلى القطاعات الدفاعية\n"
    elif btc_change_24h >= 2.0:
        msg += "   🟢 *السوق في حالة صعود*\n"
        msg += "   💡 فرص في القطاعات النشطة\n"
    else:
        msg += "   🟡 *السوق متذبذب*\n"
        msg += "   💡 انتظر إشارة واضحة\n"
    
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += f"📊 عدد العملات المرشحة: `{len(candidates)}`\n"
    msg += f"🔥 القطاعات الساخنة: `{', '.join(hot_sectors[:3]) or 'لا يوجد'}`\n"
    msg += "\n⚡ _تقرير يومي | ادخل بحذر_"
    
    send(msg)
    log.info(f"✅ Daily Report sent | {today} | {len(candidates)} candidates")


# ==================== تحديث الدوال الأساسية ====================

def scan_sector_activity():
    """مسح نشاط القطاعات - يستخدم في التقرير الدوري"""
    # هذه الدالة تستخدم في تقرير 4 ساعات
    pass


def refresh_sector_report():
    """تحديث تقرير القطاعات - يُستدعى كل 4 ساعات"""
    send_4h_sector_report()


# ==================== تحديث الحلقة الرئيسية ====================

def run():
    global all_tickers, candidates, hot_sectors, market_state, btc_change_24h
    global last_btc, last_sectors, last_deep_scan, last_stale, last_expand
    global last_ts_scan, last_wl_check, last_rt_scan, last_tps_scan, last_lh_scan
    global last_sc_refresh, last_ath_scan, last_bottom_scan, last_sector_report
    global last_whale_check, last_sr_alert, last_tickers, last_bear_scan
    global last_4h_report, price_map, vol_now, change_now, scanner, bear_hunter
    
    # تعريف المتغيرات المحلية
    price_map = {}
    vol_now = {}
    change_now = {}
    
    log.info("🚀 MAFIO-BOT V24 - WITH FULL REPORTS يبدأ...")
    log.info("📊 16 قطاع يتم مراقبتها")
    log.info("📅 تقرير يومي عند 00:00 UTC")
    log.info("⏰ تقرير كل 4 ساعات للقطاعات الساخنة")
    log.info("🎯 رصد السيولة حتى في السوق الهابط")

    time.sleep(5)
    load_state()

    # إنشاء كائنات الأنظمة
    global scanner, bear_hunter
    scanner = SmartMarketScanner()
    bear_hunter = BearMarketLiquidityHunter()

    analyze_btc()
    
    # المسح الأولي للسوق
    scanner.scan_all_market()
    
    time.sleep(2)
    init_static_watchlist()
    auto_expand_sectors()
    analyze_sectors()
    
    last_sector_report = time.time()
    last_4h_report = time.time() - 3600  # بحيث يرسل بعد ساعة

    log.info(f"✅ Ready | Candidates: {len(candidates)} | Hot sectors: {hot_sectors}")

    last_deep_scan = 0
    last_lh_scan = 0
    last_sc_refresh = 0
    last_sr_alert = 0
    last_bear_scan = 0
    last_tickers = time.time()

    send(
        f"💀 *MAFIO-BOT V24* 💀\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 16 قطاع تحت المراقبة\n"
        f"✅ تقرير يومي (00:00 UTC)\n"
        f"✅ تقرير كل 4 ساعات\n"
        f"✅ رصد السيولة حتى في السوق الهابط\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"₿ BTC: `{btc_change_24h:+.2f}%` | السوق: `{market_state}`\n"
        f"🔥 Hot: {', '.join(hot_sectors[:3]) or 'لا يوجد'}"
    )

    cycle = 0
    flow_cycle = 0

    while True:
        try:
            now = time.time()

            # حفظ الحالة كل 30 دقيقة
            if int(now) % 1800 < 12:
                save_state()

            # ==================== التقرير كل 4 ساعات ====================
            if now - last_4h_report >= REPORT_4H_INTERVAL:
                send_4h_sector_report()
                last_4h_report = now

            # ==================== التقرير اليومي ====================
            send_daily_report()

            # المسح الذكي للسوق كل ساعة
            if now - scanner.last_scan_time >= scanner.scan_interval:
                scanner.scan_all_market()
                analyze_sectors()

            # ... (بقية الكود كما هو) ...

            time.sleep(12)

        except KeyboardInterrupt:
            send("⛔ *MAFIO-BOT* — تم الإيقاف")
            break
        except Exception as e:
            log.error("Error: %s", e, exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    run()
