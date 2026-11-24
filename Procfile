# Procfile برای پلتفرم‌های سازگار با Heroku (Railway, Render, etc.)
# اگر render.yaml موجود است، Render از آن استفاده می‌کند.
# این فایل برای سازگاری با سایر پلتفرم‌ها نگه داشته شده است.
web: gunicorn proxy:app --workers 1 --threads 8 --timeout 120 --preload --bind 0.0.0.0:${PORT:-5000}
