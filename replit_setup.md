# 🚀 نشر البوت على Replit (مجاني)

## خطوات سريعة:

### 1. إنشاء Repl جديد:
- اذهب إلى replit.com
- اختر "Create Repl"
- اختر "Python"
- اختر "Import from GitHub"

### 2. رفع الكود:
```bash
git clone [your-github-repo]
# أو رفع الملفات مباشرة
```

### 3. تثبيت المتطلبات:
```bash
pip install -r requirements.txt
```

### 4. إعداد المتغيرات (Secrets):
- في لوحة Replit
- اذهب إلى "Secrets"
- أضف:
  - BOT_TOKEN
  - API_ID  
  - API_HASH
  - OWNER_ID

### 5. إعداد Always On:
```python
# main.py
import khayal
# سيبقى البوت يعمل

# أو أضف هذا الكود لإبقائه نشط:
from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    # ثم شغل البوت
    exec(open('khayal.py').read())
```

### 6. تشغيل مستمر:
- اشترك في Replit Hacker Plan (5$/شهر)
- أو استخدم UptimeRobot مجاناً لإبقاء البوت نشط