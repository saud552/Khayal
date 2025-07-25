#!/usr/bin/env python3
"""
اختبار بسيط لمحاكاة النقر اليدوي على البروكسي
"""

import asyncio
import time
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate
import logging

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إعدادات ثابتة
API_ID = 2040
API_HASH = 'b18441a1ff607e10fd989dcf492e8426'

def parse_proxy_simple(proxy_url):
    """تحليل بسيط لرابط البروكسي"""
    try:
        if "t.me/proxy" not in proxy_url:
            return None
            
        # استخراج المعاملات
        server = None
        port = None
        secret = None
        
        parts = proxy_url.split('?')[1] if '?' in proxy_url else ""
        params = dict(param.split('=') for param in parts.split('&') if '=' in param)
        
        server = params.get('server')
        port = int(params.get('port', 443))
        secret = params.get('secret')
        
        if server and secret:
            return {
                'server': server,
                'port': port,
                'secret': secret
            }
        return None
    except Exception as e:
        logger.error(f"خطأ في التحليل: {e}")
        return None

async def test_proxy_realistic(session_str, proxy_url):
    """اختبار البروكسي بطريقة واقعية أكثر"""
    logger.info(f"🔍 اختبار البروكسي: {proxy_url}")
    
    # تحليل البروكسي
    proxy_info = parse_proxy_simple(proxy_url)
    if not proxy_info:
        logger.error("❌ فشل في تحليل البروكسي")
        return False
    
    logger.info(f"📡 معلومات البروكسي: {proxy_info['server']}:{proxy_info['port']}")
    
    # اختبار الاتصال المباشر أولاً
    logger.info("1️⃣ اختبار الاتصال المباشر...")
    direct_client = TelegramClient(
        StringSession(session_str),
        API_ID,
        API_HASH,
        device_model='iPhone',  # تغيير نوع الجهاز
        system_version='iOS 15',
        app_version='8.8.0',
        lang_code='ar'  # تغيير اللغة
    )
    
    try:
        await direct_client.connect()
        if not await direct_client.is_user_authorized():
            logger.error("❌ الجلسة غير صالحة")
            return False
        
        me = await direct_client.get_me()
        logger.info(f"✅ الاتصال المباشر نجح: {me.first_name}")
        await direct_client.disconnect()
        
    except Exception as e:
        logger.error(f"❌ فشل الاتصال المباشر: {e}")
        return False
    
    # الآن اختبار البروكسي مع إعدادات مختلفة
    logger.info("2️⃣ اختبار البروكسي بطرق مختلفة...")
    
    # طريقة 1: استخدام إعدادات أساسية
    try:
        logger.info("   📱 المحاولة 1: إعدادات iPhone...")
        proxy_client = TelegramClient(
            StringSession(session_str),
            API_ID,
            API_HASH,
            connection=ConnectionTcpMTProxyRandomizedIntermediate,
            proxy=(proxy_info["server"], proxy_info["port"], proxy_info["secret"]),
            device_model='iPhone 12',
            system_version='iOS 15.0',
            app_version='8.8.0',
            lang_code='ar',
            timeout=30,
            connection_retries=2,
            auto_reconnect=False
        )
        
        await asyncio.wait_for(proxy_client.connect(), timeout=25)
        
        if await proxy_client.is_user_authorized():
            me = await proxy_client.get_me()
            logger.info(f"✅ نجح مع iPhone: {me.first_name}")
            await proxy_client.disconnect()
            return True
        else:
            logger.warning("⚠️ الاتصال نجح لكن التفويض فشل")
            
        await proxy_client.disconnect()
        
    except Exception as e:
        logger.warning(f"⚠️ فشل مع iPhone: {e}")
    
    # طريقة 2: استخدام إعدادات Android
    try:
        logger.info("   🤖 المحاولة 2: إعدادات Android...")
        await asyncio.sleep(3)  # تأخير بين المحاولات
        
        proxy_client2 = TelegramClient(
            StringSession(session_str),
            API_ID,
            API_HASH,
            connection=ConnectionTcpMTProxyRandomizedIntermediate,
            proxy=(proxy_info["server"], proxy_info["port"], proxy_info["secret"]),
            device_model='Samsung Galaxy S21',
            system_version='Android 11',
            app_version='7.9.0',
            lang_code='en',
            timeout=25,
            connection_retries=1,
            auto_reconnect=False
        )
        
        await asyncio.wait_for(proxy_client2.connect(), timeout=20)
        
        if await proxy_client2.is_user_authorized():
            me = await proxy_client2.get_me()
            logger.info(f"✅ نجح مع Android: {me.first_name}")
            await proxy_client2.disconnect()
            return True
            
        await proxy_client2.disconnect()
        
    except Exception as e:
        logger.warning(f"⚠️ فشل مع Android: {e}")
    
    # طريقة 3: استخدام إعدادات Desktop
    try:
        logger.info("   🖥️ المحاولة 3: إعدادات Desktop...")
        await asyncio.sleep(3)
        
        proxy_client3 = TelegramClient(
            StringSession(session_str),
            API_ID,
            API_HASH,
            connection=ConnectionTcpMTProxyRandomizedIntermediate,
            proxy=(proxy_info["server"], proxy_info["port"], proxy_info["secret"]),
            device_model='PC 64bit',
            system_version='Windows 10',
            app_version='3.0.0',
            lang_code='en',
            timeout=20,
            connection_retries=1
        )
        
        await asyncio.wait_for(proxy_client3.connect(), timeout=15)
        
        if await proxy_client3.is_user_authorized():
            me = await proxy_client3.get_me()
            logger.info(f"✅ نجح مع Desktop: {me.first_name}")
            await proxy_client3.disconnect()
            return True
            
        await proxy_client3.disconnect()
        
    except Exception as e:
        logger.warning(f"⚠️ فشل مع Desktop: {e}")
    
    logger.error("❌ فشل البروكسي مع جميع الطرق")
    return False

async def main():
    """الاختبار الرئيسي"""
    print("🧪 اختبار البروكسي المحسن")
    print("=" * 40)
    
    # قراءة الجلسة الأولى من قاعدة البيانات
    import sqlite3
    try:
        conn = sqlite3.connect('accounts.db')
        cursor = conn.cursor()
        cursor.execute("SELECT session FROM accounts WHERE session IS NOT NULL AND session != '' LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            print("❌ لا توجد جلسات في قاعدة البيانات")
            return
            
        session_str = result[0]
        print(f"✅ تم العثور على جلسة (طولها: {len(session_str)} حرف)")
        
    except Exception as e:
        print(f"❌ خطأ في قراءة قاعدة البيانات: {e}")
        return
    
    # روابط البروكسي للاختبار (ضع هنا الروابط التي تعمل يدوياً)
    test_links = [
        # ضع الروابط هنا
        "https://t.me/proxy?server=87.248.134.12&port=70&secret=ee6ae98613b1e1067a00c8926b6a7e8b",
    ]
    
    if not test_links[0].startswith("https://"):
        print("⚠️ ضع روابط البروكسي في المتغير test_links")
        return
    
    for i, link in enumerate(test_links, 1):
        print(f"\n🔍 اختبار البروكسي {i}/{len(test_links)}")
        print(f"🔗 الرابط: {link}")
        
        success = await test_proxy_realistic(session_str, link)
        
        if success:
            print(f"✅ البروكسي {i} يعمل!")
        else:
            print(f"❌ البروكسي {i} لا يعمل")
        
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())