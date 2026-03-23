# -*- coding: utf-8 -*-
# Build: 20260323-V22-LIQUIDITY_MASTER
"""
╔══════════════════════════════════════════════════════════════╗
║     MAFIO BOT V22 — LIQUIDITY HUNTER IN BEAR MARKET        ║
║     رصد السيولة حتى في السوق الهابط                       ║
║     تتبع أين تذهب الأموال رغم نزول السوق                   ║
╚══════════════════════════════════════════════════════════════╝
"""

# ==================== نظام رصد السيولة في السوق الهابط ====================

class BearMarketLiquidityHunter:
    """
    نظام متخصص لرصد السيولة في السوق الهابط
    يكتشف أين تذهب الأموال رغم نزول السوق
    """
    
    def __init__(self):
        self.sector_liquidity = {}      # {sector: {"vol": [], "vdelta": [], "coins": []}}
        self.coin_liquidity = {}        # {coin: {"vol_ratio": [], "vdelta": [], "timestamp": []}}
        self.bear_signals = []          # إشارات السيولة في السوق الهابط
        self.bear_mode_start = 0        # وقت بدء السوق الهابط
        self.last_bear_scan = 0
        
    def is_bear_market(self) -> bool:
        """تحديد إذا كان السوق هابطاً"""
        # 1. BTC ينزل أكثر من 2%
        if btc_change_24h <= -2.0:
            return True
        
        # 2. أكثر من 60% من العملات نازلة
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
        
        # 3. VDelta السوق أقل من 45%
        if all_tickers:
            buy_vol = 0
            sell_vol = 0
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
            if total > 0 and buy_vol / total < 0.45:
                return True
        
        return False
    
    def detect_liquidity_direction(self, vol_now: Dict, change_now: Dict, price_map: Dict):
        """
        اكتشاف اتجاه السيولة في السوق الهابط
        يحلل أي القطاعات تستقبل السيولة رغم النزول
        """
        if not self.is_bear_market():
            return []
        
        now = time.time()
        if now - self.last_bear_scan < 300:  # كل 5 دقائق
            return []
        self.last_bear_scan = now
        
        # تحليل كل قطاع
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
                price = price_map.get(sym, 0)
                
                if vol < 50_000:
                    continue
                
                sector_data["total_vol"] += vol
                changes.append(chg)
                
                # حساب VDelta للعملة
                stats = analyze_tps_ats(sym)
                if stats:
                    vd = stats.get("vdelta", 0.5)
                    vdeltas.append(vd)
                    
                    # عملات ترتفع رغم نزول السوق = قوية
                    if chg > 0 and vol > 100_000:
                        sector_data["rising_coins"].append({
                            "sym": sym,
                            "chg": chg,
                            "vol": vol,
                            "vdelta": vd,
                            "price": price
                        })
                    
                    # عملات فيها تجميع خفي (حجم مرتفع + سعر ثابت)
                    vol_ratio = get_coin_vol_ratio(sym, vol)
                    if abs(chg) < 2.0 and vol_ratio >= 1.5 and vd >= 0.60:
                        sector_data["accum_coins"].append({
                            "sym": sym,
                            "vol_ratio": vol_ratio,
                            "vdelta": vd,
                            "price": price
                        })
            
            if not changes:
                continue
            
            sector_data["avg_change"] = sum(changes) / len(changes)
            if vdeltas:
                sector_data["avg_vdelta"] = sum(vdeltas) / len(vdeltas)
            
            # حساب نقاط السيولة في السوق الهابط
            # 1. متوسط VDelta مرتفع
            if sector_data["avg_vdelta"] >= 0.65:
                sector_data["liquidity_score"] += 30
            elif sector_data["avg_vdelta"] >= 0.60:
                sector_data["liquidity_score"] += 20
            
            # 2. وجود عملات ترتفع رغم نزول السوق
            rising_count = len(sector_data["rising_coins"])
            sector_data["liquidity_score"] += rising_count * 8
            
            # 3. وجود عملات في تجميع خفي
            accum_count = len(sector_data["accum_coins"])
            sector_data["liquidity_score"] += accum_count * 12
            
            # 4. القطاع لم ينزل بشدة
            if sector_data["avg_change"] > -5.0:
                sector_data["liquidity_score"] += 15
            
            sector_analysis.append(sector_data)
        
        # ترتيب حسب نقاط السيولة
        sector_analysis.sort(key=lambda x: -x["liquidity_score"])
        
        return sector_analysis[:5]  # أفضل 5 قطاعات
    
    def scan_bear_liquidity_signals(self, vol_now: Dict, change_now: Dict, price_map: Dict):
        """
        مسح إشارات السيولة في السوق الهابط
        يرسل تنبيهات للقطاعات التي تستقبل السيولة
        """
        now = time.time()
        
        if not self.is_bear_market():
            return
        
        sectors = self.detect_liquidity_direction(vol_now, change_now, price_map)
        
        if not sectors:
            return
        
        for sector in sectors:
            if sector["liquidity_score"] < 30:
                continue
            
            # تجنب التكرار
            last_alert = self.sector_liquidity.get(sector["sector"], {}).get("last_alert", 0)
            if now - last_alert < 3600:  # مرة كل ساعة
                continue
            
            # حفظ آخر تنبيه
            if sector["sector"] not in self.sector_liquidity:
                self.sector_liquidity[sector["sector"]] = {}
            self.sector_liquidity[sector["sector"]]["last_alert"] = now
            
            # بناء الرسالة
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
  2️⃣ انتظر إشارة ENTRY من نظام WATCH→ENTRY
  3️⃣ السوق نازل → استخدم Stop Loss أضيق (-3% فقط)
━━━━━━━━━━━━━━━━━━
⚠️ _السيولة موجودة — لكن السوق نازل، ادخل بحذر!_ 🎯
"""
            send(msg)
            log.info(f"🐻 BEAR LIQUIDITY | {sector['sector']} | score={sector['liquidity_score']} | "
                    f"rising={len(sector['rising_coins'])} | accum={len(sector['accum_coins'])}")
    
    def get_bear_opportunities(self, sector: str, price_map: Dict, vol_now: Dict, change_now: Dict) -> List[Dict]:
        """
        الحصول على أفضل فرص الدخول في قطاع معين خلال السوق الهابط
        """
        opportunities = []
        coins = SECTORS.get(sector, [])
        
        for sym in coins:
            vol = vol_now.get(sym, 0)
            chg = change_now.get(sym, 0)
            price = price_map.get(sym, 0)
            
            if vol < 100_000:
                continue
            
            # شرط أساسي: العملة ترتفع أو ثابتة رغم نزول السوق
            if chg < -2.0:
                continue
            
            # حساب VDelta
            stats = analyze_tps_ats(sym)
            if not stats:
                continue
            
            vdelta = stats.get("vdelta", 0)
            ats = stats.get("ats", 0)
            tps = stats.get("tps", 0)
            
            # نسبة الحجم
            vol_ratio = get_coin_vol_ratio(sym, vol)
            
            # حساب نقاط القوة في السوق الهابط
            score = 0
            
            # حجم مرتفع
            if vol_ratio >= 2.0:
                score += 25
            elif vol_ratio >= 1.5:
                score += 15
            
            # VDelta قوي
            if vdelta >= 0.70:
                score += 35
            elif vdelta >= 0.65:
                score += 25
            
            # ATS (حيتان)
            if ats >= 2000:
                score += 25
            elif ats >= 500:
                score += 15
            
            # العملة خضراء رغم النزول
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
    
    def send_bear_entry_signals(self, price_map: Dict, vol_now: Dict, change_now: Dict):
        """
        إرسال إشارات دخول في السوق الهابط
        """
        if not self.is_bear_market():
            return
        
        # جلب أفضل قطاع سيولة
        sectors = self.detect_liquidity_direction(vol_now, change_now, price_map)
        if not sectors:
            return
        
        best_sector = sectors[0]
        if best_sector["liquidity_score"] < 40:
            return
        
        # جلب فرص الدخول في هذا القطاع
        opportunities = self.get_bear_opportunities(best_sector["sector"], price_map, vol_now, change_now)
        
        if not opportunities:
            return
        
        now = time.time()
        
        for opp in opportunities[:3]:
            sym = opp["sym"]
            base = sym.replace("USDT", "")
            
            # تجنب التكرار
            coin_data = self.coin_liquidity.get(sym, {})
            if now - coin_data.get("last_entry", 0) < 7200:
                continue
            
            if sym not in self.coin_liquidity:
                self.coin_liquidity[sym] = {}
            self.coin_liquidity[sym]["last_entry"] = now
            
            # Stop Loss أضيق في السوق الهابط
            stop_loss = opp["price"] * 0.97  # -3% فقط
            target1 = opp["price"] * 1.05   # +5%
            target2 = opp["price"] * 1.10   # +10%
            
            # إشارة دخول خاصة بالسوق الهابط
            msg = f"""
🎯 *BEAR MARKET ENTRY* — سيولة في السوق الهابط 🎯
━━━━━━━━━━━━━━━━━━
💥 *{base}* — قوة رغم نزول السوق!
📉 BTC: `{btc_change_24h:+.1f}%` (السوق نازل)
📈 {base}: `{opp['chg']:+.1f}%` (مقاوم للنزول!)
━━━━━━━━━━━━━━━━━━
📊 VDelta: `{opp['vdelta']*100:.0f}%` 🔥
📈 الحجم: `{opp['vol_ratio']:.1f}×` المعدل
📡 TPS: `{opp['tps']:.2f}` | ATS: `{opp['ats']:.0f}$`
━━━━━━━━━━━━━━━━━━
🛡️ *Stop Loss:* `{fmt_price(stop_loss)}` (-3% فقط)
🎯 *الأهداف:*
  1️⃣ `{fmt_price(target1)}` (+5%)
  2️⃣ `{fmt_price(target2)}` (+10%)
━━━━━━━━━━━━━━━━━━
💪 قوة الإشارة: `{opp['score']}/100`
🏷️ القطاع: *{best_sector['sector']}*
━━━━━━━━━━━━━━━━━━
⚠️ *السوق نازل لكن السيولة هنا!* 
⚡ ادخل بحجم صغير وStop Loss أضيق 🎯
"""
            send(msg)
            log.info(f"🎯 BEAR ENTRY | {sym} | score={opp['score']} | chg={opp['chg']:.1f}%")
            
            # إضافة لمراقبة الخروج
            add_to_exit_watchlist(sym, opp["price"])

# ==================== دمج النظام في الحلقة الرئيسية ====================

# إنشاء نسخة من BearMarketLiquidityHunter
bear_hunter = BearMarketLiquidityHunter()

# ==================== تحديث دالة run() ====================

def run():
    """الحلقة الرئيسية للبوت - مع دعم رصد السيولة في السوق الهابط"""
    global all_tickers, last_tickers, last_btc, last_sectors
    global last_deep_scan, last_stale, last_expand
    global last_daily_report, daily_report_sent_date
    global last_ts_scan, last_wl_check, last_rt_scan
    global last_tps_scan, last_lh_scan, last_sc_refresh
    global last_ath_scan, last_bottom_scan, last_sector_report
    global last_whale_check, last_sr_alert
    
    log.info("🚀 MAFIO-BOT V22 - LIQUIDITY MASTER يبدأ...")
    log.info("🎯 خاصية جديدة: رصد السيولة حتى في السوق الهابط!")
    
    # ... (باقي الكود كما هو) ...
    
    # ==================== إضافة فحص السيولة في السوق الهابط ====================
    
    # في الحلقة الرئيسية while True، أضف:
    
    # فحص السيولة في السوق الهابط (كل 5 دقائق)
    if now - last_bear_scan >= 300:  # 5 دقائق
        # تحديث حالة السوق
        bear_hunter.is_bear = bear_hunter.is_bear_market()
        
        if bear_hunter.is_bear:
            # مسح إشارات السيولة
            bear_hunter.scan_bear_liquidity_signals(vol_now, change_now, price_map)
            # إرسال إشارات دخول
            bear_hunter.send_bear_entry_signals(price_map, vol_now, change_now)
            
            # تسجيل القطاع الأكثر سيولة
            sectors = bear_hunter.detect_liquidity_direction(vol_now, change_now, price_map)
            if sectors:
                best = sectors[0]
                log.info(f"🐻 BEAR MODE | أفضل قطاع: {best['sector']} | "
                        f"نقاط: {best['liquidity_score']} | عملات صاعدة: {len(best['rising_coins'])}")
        
        last_bear_scan = now

# ==================== إضافة أوامر Telegram جديدة ====================

def poll_commands():
    """إضافة أوامر جديدة لمراقبة السيولة في السوق الهابط"""
    # ... (الكود الموجود) ...
    
    # إضافة أوامر جديدة
    elif text_lower in ("/bear", "/سوق_هابط"):
        if bear_hunter.is_bear_market():
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
            send("🟢 السوق ليس هابطاً حالياً - استخدم /sectors لرؤية القطاعات الساخنة")
    
    elif text_lower in ("/bearcoins", "/عملات_هابط"):
        if bear_hunter.is_bear_market():
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
                        msg += f"  • *{base}* `{opp['chg']:+.1f}%` | "
                        msg += f"VD:{opp['vdelta']*100:.0f}% | قوة:{opp['score']}\n"
                    send(msg)
                else:
                    send("🐻 لا توجد فرص دخول واضحة حالياً")
        else:
            send("🟢 السوق صاعد - استخدم /watchlist لرؤية الفرص")

# ==================== متغيرات إضافية ====================
last_bear_scan = 0.0
