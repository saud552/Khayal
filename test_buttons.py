#!/usr/bin/env python3
"""
ملف اختبار شامل لفحص أزرار البوت
"""

import sys
import os
import logging

# إضافة المجلد الرئيسي
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """اختبار استيراد جميع الوحدات"""
    tests = []
    
    # اختبار استيراد khayal.py
    try:
        import khayal
        tests.append(("✅", "khayal.py", "تم الاستيراد بنجاح"))
    except Exception as e:
        tests.append(("❌", "khayal.py", f"خطأ: {e}"))
    
    # اختبار استيراد config.py
    try:
        import config
        tests.append(("✅", "config.py", "تم الاستيراد بنجاح"))
    except Exception as e:
        tests.append(("❌", "config.py", f"خطأ: {e}"))
    
    # اختبار استيراد ملفات التقارير
    report_files = [
        "Telegram.report_peer",
        "Telegram.report_message", 
        "Telegram.report_photo",
        "Telegram.report_sponsored",
        "Telegram.report_mass",
        "Telegram.report_bot_messages"
    ]
    
    for module in report_files:
        try:
            __import__(module)
            tests.append(("✅", module, "تم الاستيراد بنجاح"))
        except Exception as e:
            tests.append(("❌", module, f"خطأ: {e}"))
    
    # اختبار استيراد البريد الإلكتروني
    try:
        from Email import email_reports
        tests.append(("✅", "Email.email_reports", "تم الاستيراد بنجاح"))
    except Exception as e:
        tests.append(("❌", "Email.email_reports", f"خطأ: {e}"))
    
    # اختبار استيراد الدعم
    try:
        from Telegram import support_module
        tests.append(("✅", "Telegram.support_module", "تم الاستيراد بنجاح"))
    except Exception as e:
        tests.append(("❌", "Telegram.support_module", f"خطأ: {e}"))
    
    return tests

def test_database():
    """اختبار قاعدة البيانات"""
    try:
        from add import init_db
        from Telegram.common import get_categories
        init_db()
        categories = get_categories()
        return ("✅", "قاعدة البيانات", f"تعمل بنجاح - {len(categories)} فئة")
    except Exception as e:
        return ("❌", "قاعدة البيانات", f"خطأ: {e}")

def test_handlers():
    """اختبار المعالجات"""
    tests = []
    
    try:
        import khayal
        
        # اختبار وجود المعالجات الأساسية
        handlers = [
            "start",
            "show_telegram_menu", 
            "start_proxy_setup",
            "handle_email_reports",
            "handle_special_support",
            "handle_method_selection"
        ]
        
        for handler in handlers:
            if hasattr(khayal, handler):
                tests.append(("✅", f"معالج {handler}", "موجود"))
            else:
                tests.append(("❌", f"معالج {handler}", "مفقود"))
                
    except Exception as e:
        tests.append(("❌", "المعالجات", f"خطأ: {e}"))
    
    return tests

def main():
    """تشغيل جميع الاختبارات"""
    print("🔍 بدء فحص شامل لأزرار البوت...")
    print("=" * 60)
    
    # اختبار الاستيراد
    print("\n📦 اختبار استيراد الوحدات:")
    import_tests = test_imports()
    for status, module, message in import_tests:
        print(f"{status} {module}: {message}")
    
    # اختبار قاعدة البيانات
    print("\n🗃️ اختبار قاعدة البيانات:")
    db_test = test_database()
    print(f"{db_test[0]} {db_test[1]}: {db_test[2]}")
    
    # اختبار المعالجات
    print("\n⚙️ اختبار المعالجات:")
    handler_tests = test_handlers()
    for status, handler, message in handler_tests:
        print(f"{status} {handler}: {message}")
    
    # إحصائيات
    all_tests = import_tests + [db_test] + handler_tests
    passed = len([t for t in all_tests if t[0] == "✅"])
    failed = len([t for t in all_tests if t[0] == "❌"])
    
    print("\n" + "=" * 60)
    print(f"📊 النتائج: {passed} نجح، {failed} فشل")
    
    if failed == 0:
        print("🎉 جميع الاختبارات نجحت! البوت جاهز للعمل.")
        return True
    else:
        print("⚠️ هناك مشاكل تحتاج إصلاح.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)