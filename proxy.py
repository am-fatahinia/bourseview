#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بورس‌ویو — پروکسی محلی برای دسترسی به API بورس ایران (TSETMC)
================================================================
این اسکریپت یک سرور Flask سبک است که درخواست‌های JSON را از مرورگر
شما می‌گیرد و به cdn.tsetmc.com/api/... فوروارد می‌کند، همراه با:
  • افزودن هدرهای صحیح (Referer, User-Agent) که TSETMC نیاز دارد
  • افزودن هدرهای CORS تا مرورگر بتواند پاسخ را بخواند
  • کش درون‌حافظه‌ای ۳۰ ثانیه‌ای برای دیده‌بان بازار و ۲ دقیقه‌ای برای داده‌های ثابت
  • Fallback هوشمند: در صورت قطع API، آخرین داده‌ی موفق برگردانده می‌شود

نحوه اجرا:
    pip install flask requests
    python proxy.py
سپس در مرورگر به http://localhost:5000 بروید.
"""

import os
import sys
import json
import time
import threading
import gzip
import io
from datetime import datetime, timedelta
from functools import wraps

try:
    import requests
except ImportError:
    print("خطا: کتابخانه requests نصب نیست.")
    print("اجرا کنید: pip install requests")
    sys.exit(1)

try:
    from flask import Flask, request, jsonify, send_from_directory, Response
except ImportError:
    print("خطا: کتابخانه flask نصب نیست.")
    print("اجرا کنید: pip install flask")
    sys.exit(1)

from concurrent.futures import ThreadPoolExecutor


# ──────────────────────────────────────────────────────────────────────────
# پیکربندی
# ──────────────────────────────────────────────────────────────────────────
TSETMC_BASE = "https://cdn.tsetmc.com/api"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://www.tsetmc.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# یک Session سراسری برای استفاده‌ی مجدد از connection pool
_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update(DEFAULT_HEADERS)
# timeout بیشتر برای مقابله با کندی گاه‌گاهی TSETMC
REQUEST_TIMEOUT = 30  # ثانیه

# مسیر پروژه
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, "bourseview.html")

# مدت زمان کش (ثانیه)
# نکته: TTL کمی بیشتر از فاصله‌ی به‌روزرسان خودکار (۳۰ ثانیه) تنظیم شده
# تا کش همیشه تازه باشد، حتی اگر به‌روزرسان چند ثانیه تأخیر داشته باشد.
CACHE_TTL = {
    "marketwatch": 45,        # دیده‌بان بازار — به‌روزرسان هر ۳۰ ثانیه
    "indices": 45,             # شاخص‌ها — به‌روزرسان هر ۳۰ ثانیه
    "funds": 180,              # صندوق‌ها — به‌روزرسان هر ۲ دقیقه
    "instrument_info": 60,     # اطلاعات سهم — هر ۱ دقیقه
    "instrument_identity": 3600,  # هویت سهم — هر ۱ ساعت (تقریباً ثابت)
    "closing_price_daily": 1800,  # تاریخچه روزانه — هر ۳۰ دقیقه
    "search": 600,             # جستجو — هر ۱۰ دقیقه
    "default": 60,
}

# حافظه کش ساده‌ی thread-safe
_cache = {}
_cache_lock = threading.Lock()
_last_good = {}  # برای fallback: آخرین پاسخ موفق هر endpoint

app = Flask(__name__, static_folder=None)


# ──────────────────────────────────────────────────────────────────────────
# ابزارهای کش و ارسال درخواست
# ──────────────────────────────────────────────────────────────────────────
def cache_key(endpoint, *parts):
    return endpoint + ":" + "/".join(str(p) for p in parts)


def get_cached(key, ttl):
    """اگر کش معتبر باشد، داده را برمی‌گرداند."""
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"]) < ttl:
            return entry["data"], True
        # اگر کش منقضی شده ولی fallback داریم، دادهٔ قبلی را برگردان
        if key in _last_good:
            return _last_good[key]["data"], False
        return None, False


def set_cached(key, data, is_success=True):
    """ذخیره در کش و در last_good در صورت موفقیت."""
    now = time.time()
    with _cache_lock:
        _cache[key] = {"data": data, "ts": now}
        if is_success:
            _last_good[key] = {"data": data, "ts": now}


def fetch_tsetmc(path, ttl_key="default", force=False):
    """دریافت داده از TSETMC با هدرهای لازم و کش و fallback.

    پارامتر force=True همیشه درخواست واقعی به TSETMC می‌فرستد (برای refresh پس‌زمینه).
    """
    url = TSETMC_BASE + path
    key = cache_key(ttl_key, path)
    ttl = CACHE_TTL.get(ttl_key, CACHE_TTL["default"])

    # ۱) اگر force نیست، ابتدا کش را بررسی کن
    if not force:
        cached, is_fresh = get_cached(key, ttl)
        if cached is not None:
            # اگر داده از کش تازه باشد، بدون هیچ پس‌زمینه‌ای برگردان
            # اگر stale باشد، در پس‌زمینه به‌روزرسانی کن
            if not is_fresh:
                t = threading.Thread(target=_refresh_cache, args=(path, ttl_key, key), daemon=True)
                t.start()
            return cached, is_fresh

    # ۲) درخواست واقعی به TSETMC (force=True یا cache miss)
    try:
        resp = _HTTP_SESSION.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200 and resp.text.strip():
            data = resp.json()
            set_cached(key, data, is_success=True)
            return data, True
        else:
            # پاسخ ناموفق بود — اگر last_good داریم برگردان
            with _cache_lock:
                if key in _last_good:
                    return _last_good[key]["data"], False
            return {"error": f"TSETMC returned status {resp.status_code}", "data": None}, False
    except requests.exceptions.Timeout:
        with _cache_lock:
            if key in _last_good:
                return _last_good[key]["data"], False
        return {"error": "timeout", "data": None}, False
    except requests.exceptions.RequestException as e:
        with _cache_lock:
            if key in _last_good:
                return _last_good[key]["data"], False
        return {"error": f"request_error: {str(e)}", "data": None}, False
    except json.JSONDecodeError:
        with _cache_lock:
            if key in _last_good:
                return _last_good[key]["data"], False
        return {"error": "invalid_json", "data": None}, False


def _refresh_cache(path, ttl_key, key):
    """به‌روزرسانی کش در پس‌زمینه."""
    try:
        url = TSETMC_BASE + path
        resp = _HTTP_SESSION.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200 and resp.text.strip():
            data = resp.json()
            set_cached(key, data, is_success=True)
    except Exception:
        pass  # اگر نشد، کش قدیمی همچنان معتبر است


# ──────────────────────────────────────────────────────────────────────────
# راه‌اندازی به‌روزرسان خودکار (Proactive Refresher)
# در production (gunicorn) با --preload، این کد در master اجرا نمی‌شود
# بلکه در هر worker بعد از fork اجرا می‌شود.
# ──────────────────────────────────────────────────────────────────────────
_refresher_started = False

def start_proactive_refresher():
    """شروع به‌روزرسان خودکار اگر قبلاً شروع نشده باشد (thread-safe)."""
    global _refresher_started
    if _refresher_started:
        return
    _refresher_started = True
    t = threading.Thread(target=_proactive_refresher, daemon=True)
    t.start()
    print("  [refresher] به‌روزرسان خودکار شروع شد", flush=True)


def _proactive_refresher():
    """به‌طور خودکار و مستقل از درخواست‌ها، کش داده‌های زنده را تازه نگه می‌دارد."""
    time.sleep(2)
    print("  [refresher] راه‌اندازی به‌روزرسان خودکار (هر ۳۰ ثانیه)", flush=True)

    cycle = 0
    while True:
        cycle += 1
        start = time.time()
        try:
            with ThreadPoolExecutor(max_workers=2) as ex:
                futures = [
                    ex.submit(fetch_tsetmc, "/ClosingPrice/GetMarketWatch", "marketwatch", True),
                    ex.submit(fetch_tsetmc, "/Index/GetIndexB1LastAll/0/1", "indices", True),
                ]
                for f in futures:
                    try:
                        f.result(timeout=35)
                    except Exception:
                        pass

            if cycle % 4 == 0:
                with ThreadPoolExecutor(max_workers=3) as ex:
                    futs = [ex.submit(fetch_tsetmc, f"/Fund/GetFunds/{t}", "funds", True) for t in ("3", "4", "5")]
                    for f in futs:
                        try:
                            f.result(timeout=35)
                        except Exception:
                            pass

            elapsed = time.time() - start
            print(f"  [refresher] چرخه {cycle} ✓ ({elapsed:.1f}s, cache={len(_cache)})", flush=True)
        except Exception as e:
            print(f"  [refresher] خطا در چرخه {cycle}: {e}", flush=True)

        wait = max(5, 30 - (time.time() - start))
        time.sleep(wait)


# شروع به‌روزرسان هنگام import (برای gunicorn با --preload، در هر worker)
# اما فقط اگر مستر نیستیم
if not os.environ.get("GUNICORN_MASTER") == "1":
    # در حالت local (python proxy.py) یا worker گانیکورن
    # در مستر گانیکورن (با --preload)، این کد اجرا نمی‌شود چون GUNICORN_MASTER=1
    pass  # refresher بعد از first request شروع می‌شود


@app.before_request
def _ensure_refresher():
    """شروع به‌روزرسان در اولین درخواست (برای production)."""
    if not _refresher_started:
        start_proactive_refresher()


def cors_headers(f):
    """Decorator برای افزودن هدرهای CORS به همه‌ی پاسخ‌ها."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        resp = f(*args, **kwargs)
        if isinstance(resp, tuple):
            data, status = resp[0], resp[1] if len(resp) > 1 else 200
        else:
            data, status = resp, 200
        if isinstance(data, Response):
            data.headers["Access-Control-Allow-Origin"] = "*"
            data.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            data.headers["Access-Control-Allow-Headers"] = "Content-Type"
            data.headers["Cache-Control"] = "no-cache"
            return data
        out = jsonify(data)
        out.status_code = status
        out.headers["Access-Control-Allow-Origin"] = "*"
        out.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        out.headers["Access-Control-Allow-Headers"] = "Content-Type"
        out.headers["Cache-Control"] = "no-cache"
        return out
    return wrapped


# ──────────────────────────────────────────────────────────────────────────
# مسیرهای API پروکسی
# ──────────────────────────────────────────────────────────────────────────

@app.route("/api/health")
@cors_headers
def health():
    """بررسی سلامت پروکسی — برای تست سریع."""
    # گزارش سن کش برای هر endpoint کلیدی
    now = time.time()
    cache_ages = {}
    for label, path, ttl_key in [
        ("marketwatch", "/ClosingPrice/GetMarketWatch", "marketwatch"),
        ("indices", "/Index/GetIndexB1LastAll/0/1", "indices"),
    ]:
        key = cache_key(ttl_key, path)
        entry = _cache.get(key)
        if entry:
            cache_ages[label] = round(now - entry["ts"], 1)
        else:
            cache_ages[label] = None
    return {
        "status": "ok",
        "time": datetime.now().isoformat(),
        "cache_size": len(_cache),
        "cache_ages": cache_ages,
        "has_refresher": True,
    }


@app.route("/api/marketwatch")
@cors_headers
def marketwatch():
    """دیده‌بان بازار — همه‌ی نمادهای بورس و فرابورس."""
    data, fresh = fetch_tsetmc("/ClosingPrice/GetMarketWatch", "marketwatch")
    # فیلتر فقط سهام عادی (yVal=300 و بازارهای 1/2/4)
    try:
        items = data.get("marketwatch", [])
        # فقط نمادهای معامله‌شده‌ی امروز (با قیمت > 0)
        stocks = [
            it for it in items
            if it.get("yVal") == 300
            and it.get("flow") in (1, 2, 4)
            and (it.get("pClosing") or it.get("pDrCotVal") or it.get("pmd") or 0) > 0
        ]
        return {
            "count": len(stocks),
            "total_instruments": len(items),
            "fresh": fresh,
            "ts": datetime.now().isoformat(),
            "stocks": stocks,
        }
    except Exception as e:
        return {"error": str(e), "stocks": [], "fresh": fresh}, 500


@app.route("/api/marketwatch/all")
@cors_headers
def marketwatch_all():
    """دیده‌بان کامل — همه‌ی نمادها بدون فیلتر (صندوق‌ها، حق تقدم، اوراق و...)."""
    data, fresh = fetch_tsetmc("/ClosingPrice/GetMarketWatch", "marketwatch")
    items = data.get("marketwatch", []) if "marketwatch" in data else []
    # گروه‌بندی بر اساس yVal برای دسترسی آسان
    by_type = {}
    for it in items:
        y = it.get("yVal")
        by_type.setdefault(y, []).append(it)
    return {
        "total": len(items),
        "fresh": fresh,
        "ts": datetime.now().isoformat(),
        "by_type": by_type,
        "items": items,
    }


@app.route("/api/indices")
@cors_headers
def indices():
    """همه‌ی شاخص‌های بازار (شامل شاخص کل، هم‌وزن و گروه‌های صنعت)."""
    data, fresh = fetch_tsetmc("/Index/GetIndexB1LastAll/0/1", "indices")
    # اگر data خطا باشد، items خالی می‌شود
    if not isinstance(data, dict) or "indexB1" not in data:
        return {
            "all": [],
            "main": {},
            "sectors": [],
            "others": [],
            "fresh": False,
            "ts": datetime.now().isoformat(),
            "error": data.get("error") if isinstance(data, dict) else "unknown_error",
        }
    items = data.get("indexB1", [])
    # مشخص کردن شاخص‌های کلیدی برای دسترسی سریع
    main_keys = {
        "32097828799138957": "tedpix",        # شاخص کل
        "67130298613737946": "tedpix_equal",  # شاخص کل (هم وزن)
        "8384385859414435": "price_equal",    # شاخص قیمت (هم وزن)
        "49579049405614711": "ifx",           # شاخص آزاد شناور
        "43754960038275285": "industry",      # شاخص صنعت
        "62752761908615603": "market1",       # شاخص بازار اول
        "71704845530629737": "market2",       # شاخص بازار دوم
    }
    main = {}
    for it in items:
        code = it.get("insCode")
        if code in main_keys:
            main[main_keys[code]] = {
                "name": it.get("lVal30"),
                "value": it.get("xDrNivJIdx004"),
                "change_pct": it.get("xVarIdxJRfV"),
                "change_value": it.get("indexChange"),
                "ins_code": code,
            }
    # شاخص‌های صنعت (گره‌های ۲ رقمی شروع می‌شوند با عدد مثل "01-زراعت")
    sector_indices = []
    other_indices = []
    for it in items:
        name = it.get("lVal30", "")
        if name and name[:2].isdigit() and "-" in name[:5]:
            sector_indices.append(it)
        elif not name.startswith("شاخص"):
            other_indices.append(it)
    return {
        "all": items,
        "main": main,
        "sectors": sector_indices,
        "others": other_indices,
        "fresh": fresh,
        "ts": datetime.now().isoformat(),
    }


@app.route("/api/stock/<ins_code>")
@cors_headers
def stock_detail(ins_code):
    """اطلاعات کامل یک سهم: هویتی + قیمت + نسبت‌ها."""
    # ۱) هویت سهم (نام، گروه صنعت، تعداد سهام و...)
    identity_data, _ = fetch_tsetmc(f"/Instrument/GetInstrumentIdentity/{ins_code}", "instrument_identity")
    # ۲) اطلاعات سهم (EPS، PE گروه، min/max هفته و سال، میانگین ارزش معاملات)
    info_data, _ = fetch_tsetmc(f"/Instrument/GetInstrumentInfo/{ins_code}", "instrument_info")
    # ۳) قیمت روز (قیمت دیروز، آخرین قیمت، حدود قیمت، وضعیت بازار)
    closing_data, _ = fetch_tsetmc(f"/ClosingPrice/GetClosingPriceInfo/{ins_code}", "instrument_info")

    result = {
        "ins_code": ins_code,
        "identity": identity_data.get("instrumentIdentity", {}) if isinstance(identity_data, dict) else {},
        "info": info_data.get("instrumentInfo", {}) if isinstance(info_data, dict) else {},
        "closing": closing_data.get("closingPriceInfo", {}) if isinstance(closing_data, dict) else {},
        "ts": datetime.now().isoformat(),
    }
    return result


@app.route("/api/stock/<ins_code>/chart")
@cors_headers
def stock_chart(ins_code):
    """دریافت تاریخچه قیمت سهم برای رسم نمودار.
    
    پارامترها:
      days: تعداد روزهای گذشته (پیش‌فرض 365)
    
    نکته: API بورس تاریخچه‌ی چندروزه را مستقیم نمی‌دهد؛ ما N روز کاری اخیر را
    با فراخوانی چندباره‌ی endpoint روزانه می‌گیریم. برای جلوگیری از کندی،
    تعداد روزها را به صورت هوشمند محدود می‌کنیم و کش طولانی می‌کنیم.
    """
    try:
        days = int(request.args.get("days", 365))
    except ValueError:
        days = 365
    days = max(10, min(days, 1000))  # محدودیت منطقی

    # پیدا کردن آخرین روز معاملاتی از closingPriceInfo
    info_data, _ = fetch_tsetmc(f"/ClosingPrice/GetClosingPriceInfo/{ins_code}", "instrument_info")
    last_date = None
    if isinstance(info_data, dict):
        info = info_data.get("closingPriceInfo", {})
        last_date = info.get("finalLastDate")

    if not last_date:
        return {"error": "could not determine last trading day", "history": []}, 500

    # تولید لیست N روز گذشته (تقویمی) - ما درخواست را برای هر روز می‌فرستیم
    # اما TSETMC فقط روزهای کاری را پاسخ می‌دهد (پس بی‌اثر است)
    # برای پرفورمنس بهتر، تاریخچه چندروزه را از یک endpoint دیگر می‌گیریم
    # سعی می‌کنیم با GetClosingPriceLastDayHistory که تاریخچه 30 روز اخیر را می‌دهد
    history_data, _ = fetch_tsetmc(
        f"/ClosingPrice/GetClosingPriceLastDayHistory/{ins_code}",
        "closing_price_daily"
    )
    history = history_data.get("closingPriceHistory", []) if isinstance(history_data, dict) else []
    # اگر تاریخچه کافی نبود، روز به روز از آخرین تاریخ بگیر
    # (این بخش را برای سادگی غیرفعال می‌کنیم؛ ۳۰ روز اخیر کافی است برای نمودار کوتاه‌مدت)
    return {
        "ins_code": ins_code,
        "last_date": last_date,
        "history": history,
        "ts": datetime.now().isoformat(),
    }


@app.route("/api/stock/<ins_code>/intraday")
@cors_headers
def stock_intraday(ins_code):
    """داده‌های لحظه‌ای/روزانه‌ی یک سهم برای یک تاریخ خاص (پیش‌فرض آخرین روز معاملاتی).
    
    اگر امروز بازار هنوز معامله‌ای نداشته باشد، آخرین روز معاملاتی قبل استفاده می‌شود.
    """
    date = request.args.get("date")
    if not date:
        # آخرین روز معاملاتی را پیدا کن
        info_data, _ = fetch_tsetmc(f"/ClosingPrice/GetClosingPriceInfo/{ins_code}", "instrument_info")
        if isinstance(info_data, dict):
            info = info_data.get("closingPriceInfo", {})
            date = info.get("finalLastDate")
    if not date:
        return {"error": "date required", "history": []}, 400

    # تبدیل به عدد صحیح YYYYMMDD
    try:
        date_int = int(str(date).replace("-", "").replace("/", "")[:8])
    except (ValueError, TypeError):
        return {"error": "invalid date format", "history": []}, 400

    # تلاش برای دریافت تاریخچهٔ این تاریخ
    data, fresh = fetch_tsetmc(
        f"/ClosingPrice/GetClosingPriceHistory/{ins_code}/{date_int}",
        "closing_price_daily"
    )
    history = data.get("closingPriceHistory", []) if isinstance(data, dict) else []

    # اگر داده‌ها خیلی کم بود (کمتر از ۵ نقطه — یعنی بازار هنوز معامله نکرده)،
    # به‌جای آن، روز کاری قبلی را امتحان کن
    if len(history) < 5:
        prev_date = _previous_trading_day(date_int)
        if prev_date:
            data_prev, _ = fetch_tsetmc(
                f"/ClosingPrice/GetClosingPriceHistory/{ins_code}/{prev_date}",
                "closing_price_daily"
            )
            prev_history = data_prev.get("closingPriceHistory", []) if isinstance(data_prev, dict) else []
            if len(prev_history) > len(history):
                history = prev_history
                date_int = prev_date
                data = data_prev
                fresh = False

    return {
        "ins_code": ins_code,
        "date": date_int,
        "history": history,
        "fresh": fresh,
        "ts": datetime.now().isoformat(),
    }


def _previous_trading_day(date_int):
    """محاسبهٔ روز کاری قبلی از تاریخ YYYYMMDD."""
    from datetime import datetime as dt, timedelta
    try:
        s = str(date_int)
        d = dt(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, TypeError):
        return None
    # عقب برو تا به روز کاری (جمعه نه) برسیم
    for _ in range(7):
        d = d - timedelta(days=1)
        # 4 = Thursday in Python's weekday() (Mon=0)
        # 5 = Friday, 6 = Saturday
        if d.weekday() == 4:  # پنجشنبه — بازار تا ظهر باز است ولی برای سادگی رد می‌کنیم
            continue
        if d.weekday() == 5:  # جمعه — بسته
            continue
        return int(d.strftime("%Y%m%d"))
    return None


@app.route("/api/funds")
@cors_headers
def funds():
    """همه‌ی صندوق‌های قابل معامله (ETF).
    
    نوع ۴: صندوق‌های درآمد ثابت و سهامی (پرکاربرد)
    نوع ۳: صندوق‌های طلا
    نوع ۵: صندوق‌های مختلط
    """
    types = request.args.get("types", "3,4,5")
    types_list = [t.strip() for t in types.split(",") if t.strip()]

    # دریافت موازی همه‌ی انواع صندوق‌ها
    def fetch_one(t):
        data, _ = fetch_tsetmc(f"/Fund/GetFunds/{t}", "funds")
        if isinstance(data, dict) and "funds" in data:
            for f in data["funds"]:
                f["_fund_type_id"] = t
            return data["funds"]
        return []

    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(fetch_one, types_list))

    all_funds = []
    for r in results:
        all_funds.extend(r)

    return {
        "count": len(all_funds),
        "funds": all_funds,
        "ts": datetime.now().isoformat(),
    }


@app.route("/api/search")
@cors_headers
def search():
    """جستجوی نماد بر اساس نام فارسی یا لاتین.
    
    پارامتر: q (query string)
    """
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return {"results": [], "query": q}
    # URL-encode کردن query به صورت صحیح برای کاراکترهای فارسی
    from urllib.parse import quote
    q_encoded = quote(q)
    data, _ = fetch_tsetmc(f"/Instrument/GetInstrumentSearch/{q_encoded}", "search")
    results = data.get("instrumentSearch", []) if isinstance(data, dict) else []
    return {"results": results, "query": q}


@app.route("/api/sectors")
@cors_headers
def sectors():
    """لیست گروه‌های صنعت (از شاخص‌ها استخراج می‌شود)."""
    data, _ = fetch_tsetmc("/Index/GetIndexB1LastAll/0/1", "indices")
    items = data.get("indexB1", []) if isinstance(data, dict) else []
    sector_list = []
    for it in items:
        name = it.get("lVal30", "")
        # شاخص‌های صنعت با عدد شروع می‌شوند، مثل "01-زراعت"
        if name and name[:2].isdigit() and "-" in name[:5]:
            sector_list.append({
                "code": it.get("insCode"),
                "name": name,
                "value": it.get("xDrNivJIdx004"),
                "change_pct": it.get("xVarIdxJRfV"),
                "change_value": it.get("indexChange"),
            })
    return {"sectors": sector_list, "count": len(sector_list)}


# ──────────────────────────────────────────────────────────────────────────
# سرو فایل HTML اصلی
# ──────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if not os.path.exists(HTML_FILE):
        return """
        <html dir="rtl"><body style="font-family:Tahoma;padding:40px;direction:rtl">
        <h2>فایل bourseview.html یافت نشد</h2>
        <p>مطمئن شوید فایل HTML در همان پوشه‌ی proxy.py قرار دارد.</p>
        <p>مسیر انتظار: <code>{}</code></p>
        </body></html>
        """.format(HTML_FILE), 404
    return send_from_directory(BASE_DIR, "bourseview.html")


@app.route("/<path:filename>")
def static_files(filename):
    """سرو فایل‌های استاتیک در همان پوشه (CSS, JS, تصاویر)."""
    # جلوگیری از دسترسی به فایل‌های حساس
    if filename in ("proxy.py", "run.sh", "run.bat", "launch.py", "README.md",
                    "requirements.txt", "render.yaml", "Procfile", "runtime.txt",
                    ".gitignore", "DEPLOY.md", ".env"):
        return "Not Found", 404
    full = os.path.join(BASE_DIR, filename)
    if os.path.isfile(full):
        return send_from_directory(BASE_DIR, filename)
    return "Not Found", 404


# ──────────────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    print("=" * 60)
    print("  بورس‌ویو — پروکسی محلی بورس ایران")
    print("=" * 60)
    print(f"  سرور روی: http://{host}:{port}")
    print(f"  فایل HTML: {HTML_FILE}")
    print()
    print("  برای توقف: Ctrl+C")
    print("=" * 60)
    print()
    # پیش‌بارگذاری (warmup) داده‌های اصلی به صورت موازی
    def warmup():
        time.sleep(1)
        print("  [warmup] در حال بارگذاری اولیه‌ی داده‌ها (موازی)...")
        def fetch_one(path, ttl_key, label):
            try:
                fetch_tsetmc(path, ttl_key)
                print(f"  [warmup] ✓ {label}")
            except Exception as e:
                print(f"  [warmup] ✗ {label}: {e}")
        with ThreadPoolExecutor(max_workers=6) as ex:
            ex.map(lambda args: fetch_one(*args), [
                ("/ClosingPrice/GetMarketWatch", "marketwatch", "MarketWatch"),
                ("/Index/GetIndexB1LastAll/0/1", "indices", "Indices"),
                ("/Fund/GetFunds/3", "funds", "Funds (type 3 - gold)"),
                ("/Fund/GetFunds/4", "funds", "Funds (type 4 - fixed income)"),
                ("/Fund/GetFunds/5", "funds", "Funds (type 5 - mixed)"),
            ])
        print("  [warmup] بارگذاری اولیه کامل شد.")
    t = threading.Thread(target=warmup, daemon=True)
    t.start()

    # به‌روزرسان خودکار (proactive refresher)
    # کش را هر ۳۰ ثانیه مستقل از درخواست‌ها تازه می‌کند
    start_proactive_refresher()

    # حالت توسعه: use_reloader=False برای جلوگیری از اجرای دوبله‌ی warmup
    # production: threaded=True برای پاسخگویی همزمان
    app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
