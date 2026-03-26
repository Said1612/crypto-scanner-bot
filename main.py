# -*- coding: utf-8 -*-
# Build: 20260320-001
"""
╔══════════════════════════════════════════════════════════════╗
║           MAFIO-BOT — UNIFIED ENGINE            ║
║   Anti-Rate-Limit + Smart Cache + Trailing Stop            ║
║   Smart Top10 — اصطياد العملات قبل الانفجار               ║
╚══════════════════════════════════════════════════════════════╝

التحسينات في V15 (فوق V14):
  ✅ FIX: تنظيف جميع الرموز الخاطئة في SECTORS (مسافات + حروف سيريلية)
  🆕 vol_ratio تاريخي: مقارنة حجم العملة بمتوسطها التاريخي (لا بمتوسط القطاع)
  🆕 RSI Filter: فلتر RSI على 14 فترة — يرفض العملات overbought (RSI>70)
  🆕 Backtesting: تتبع إشارات Top10 وقياس الأداء الفعلي بعد 1h/4h/24h
  🆕 رسالة Telegram محسّنة: أوضح + RSI + نسبة النجاح التاريخية

استراتيجية الطلبات (Anti-Rate-Limit):
  ● طلب واحد للـ 24h Ticker  كل 12 ثانية   → 5/دقيقة
  ● Cache ذكي: 15m=60s, 1h=5min, 4h=15min
  ● Scan عميق (Klines+OrderBook) كل ساعة
  ● الفلتر المسبق يرفض 90% من العملات بدون Klines

النتيجة: ~8 طلبات/دقيقة بدل 492 ✅
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any, Set
