#!/usr/bin/env python3
"""
سكريبت مراقبة البوت في الوقت الفعلي
"""

import time
import subprocess
import os
import signal

def check_bot_status():
    """التحقق من حالة البوت"""
    try:
        result = subprocess.run(['pgrep', '-f', 'python3 khayal.py'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            pid = result.stdout.strip()
            return True, pid
        return False, None
    except:
        return False, None

def get_recent_logs(num_lines=10):
    """جلب آخر السجلات"""
    try:
        with open('/workspace/bot.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return lines[-num_lines:] if len(lines) >= num_lines else lines
    except:
        return []

def monitor_loop():
    """حلقة المراقبة الرئيسية"""
    print("🤖 بدء مراقبة البوت...")
    print("=" * 50)
    
    while True:
        try:
            # التحقق من حالة البوت
            is_running, pid = check_bot_status()
            
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            
            if is_running:
                print(f"[{timestamp}] ✅ البوت يعمل (PID: {pid})")
            else:
                print(f"[{timestamp}] ❌ البوت متوقف!")
                
            # عرض آخر السجلات
            recent_logs = get_recent_logs(3)
            if recent_logs:
                print("📋 آخر السجلات:")
                for log in recent_logs:
                    if log.strip():
                        print(f"   {log.strip()}")
            
            print("-" * 30)
            time.sleep(30)  # فحص كل 30 ثانية
            
        except KeyboardInterrupt:
            print("\n🛑 تم إيقاف المراقبة")
            break
        except Exception as e:
            print(f"❌ خطأ في المراقبة: {e}")
            time.sleep(10)

if __name__ == "__main__":
    monitor_loop()