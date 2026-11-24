#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بورس‌ویو — راه‌انداز کراس‌پلتفرم (ویندوز، لینوکس، مک)
================================================================
این اسکریپت جایگزین run.sh و run.bat است و روی همه‌ی سیستم‌عامل‌ها
به‌طور یکسان کار می‌کند.

نحوهٔ اجرا:
    python launch.py           # پورت پیش‌فرض 5000
    python launch.py --port 8080
    python launch.py --no-browser   # مرورگر را باز نکن

سپس در مرورگر به http://127.0.0.1:5000 بروید.
"""

import os
import sys
import subprocess
import time
import threading
import webbrowser
import argparse
from pathlib import Path


BASE_DIR = Path(__file__).parent.resolve()
PROXY_FILE = BASE_DIR / "proxy.py"

# رنگ‌های ANSI برای خروجی ترمینال (در ویندوز 10+ هم پشتیبانی می‌شود)
def enable_colors():
    """فعال‌سازی کد ANSI در ویندوز."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

class C:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    NC = "\033[0m"


def print_banner():
    print(f"{C.CYAN}{'═' * 64}")
    print(f"║{C.BOLD}            بورس‌ویو — سامانه تحلیل بازار بورس ایران            {C.CYAN}║")
    print(f"║      اتصال مستقیم به API رسمی بورس تهران (TSETMC)             ║")
    print(f"{'═' * 64}{C.NC}")
    print()


def find_python():
    """پیدا کردن Python قابل اجرا — ترجیح به py (python.org) و دور شدن از Windows Store stub."""
    candidates = [sys.executable, "py", "python", "python3"]
    for cmd in candidates:
        try:
            # اول نسخه را بگیر
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                continue
            version_str = (result.stdout or result.stderr).strip()
            # یک تست واقعی هم بگیر (اجرای کد ساده)
            test = subprocess.run(
                [cmd, "-c", "import sys; print(sys.version_info[0])"],
                capture_output=True, text=True, timeout=5,
            )
            if test.returncode != 0:
                # اگر اجرا نشد، احتمالاً Windows Store stub است
                print(f"{C.RED}⚠  «{cmd}» اجرای کد را نمی‌پذیرد (احتمالاً نسخهٔ Microsoft Store).{C.NC}")
                print(f"{C.YELLOW}   نسخهٔ گزارش‌شده: {version_str}{C.NC}")
                print(f"{C.YELLOW}   برای نصب کامل Python به python.org مراجعه کنید.{C.NC}")
                print()
                continue
            return cmd, version_str
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None, None


def install_dependencies(python_cmd):
    """نصب flask و requests."""
    print(f"{C.YELLOW}⚙️  در حال نصب وابستگی‌ها (flask, requests)...{C.NC}")
    try:
        # اول با --user امتحان کن
        result = subprocess.run(
            [python_cmd, "-m", "pip", "install", "--user", "--quiet", "flask", "requests"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            # بدون --user امتحان کن
            result = subprocess.run(
                [python_cmd, "-m", "pip", "install", "--quiet", "flask", "requests"],
                capture_output=True, text=True, timeout=120
            )
        if result.returncode == 0:
            print(f"{C.GREEN}✓ وابستگی‌ها نصب شدند{C.NC}")
            return True
        else:
            print(f"{C.RED}✗ خطا در نصب:{C.NC}")
            print(result.stderr[:500] if result.stderr else "نامشخص")
            return False
    except subprocess.TimeoutExpired:
        print(f"{C.RED}✗ نصب بیش از حد طول کشید{C.NC}")
        return False
    except Exception as e:
        print(f"{C.RED}✗ خطا: {e}{C.NC}")
        return False


def check_dependencies(python_cmd):
    """بررسی اینکه flask و requests نصب شده‌اند."""
    try:
        result = subprocess.run(
            [python_cmd, "-c", "import flask; import requests; print('ok')"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0 and "ok" in (result.stdout or "")
    except Exception:
        return False


def open_browser_later(url, delay=3):
    """باز کردن مرورگر پس از چند ثانیه در یک thread جداگانه."""
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    t = threading.Thread(target=_open, daemon=True)
    t.start()


def run_proxy(python_cmd, port, open_browser=True):
    """اجرای پروکسی Flask."""
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOST"] = "127.0.0.1"

    url = f"http://127.0.0.1:{port}"
    print(f"{C.YELLOW}🚀 اجرای پروکسی روی پورت {port} ...{C.NC}")
    print(f"{C.CYAN}    آدرس سامانه: {url}{C.NC}")
    print(f"{C.CYAN}    برای توقف: Ctrl+C{C.NC}")
    print()

    if open_browser:
        open_browser_later(url, delay=3)

    # اجرای پروکسی
    try:
        # ارث بردن stdin برای پشتیبانی از Ctrl+C
        proc = subprocess.run(
            [python_cmd, str(PROXY_FILE)],
            env=env,
        )
        return proc.returncode
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}توقف پروکسی...{C.NC}")
        return 0
    except PermissionError:
        # خطای رایج در نسخهٔ Microsoft Store Python
        print()
        print(f"{C.RED}❌ خطای دسترسی (Access Denied) در اجرای Python!{C.NC}")
        print(f"{C.RED}   Python شما از Microsoft Store نصب شده و دسترسی محدود دارد.{C.NC}")
        print()
        print(f"{C.YELLOW}راه‌حل (۳۰ ثانیه):{C.NC}")
        print(f"  ۱) به این لینک بروید: {C.CYAN}https://www.python.org/downloads/{C.NC}")
        print(f"  ۲) دکمهٔ سبز «Download Python 3.12» را بزنید")
        print(f"  ۳) فایل را اجرا کنید و در صفحهٔ نصب تیک این گزینه را بزنید:")
        print(f"     {C.BOLD}☑ Add Python to PATH{C.NC}   (خیلی مهم!)")
        print(f"  ۴) پس از نصب، این فایل را دوباره اجرا کنید")
        print()
        return 1
    except Exception as e:
        print(f"{C.RED}✗ خطا در اجرای پروکسی: {e}{C.NC}")
        return 1


def main():
    enable_colors()
    print_banner()

    parser = argparse.ArgumentParser(
        description="بورس‌ویو — راه‌انداز کراس‌پلتفرم",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=5000, help="پورت سرور (پیش‌فرض: 5000)")
    parser.add_argument("--no-browser", action="store_true", help="مرورگر را به‌طور خودکار باز نکن")
    parser.add_argument("--install-only", action="store_true", help="فقط وابستگی‌ها را نصب کن و خارج شو")
    args = parser.parse_args()

    # ۱) پیدا کردن Python
    python_cmd, version_str = find_python()
    if not python_cmd:
        print(f"{C.RED}❌ Python قابل اجرا پیدا نشد.{C.NC}")
        print()
        print(f"{C.YELLOW}اگر از ویندوز استفاده می‌کنید:{C.NC}")
        print(f"  Python سیستم شما احتمالاً از Microsoft Store نصب شده که")
        print(f"  دسترسی محدود دارد (خطای Access Denied).")
        print()
        print(f"{C.BOLD}راه‌حل (۳۰ ثانیه):{C.NC}")
        print(f"  ۱) به این لینک بروید: {C.CYAN}https://www.python.org/downloads/{C.NC}")
        print(f"  ۲) دکمهٔ سبز «Download Python 3.12» را بزنید")
        print(f"  ۳) فایل نصب را اجرا کنید و در صفحهٔ اول تیک این گزینه را بزنید:")
        print(f"     {C.BOLD}☑ Add Python to PATH{C.NC}   (خیلی مهم!)")
        print(f"  ۴) پس از اتمام نصب، این فایل را دوباره اجرا کنید")
        print()
        if sys.platform.startswith("win"):
            print(f"{C.CYAN}سپس فایل run.bat را دوباره اجرا کنید.{C.NC}")
        sys.exit(1)
    print(f"{C.GREEN}✓ Python پیدا شد: {version_str}{C.NC}")

    # ۲) بررسی وابستگی‌ها
    if not check_dependencies(python_cmd):
        if not install_dependencies(python_cmd):
            print(f"{C.RED}❌ نصب وابستگی‌ها ناموفق بود.{C.NC}")
            print(f"    لطفاً دستی نصب کنید: {C.CYAN}pip install flask requests{C.NC}")
            sys.exit(1)
        # بررسی دوباره
        if not check_dependencies(python_cmd):
            print(f"{C.RED}❌ وابستگی‌ها همچنان نصب نیستند.{C.NC}")
            sys.exit(1)
    else:
        print(f"{C.GREEN}✓ وابستگی‌ها (flask, requests) آماده‌اند{C.NC}")

    if args.install_only:
        print(f"{C.GREEN}✓ همه‌چیز آماده است. می‌توانید proxy.py را اجرا کنید.{C.NC}")
        return

    # ۳) اجرای پروکسی
    sys.exit(run_proxy(python_cmd, args.port, open_browser=not args.no_browser))


if __name__ == "__main__":
    main()
