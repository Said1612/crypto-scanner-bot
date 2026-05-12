# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MAFIO Liquidity Scanner v3.1** — بوت مسح السيولة للعملات الرقمية.
يراقب أسواق MEXC وBinance بحثاً عن إشارات دخول قوية بناءً على تحليل تدفق السيولة، ويرسل التنبيهات عبر Telegram.

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
| `TELEGRAM_TOKEN` | توكن بوت Telegram |
| `CHAT_ID` | معرف المحادثة الخاصة |
| `GROUP_ID` | معرف المجموعة (اختياري) |
| `UPSTASH_REDIS_REST_URL` | رابط Redis لحفظ الحالة |
| `UPSTASH_REDIS_REST_TOKEN` | توكن Redis |
| `USE_BINANCE` | `true/false` — تفعيل Binance (قد يُحجب على Railway) |
| `PROXY_URL` | بروكسي اختياري |

يعمل البوت على **Railway** — MEXC لا يحجب IPs السحابية، لكن Binance قد يحجبها.

## Architecture

كل الكود في ملف واحد: `main.py` (~1100 سطر)

### دورة العمل الرئيسية

```
main() loop (كل ثانية)
├── كل 30 ثانية → fast_scan()   → _check() بـ 5m klines
└── كل 5 دقائق  → slow_scan()  → _check() بـ 1h/60m klines
```

### تدفق `_check()` (الفلتر الرئيسي)

```
1. فلاتر سريعة (بدون API): pump_24h, cooldown, tier, late_entry, vol_floor, bias_gate
2. fetch_klines()       → vol_spike_and_move(), calc_flow()
3. fetch_funding_rate() → تعديل الحدود إذا كان bullish
4. fetch_agg_trades()   → ratio, net flow
5. fetch_ob_imbalance() → spot + futures order book
6. build_signal() + send() → Telegram
7. حفظ في alerted + tracking + Redis
```

### نظام الـ Tiers (حسب حجم التداول 24h)

| Tier | Volume | spike_min | ratio_min | net_min |
|------|--------|-----------|-----------|---------|
| Micro | < $2M | 3.5x | 2.5x | $300 |
| Small | $2-15M | 2.8x | 2.5x | $1,500 |
| Mid | $15-80M | 2.5x | 2.5x | $15,000 |
| Large | > $80M | 2.2x | 1.8x | $80,000 |

### Market Bias (تكيف تلقائي مع السوق)

`calc_market_bias()` يحسب نقاط -100 إلى +100 من:
- **Breadth**: نسبة العملات الصاعدة مقابل الهابطة
- **CVD**: إجمالي تدفق الشراء مقابل البيع
- **Taker-buy ratio**: نسبة أوامر الشراء السوقية

`get_market_ctx(bias)` يُعيد معاملات تكيفية: `spike_mult, ratio_min, pos_limit, late_pct, move_min`

### State Management

- **`alerted`**: `{sym: timestamp}` — cooldown 2h لكل عملة
- **`tracking`**: `{sym: {entry, t0, hit, max, exchange}}` — تتبع الأهداف
- **`_funding_cache`**: كاش funding rates لمدة 5 دقائق
- **`_multi_confirm`**: تأكيد متعدد المسحات (fast + slow) خلال 30 دقيقة

الحالة تُحفظ في Redis وتُستعاد عند إعادة التشغيل.

### Milestone Tracking

`check_milestones()` يُرسل تنبيهاً عند بلوغ: 2%, 5%, 10%, 15%, 20%, 25%, 30%, 40%, 50%, 75%, 100%, ...
يتتبع العملات لمدة 24 ساعة بعد الإشارة.

## Deployment

يعمل على **Railway** عبر `nixpacks.toml`:
```toml
[start]
cmd = "python main.py"
```
Python version: 3.11.6 (محدد في `runtime.txt`)

## Key Design Decisions

- **MEXC أولاً**: لا يحجب IPs السحابية على عكس Binance
- **Super-Ratio Bypass**: إذا كان ratio ≥ 20x، يتجاوز شرط الـ spike_min
- **لا إشارة بدون تأكيد إرسال**: `send()` يجب أن ينجح قبل حفظ الحالة
- **Funding Bullish**: يُخفف جميع الشروط بنسبة 25-40%
- **DIAG log**: بعد كل slow_scan يُطبع سبب رفض كل عملة (لتحسين الفلاتر)
