# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MAFIO SNIPER** — بوت مسح السيولة للعملات الرقمية (v3.2 codebase / v15.3 signal display).
يراقب أسواق MEXC وBinance بحثاً عن إشارات دخول قوية بناءً على تحليل تدفق السيولة، ويرسل التنبيهات عبر Telegram.

يعمل على **VPS** (وليس Railway). يتم تحديث الكود على الـ VPS عبر:
```bash
wget -O /root/crypto-scanner-bot/main.py https://raw.githubusercontent.com/Said1612/crypto-scanner-bot/<branch>/main.py && systemctl restart crypto-scanner
```

## Running the Bot

```bash
python main.py
```

المتطلبات:
```bash
pip install -r requirements.txt
# requirements: requests, websocket-client
```

## Environment Variables (Required)

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | توكن بوت Telegram — **يجب ضبطه كمتغير بيئة، لا تضعه في الكود** |
| `CHAT_ID` | معرف المحادثة الخاصة |
| `GROUP_ID` | معرف المجموعة |
| `UPSTASH_REDIS_REST_URL` | رابط Redis لحفظ الحالة |
| `UPSTASH_REDIS_REST_TOKEN` | توكن Redis |
| `USE_BINANCE` | `true/false` — تفعيل Binance |
| `PROXY_URL` | بروكسي اختياري |

⚠️ لا تضع قيم افتراضية للتوكنات في الكود — استخدم متغيرات البيئة فقط.

## Architecture

كل الكود في ملف واحد: `main.py` (~2700+ سطر)

### دورة العمل الرئيسية

```
main() loop
├── كل 5 ثانية   → fast_scan()         → _check() بـ 5m klines
├── كل 60 ثانية  → scan_sleeping_giant() → عملات هادئة تنفجر فجأة
├── كل 5 دقائق  → slow_scan()          → _check() بـ 1h/60m klines
│                → scan_quiet_accum()   → تراكم هادئ بدون spike
│                → scan_trend_follow()  → متابعة الترند
│                → scan_sector_liquidity()
└── كل 15 دقيقة → scan_supertrend()    → SUPERTREND(10,3) flip
```

### تدفق `_check()` (الفلتر الرئيسي)

```
1. فلاتر سريعة: blacklist, pump_24h, cooldown, dedup_60s, tier, bias_gate
2. fetch_klines()       → vol_spike_and_move(), calc_flow()
3. fetch_funding_rate() → تعديل الحدود إذا كان bullish
4. fetch_agg_trades()   → ratio, net flow
5. _calc_score()        → نقاط 0-100 للإشارة
6. _ai_assess()         → تقييم AI (من signal_history.json)
7. fetch_ob_imbalance() → spot + futures order book
8. build_signal() + send() → Telegram مع keyboard
9. _db_add()            → حفظ في signal_history.json (ML training)
10. حفظ في alerted + tracking + Redis
```

### نظام الـ Tiers (v3.2)

| Tier | Volume | spike_min | ratio_min | net_min |
|------|--------|-----------|-----------|---------|
| Micro | < $2M | 3.5x | 3.0x | $5,000 |
| Small | $2-15M | 2.8x | 2.5x | $15,000 |
| Mid | $15-80M | 2.5x | 2.5x | $60,000 |
| Large | > $80M | 2.2x | 1.8x | $250,000 |

### الميزات الجديدة في v3.2 (مقارنة بـ v3.1)

- **AI Agent** (`ai_agent.py`): تقييم الإشارات بناءً على تاريخ التداول (`signal_history.json`)
- **Signal Database**: `signal_history.json` — سجل كامل لكل الإشارات (ML training data)
- **Score System**: `_calc_score()` يعطي نقاط 0-100 لكل إشارة
- **TP/SL**: `_calc_tp_sl()` يحسب أهداف الربح ووقف الخسارة تلقائياً
- **Stop-Loss Tracking**: `SIGNAL_SL_PCT = -5.0%` — يغلق التتبع عند خسارة 5%
- **Signal Timeout**: `SIGNAL_TIMEOUT_H = 8h` — إشارة تنتهي إذا لم تصل +5% خلال 8 ساعات
- **Milestone Images**: `_make_milestone_image()` + `_send_photo()` — صور عند الـ milestones
- **Telegram Commands**: `poll_telegram()` + `register_commands()` — أوامر تفاعلية
- **Reversal Alert**: `_fire_reversal()` — تنبيه عند انعكاس الإشارة (-3% من القمة)
- **Blacklist**: عملات محظورة دائماً (wash-trading, delisted)
- **Coin Categories**: تصنيف العملات (Meme, AI, DeFi, L1/L2...)
- **Reports**: يومي + أسبوعي + شهري
- **Sector Liquidity Scanner**: مسح قطاعي

### Scan Timing (v3.2)

| Scanner | Interval | Method |
|---------|----------|--------|
| fast_scan | 5s | price delta ≥ 0.3% → 5m klines |
| scan_sleeping_giant | 60s | flat coin + sudden 1m vol explosion |
| slow_scan | 5min | top 200 by vol → 1h klines |
| scan_quiet_accum | 5min | تراكم هادئ بدون spike كبير |
| scan_trend_follow | 5min | EMA trend follow |
| scan_sector_liquidity | 5min | sector rotation |
| scan_supertrend | 15min | SUPERTREND(10,3) flip |

### Market Bias (تكيف تلقائي)

`calc_market_bias()` يحسب -100 إلى +100 من Breadth + CVD + Taker-buy.
`get_market_ctx(bias)` يُعيد: `spike_mult, ratio_mult, pos_limit, late_pct, move_min, ob_min`.

### State Management

- **`alerted`**: cooldown 2h لكل عملة
- **`tracking`**: تتبع الأهداف مع SL وtimeout
- **`signal_history.json`**: قاعدة بيانات كاملة لكل الإشارات (append-only)
- **`_funding_cache`**: كاش funding rates لمدة 5 دقائق
- **`_signal_dedup`**: نافذة 60 ثانية لمنع تكرار الإشارة (fast_scan retrigger)
- Redis: يحفظ ويستعيد `alerted + tracking + signal_count`

## Key Design Decisions

- **MEXC أولاً**: لا يحجب IPs السحابية
- **Super-Ratio Bypass**: ratio ≥ 20x يتجاوز شرط spike_min
- **لا إشارة بدون تأكيد إرسال**: `send()` يجب أن ينجح قبل حفظ الحالة
- **Funding Bullish**: يُخفف جميع الشروط بنسبة 25-40%
- **DIAG log**: بعد كل slow_scan يُطبع سبب رفض كل عملة
- **`_signal_dedup`**: يمنع إعادة إطلاق نفس الإشارة خلال 60 ثانية من fast_scan السريع (5s)
