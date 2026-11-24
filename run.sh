#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# بورس‌ویو — اسکریپت راه‌اندازی سریع
# ═══════════════════════════════════════════════════════════════
# این اسکریپت:
#   ۱) وابستگی‌های Python را نصب می‌کند (flask, requests)
#   ۲) پروکسی محلی را روی پورت 5000 اجرا می‌کند
#   ۳) مرورگر پیش‌فرض را به آدرس http://127.0.0.1:5000 باز می‌کند
# ═══════════════════════════════════════════════════════════════

set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# رنگ‌ها برای خروجی ترمینال
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║            بورس‌ویو — سامانه تحلیل بازار بورس ایران           ║"
    echo "║                                                              ║"
    echo "║      اتصال مستقیم به API رسمی بورس تهران (TSETMC)             ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# بررسی Python
check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        echo -e "${RED}❌ Python نصب نیست. ابتدا Python 3.8 یا بالاتر را نصب کنید:${NC}"
        echo -e "    Ubuntu/Debian:  sudo apt install python3 python3-pip"
        echo -e "    macOS (brew):    brew install python"
        echo -e "    Windows:         https://python.org/downloads/"
        exit 1
    fi
    echo -e "${GREEN}✓ Python پیدا شد: $($PYTHON --version)${NC}"
}

# بررسی و نصب وابستگی‌ها
check_deps() {
    echo -e "${YELLOW}⚙️  بررسی و نصب وابستگی‌ها...${NC}"
    $PYTHON -m pip install --quiet --user flask requests 2>&1 | tail -3 || {
        echo -e "${YELLOW}تلاش با --break-system-packages...${NC}"
        $PYTHON -m pip install --quiet --break-system-packages flask requests 2>&1 | tail -3
    }
    echo -e "${GREEN}✓ وابستگی‌ها آماده‌اند${NC}"
}

# اجرای پروکسی
run_proxy() {
    PORT=${PORT:-5000}
    echo -e "${YELLOW}🚀 اجرای پروکسی روی پورت $PORT ...${NC}"
    echo -e "${CYAN}    آدرس سامانه: http://127.0.0.1:$PORT${NC}"
    echo -e "${CYAN}    برای توقف: Ctrl+C${NC}"
    echo ""

    # باز کردن مرورگر پس از ۲ ثانیه در پس‌زمینه
    (
        sleep 2
        URL="http://127.0.0.1:$PORT"
        if command -v xdg-open &>/dev/null; then
            xdg-open "$URL" >/dev/null 2>&1 || true
        elif command -v open &>/dev/null; then
            open "$URL" >/dev/null 2>&1 || true
        elif command -v start &>/dev/null; then
            start "$URL" >/dev/null 2>&1 || true
        else
            echo -e "${YELLOW}🔗 مرورگر را به صورت دستی باز کنید: $URL${NC}"
        fi
    ) &

    # اجرای پروکسی
    $PYTHON proxy.py
}

# ────────── main ──────────
print_banner
check_python
check_deps
run_proxy
