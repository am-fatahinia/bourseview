#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# اسکریپت کمکی دیپلوی بورس‌ویو
# ═══════════════════════════════════════════════════════════════
# این اسکریپت:
# 1. git repository را آماده می‌کند
# 2. تغییرات را commit و push می‌کند
# 3. دستورالعمل دیپلوی روی Render را نمایش می‌دهد
# ═══════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"

echo "═══════════════════════════════════════════════════"
echo "  🚀 آماده‌سازی دیپلوی بورس‌ویو"
echo "═══════════════════════════════════════════════════"
echo ""

# بررسی git
if ! command -v git &> /dev/null; then
    echo "❌ خطا: git نصب نیست."
    echo "   نصب: https://git-scm.com/downloads"
    exit 1
fi

# راه‌اندازی git اگر لازم است
if [ ! -d .git ]; then
    echo "📦 راه‌اندازی git repository..."
    git init
    git branch -M main
fi

# بررسی remote
REMOTE=$(git remote get-url origin 2>/dev/null || echo "")

if [ -z "$REMOTE" ]; then
    echo ""
    echo "🔗 ابتدا یک repository در گیت‌هاب بسازید:"
    echo "   https://github.com/new"
    echo ""
    echo "   سپس آدرس آن را وارد کنید."
    echo ""
    read -p "   آدرس repository (مثل https://github.com/user/bourseview.git): " REPO_URL
    
    if [ -z "$REPO_URL" ]; then
        echo "❌ آدرس repository وارد نشد."
        exit 1
    fi
    
    git remote add origin "$REPO_URL"
    echo "✅ remote اضافه شد: $REPO_URL"
fi

echo ""
echo "📦 افزودن فایل‌ها..."
git add .
git status --short

echo ""
read -p "پیام commit (Enter برای پیش‌فرض): " COMMIT_MSG
COMMIT_MSG=${COMMIT_MSG:-"Deploy: بورس‌ویو با داده‌ی زنده TSETMC"}

git commit -m "$COMMIT_MSG" || echo "ℹ️  تغییر جدیدی برای commit نیست."

echo ""
echo "🚀 push به گیت‌هاب..."
git push -u origin main || {
    echo "❌ push ناموفق بود. ممکن است نیاز باشد ابتدا pull کنید:"
    echo "   git pull --rebase origin main"
    exit 1
}

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ کد آماده دیپلوی است!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "📋 مراحل بعدی:"
echo ""
echo "  1. به https://dashboard.render.com بروید"
echo "  2. روی 'New +' کلیک کنید → 'Web Service'"
echo "  3. repository خود را انتخاب کنید"
echo "  4. Render به‌طور خودکار render.yaml را می‌خواند"
echo "  5. روی 'Create Web Service' کلیک کنید"
echo "  6. منتظر بمانید تا build کامل شود (۳–۵ دقیقه)"
echo ""
echo "📖 برای جزئیات بیشتر: DEPLOY.md را بخوانید"
echo ""
