# ═══════════════════════════════════════════════════════════════
# بورس‌ویو — راه‌انداز PowerShell برای ویندوز
# ═══════════════════════════════════════════════════════════════
# نحوهٔ اجرا:
#   ۱. PowerShell را باز کنید
#   ۲. cd به پوشهٔ پروژه
#   ۳. اجرا: powershell -ExecutionPolicy Bypass -File .\run.ps1
#   یا اگر خطای اجرای اسکریپت دیدید:
#   powershell -ExecutionPolicy RemoteSigned -File .\run.ps1
# ═══════════════════════════════════════════════════════════════

# تنظیم Encoding برای پشتیبانی از فارسی
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$host.UI.RawUI.WindowTitle = "BourseView - بورس‌ویو"

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  بورس‌ویو — سامانه تحلیل بازار بورس ایران (TSETMC)" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# رفتن به پوشهٔ اسکریپت
Set-Location -Path $PSScriptRoot

# ─── پیدا کردن Python ───
$PythonCmd = $null
$candidates = @("py", "python", "python3")

foreach ($cmd in $candidates) {
    try {
        $null = & $cmd --version 2>$null
        if ($LASTEXITCODE -eq 0) {
            # تست واقعی اجرا
            $null = & $cmd -c "import sys; print(sys.version_info[0])" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonCmd = $cmd
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $PythonCmd) {
    Write-Host "❌ Python قابل اجرا پیدا نشد." -ForegroundColor Red
    Write-Host ""
    Write-Host "Python سیستم شما احتمالاً از Microsoft Store نصب شده که" -ForegroundColor Yellow
    Write-Host "دسترسی محدود دارد (خطای Access Denied)." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "راه‌حل:" -ForegroundColor Green
    Write-Host "  ۱) به لینک زیر بروید: https://www.python.org/downloads/" -ForegroundColor Cyan
    Write-Host "  ۲) دکمهٔ سبز «Download Python 3.12» را بزنید"
    Write-Host "  ۳) هنگام نصب تیک ☑ Add Python to PATH را حتماً بزنید"
    Write-Host "  ۴) پس از نصب، این اسکریپت را دوباره اجرا کنید"
    Write-Host ""
    Read-Host "برای بستن Enter را بزنید"
    exit 1
}

# نمایش نسخه
$version = & $PythonCmd --version 2>$null
Write-Host "✓ Python: $version" -ForegroundColor Green

# ─── نصب وابستگی‌ها ───
Write-Host "⚙️  بررسی و نصب وابستگی‌ها..." -ForegroundColor Yellow
& $PythonCmd -m pip install --user --quiet flask requests 2>$null
if ($LASTEXITCODE -ne 0) {
    & $PythonCmd -m pip install --quiet flask requests 2>$null
}
Write-Host "✓ وابستگی‌ها آماده‌اند" -ForegroundColor Green
Write-Host ""

# ─── باز کردن مرورگر در پس‌زمینه ───
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 3
    Start-Process "http://127.0.0.1:5000"
} | Out-Null

# ─── اجرای پروکسی ───
Write-Host "🚀 اجرای پروکسی روی پورت 5000..." -ForegroundColor Yellow
Write-Host "    آدرس سامانه: http://127.0.0.1:5000" -ForegroundColor Cyan
Write-Host "    برای توقف: Ctrl+C" -ForegroundColor Cyan
Write-Host ""

$env:PORT = "5000"
try {
    & $PythonCmd "$PSScriptRoot\proxy.py"
} catch {
    Write-Host ""
    Write-Host "❌ خطا در اجرای پروکسی: $_" -ForegroundColor Red
}

Write-Host ""
Read-Host "برای بستن Enter را بزنید"
