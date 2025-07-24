# DrKhayal/Telegram/common_improved.py - نظام معالجة محسن مع فحص البروكسي المتقدم

import asyncio
import sqlite3
import base64
import logging
import time
import random
import re
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Union, Any
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass

# مكتبات Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes, ConversationHandler

from telethon import TelegramClient, functions, types, utils
from telethon.errors import (
    AuthKeyDuplicatedError,
    FloodWaitError,
    PeerFloodError,
    SessionPasswordNeededError,
    RPCError,
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    SessionExpiredError,
    TimeoutError as TelethonTimeoutError,
    NetworkMigrateError
)
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate
from telethon.sessions import StringSession

# استيراد الوحدات المحلية
try:
    from encryption import decrypt_session
    from config import API_ID, API_HASH, DB_PATH
    from config_enhanced import enhanced_config
    from add import safe_db_query
except ImportError as e:
    logging.warning(f"فشل استيراد بعض الوحدات: {e}")
    # قيم افتراضية في حالة فشل الاستيراد
    API_ID = 26924046
    API_HASH = "4c6ef4cee5e129b7a674de156e2bcc15"
    DB_PATH = 'accounts.db'

# إعداد المسجل
logger = logging.getLogger(__name__)
detailed_logger = logging.getLogger('detailed_proxy')

# إعداد مسجل مفصل للبروكسي
if not detailed_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    detailed_logger.addHandler(handler)
    detailed_logger.setLevel(logging.DEBUG)

# === الثوابت المحسنة ===
PROXY_CHECK_TIMEOUT = getattr(enhanced_config.proxy if 'enhanced_config' in globals() else None, 'check_timeout', 25)
PROXY_RECHECK_INTERVAL = getattr(enhanced_config.proxy if 'enhanced_config' in globals() else None, 'recheck_interval', 3000)
MAX_PROXY_RETRIES = getattr(enhanced_config.proxy if 'enhanced_config' in globals() else None, 'max_retries', 30)
CONCURRENT_PROXY_CHECKS = getattr(enhanced_config.proxy if 'enhanced_config' in globals() else None, 'concurrent_checks', 3)
REPORT_CONFIRMATION_TIMEOUT = 10  # ثانية للتأكيد
MAX_REPORTS_PER_SESSION = 1000000  # الحد الأقصى للبلاغات لكل جلسة

# أنواع التقارير المحسنة
REPORT_TYPES_ENHANCED = {
    2: ("رسائل مزعجة", types.InputReportReasonSpam()),
    3: ("إساءة أطفال", types.InputReportReasonChildAbuse()),
    4: ("محتوى جنسي", types.InputReportReasonPornography()),
    5: ("عنف", types.InputReportReasonViolence()),
    6: ("انتهاك خصوصية", types.InputReportReasonPersonalDetails()),
    7: ("مخدرات", types.InputReportReasonIllegalDrugs()),
    8: ("حساب مزيف", types.InputReportReasonFake()),
    9: ("حقوق النشر", types.InputReportReasonCopyright()),
    11: ("أخرى", types.InputReportReasonOther()),
}

# === استثناءات مخصصة محسنة ===
class ProxyTestFailed(Exception):
    """استثناء خاص بفشل اختبار البروكسي"""
    pass

class ProxyConnectionFailed(Exception):
    """استثناء خاص بفشل الاتصال بالبروكسي"""
    pass

class ProxyTimeoutError(Exception):
    """استثناء خاص بانتهاء مهلة البروكسي"""
    pass

class SessionValidationError(Exception):
    """استثناء خاص بفشل التحقق من الجلسة"""
    pass

@dataclass
class ProxyStats:
    """إحصائيات البروكسي المفصلة"""
    server: str
    port: int
    ping: int = 0
    response_time: int = 0
    quality_score: int = 0
    last_check: int = 0
    success_rate: float = 0.0
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    last_error: Optional[str] = None
    
    def update_stats(self, success: bool, ping: int = 0, response_time: int = 0, error: str = None):
        """تحديث إحصائيات البروكسي"""
        self.total_checks += 1
        self.last_check = int(time.time())
        
        if success:
            self.successful_checks += 1
            self.ping = ping
            self.response_time = response_time
            self.last_error = None
            
            # حساب نقاط الجودة بناءً على الأداء
            self.quality_score = min(100, max(0, 100 - (ping // 50) - (response_time // 100)))
        else:
            self.failed_checks += 1
            self.last_error = error
            self.quality_score = max(0, self.quality_score - 10)
        
        # حساب معدل النجاح
        self.success_rate = (self.successful_checks / self.total_checks) * 100

class EnhancedProxyChecker:
    """نظام فحص بروكسي محسن مع تتبع مفصل وتحقق حقيقي"""
    
    def __init__(self):
        self.proxy_stats: Dict[str, ProxyStats] = {}
        self.failed_proxies = set()
        self.last_check_times = {}
        self.concurrent_checks = CONCURRENT_PROXY_CHECKS
        self.active_connections = {}
        self.proxy_blacklist = set()
        
    def _get_proxy_key(self, proxy_info: dict) -> str:
        """إنشاء مفتاح فريد للبروكسي"""
        return f"{proxy_info['server']}:{proxy_info['port']}"
    
    def _is_proxy_blacklisted(self, proxy_info: dict) -> bool:
        """فحص إذا كان البروكسي في القائمة السوداء"""
        proxy_key = self._get_proxy_key(proxy_info)
        return proxy_key in self.proxy_blacklist
    
    def _blacklist_proxy(self, proxy_info: dict, reason: str):
        """إضافة البروكسي للقائمة السوداء"""
        proxy_key = self._get_proxy_key(proxy_info)
        self.proxy_blacklist.add(proxy_key)
        detailed_logger.warning(f"⚫ تم إضافة البروكسي للقائمة السوداء: {proxy_key} - السبب: {reason}")
        
    async def deep_proxy_test(self, session_str: str, proxy_info: dict) -> dict:
        """اختبار عميق للبروكسي مع فحوصات متعددة محسنة"""
        proxy_key = self._get_proxy_key(proxy_info)
        result = proxy_info.copy()
        client = None
        
        # فحص القائمة السوداء أولاً
        if self._is_proxy_blacklisted(proxy_info):
            result.update({
                "status": "blacklisted",
                "ping": 0,
                "response_time": 0,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": "البروكسي في القائمة السوداء"
            })
            return result
        
        # الحصول على إحصائيات البروكسي أو إنشاؤها
        if proxy_key not in self.proxy_stats:
            self.proxy_stats[proxy_key] = ProxyStats(
                server=proxy_info["server"],
                port=proxy_info["port"]
            )
        
        stats = self.proxy_stats[proxy_key]
        
        try:
            # إعداد العميل مع timeout صارم ومعلمات محسنة
            params = {
                "api_id": API_ID,
                "api_hash": API_HASH,
                "timeout": PROXY_CHECK_TIMEOUT,
                "connection": ConnectionTcpMTProxyRandomizedIntermediate,
                "device_model": f"ProxyBot-{uuid.uuid4().hex[:8]}",
                "system_version": "Android 10",
                "app_version": "1.0.0",
                "lang_code": "ar",
                "auto_reconnect": False,
                "connection_retries": 1,
                "retry_delay": 1
            }
            
            # تحضير السر مع معالجة أفضل للأخطاء وتتبع مفصل
            secret = proxy_info["secret"]
            detailed_logger.debug(f"🔍 معالجة السر: نوع={type(secret)}, قيمة={str(secret)[:30]}...")
            
            # معالجة شاملة لأنواع الأسرار المختلفة
            if isinstance(secret, bytes):
                # السر موجود كـ bytes بالفعل
                detailed_logger.debug("السر هو bytes بالفعل")
                secret_bytes = secret
            elif isinstance(secret, str):
                try:
                    # التحقق من صحة تنسيق السر
                    if len(secret) < 32 or len(secret) % 2 != 0:
                        raise ValueError("طول السر غير صالح")
                    detailed_logger.debug(f"تحويل السر من str إلى bytes: {len(secret)} حرف")
                    secret_bytes = bytes.fromhex(secret)
                    detailed_logger.debug(f"✅ تم التحويل بنجاح: {len(secret_bytes)} بايت")
                except ValueError as e:
                    detailed_logger.error(f"❌ فشل تحويل السر: {e}")
                    self._blacklist_proxy(proxy_info, f"سر غير صالح: {e}")
                    raise ProxyTestFailed(f"سر غير صالح: {secret}")
            else:
                # نوع غير متوقع، محاولة تحويل
                detailed_logger.warning(f"⚠️ نوع سر غير متوقع: {type(secret)}")
                try:
                    secret_str = str(secret)
                    secret_bytes = bytes.fromhex(secret_str)
                except Exception as e:
                    detailed_logger.error(f"❌ فشل تحويل السر غير المتوقع: {e}")
                    self._blacklist_proxy(proxy_info, f"نوع سر غير مدعوم: {type(secret)}")
                    raise ProxyTestFailed(f"نوع سر غير مدعوم: {type(secret)}")
            
            # تحويل secret_bytes إلى hex string للمكتبة Telethon
            secret_hex = secret_bytes.hex() if isinstance(secret_bytes, bytes) else secret_bytes
            detailed_logger.debug(f"🔍 نوع secret_bytes: {type(secret_bytes)}, نوع secret_hex: {type(secret_hex)}")
            detailed_logger.debug(f"🔧 إعداد البروكسي: server={proxy_info['server']}, port={proxy_info['port']}, secret_type={type(secret_hex)}")
            params["proxy"] = (
                proxy_info["server"],
                proxy_info["port"],
                secret_hex  # استخدام hex string بدلاً من bytes
            )
            
            # اختبار الاتصال الأولي مع قياس الوقت
            start_time = time.time()
            client = TelegramClient(StringSession(session_str), **params)
            
            # اختبار الاتصال مع timeout محدود
            try:
                await asyncio.wait_for(client.connect(), timeout=PROXY_CHECK_TIMEOUT)
                connection_time = time.time() - start_time
            except asyncio.TimeoutError:
                raise ProxyTimeoutError("انتهت مهلة الاتصال")
            except (ConnectionError, OSError, NetworkMigrateError):
                raise ProxyConnectionFailed("فشل الاتصال بالبروكسي")
            
            # التحقق من التفويض
            if not await client.is_user_authorized():
                raise SessionValidationError("الجلسة غير مفوضة")
            
            # اختبار سرعة الاستجابة
            response_start = time.time()
            try:
                me = await asyncio.wait_for(client.get_me(), timeout=PROXY_CHECK_TIMEOUT // 2)
                response_time = time.time() - response_start
            except asyncio.TimeoutError:
                raise ProxyTimeoutError("انتهت مهلة الاستجابة")
            
            # اختبار إضافي: جلب بعض الحوارات
            dialogs_start = time.time()
            dialog_count = 0
            try:
                async for dialog in client.iter_dialogs(limit=3):
                    dialog_count += 1
                    if dialog_count >= 3:
                        break
                dialogs_time = time.time() - dialogs_start
            except Exception:
                dialogs_time = 999  # قيمة عالية تشير لمشكلة
            
            # تقييم جودة البروكسي بطريقة محسنة
            ping = int(connection_time * 1000)
            responsiveness = int(response_time * 1000)
            dialogs_ms = int(dialogs_time * 1000)
            
            # حساب نقاط الجودة بناءً على عوامل متعددة
            quality_score = 100
            
            # تقليل النقاط بناءً على ping
            if ping > 5000:
                quality_score -= 40
            elif ping > 3000:
                quality_score -= 25
            elif ping > 1500:
                quality_score -= 10
            
            # تقليل النقاط بناءً على سرعة الاستجابة
            if responsiveness > 3000:
                quality_score -= 30
            elif responsiveness > 2000:
                quality_score -= 15
            elif responsiveness > 1000:
                quality_score -= 5
            
            # تقليل النقاط بناءً على سرعة جلب الحوارات
            if dialogs_ms > 5000:
                quality_score -= 20
            elif dialogs_ms > 3000:
                quality_score -= 10
            
            # إضافة مكافأة للبروكسيات المستقرة
            if stats.success_rate > 80:
                quality_score += 10
            
            quality_score = max(0, min(100, quality_score))
            
            # تحديث النتيجة
            result.update({
                "status": "active",
                "ping": ping,
                "response_time": responsiveness,
                "dialogs_time": dialogs_ms,
                "quality_score": quality_score,
                "last_check": int(time.time()),
                "user_id": me.id,
                "connection_successful": True,
                "error": None,
                "stability_score": stats.success_rate
            })
            
            # تحديث الإحصائيات
            stats.update_stats(True, ping, responsiveness)
            
            detailed_logger.info(f"✅ بروكسي نشط: {proxy_info['server']} - ping: {ping}ms - استجابة: {responsiveness}ms - جودة: {quality_score}%")
            
        except (ProxyTimeoutError, asyncio.TimeoutError):
            error_msg = "انتهت مهلة الاتصال"
            result.update({
                "status": "timeout",
                "ping": 9999,
                "response_time": 9999,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": error_msg
            })
            stats.update_stats(False, error=error_msg)
            self.failed_proxies.add(proxy_info["server"])
            
            # إضافة للقائمة السوداء بعد فشل متكرر
            if stats.failed_checks >= 3 and stats.success_rate < 10:
                self._blacklist_proxy(proxy_info, "فشل متكرر في الاتصال")
            
        except (ProxyTestFailed, ProxyConnectionFailed, SessionValidationError) as e:
            error_msg = str(e)
            result.update({
                "status": "failed",
                "ping": 0,
                "response_time": 0,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": error_msg
            })
            stats.update_stats(False, error=error_msg)
            self.failed_proxies.add(proxy_info["server"])
            
        except Exception as e:
            error_msg = f"خطأ غير متوقع: {str(e)}"
            result.update({
                "status": "error",
                "ping": 0,
                "response_time": 0,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": error_msg
            })
            stats.update_stats(False, error=error_msg)
            logger.error(f"خطأ في فحص البروكسي {proxy_info['server']}: {e}")
            # إضافة تتبع كامل للخطأ للتشخيص
            import traceback
            logger.error(f"تتبع الخطأ الكامل:\n{traceback.format_exc()}")
            
        finally:
            if client and client.is_connected():
                try:
                    await asyncio.wait_for(client.disconnect(), timeout=5)
                except:
                    pass
                    
        return result
    
    async def batch_check_proxies(self, session_str: str, proxies: List[dict]) -> List[dict]:
        """فحص مجموعة من البروكسيات بشكل متوازي مع تحسينات الأداء"""
        if not proxies:
            return []
        
        # تصفية البروكسيات المكررة
        unique_proxies = {}
        for proxy in proxies:
            key = self._get_proxy_key(proxy)
            if key not in unique_proxies:
                unique_proxies[key] = proxy
        
        filtered_proxies = list(unique_proxies.values())
        detailed_logger.info(f"🔍 بدء فحص {len(filtered_proxies)} بروكسي (تم إزالة {len(proxies) - len(filtered_proxies)} مكرر)")
        
        # استخدام semaphore للتحكم في عدد الفحوصات المتزامنة
        semaphore = asyncio.Semaphore(self.concurrent_checks)
        
        async def check_single_with_retry(proxy):
            proxy_key = self._get_proxy_key(proxy)
            retry_count = 0
            max_retries = 2
            
            async with semaphore:
                while retry_count <= max_retries:
                    try:
                        result = await self.deep_proxy_test(session_str, proxy)
                        
                        # إذا نجح الاختبار، قم بإرجاع النتيجة
                        if result.get('status') == 'active':
                            return result
                        
                        # إذا فشل ولكن ليس بسبب مشكلة دائمة، حاول مرة أخرى
                        if result.get('status') in ['timeout', 'error'] and retry_count < max_retries:
                            retry_count += 1
                            detailed_logger.debug(f"🔄 إعادة محاولة {retry_count}/{max_retries} للبروكسي {proxy_key}")
                            await asyncio.sleep(1)  # انتظار قصير قبل إعادة المحاولة
                            continue
                        
                        return result
                        
                    except Exception as e:
                        retry_count += 1
                        if retry_count <= max_retries:
                            detailed_logger.debug(f"🔄 خطأ في فحص {proxy_key}, إعادة محاولة {retry_count}/{max_retries}: {e}")
                            await asyncio.sleep(1)
                        else:
                            detailed_logger.error(f"❌ فشل نهائي في فحص {proxy_key}: {e}")
                            return {
                                **proxy,
                                "status": "error",
                                "error": str(e),
                                "quality_score": 0,
                                "last_check": int(time.time())
                            }
                
                # إذا فشلت جميع المحاولات
                return {
                    **proxy,
                    "status": "failed",
                    "error": "فشل بعد عدة محاولات",
                    "quality_score": 0,
                    "last_check": int(time.time())
                }
        
        # تنفيذ الفحوصات بشكل متوازي
        start_time = time.time()
        tasks = [check_single_with_retry(proxy) for proxy in filtered_proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # معالجة النتائج
        valid_results = []
        successful_count = 0
        failed_count = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"خطأ في فحص البروكسي {filtered_proxies[i]['server']}: {result}")
                error_result = {
                    **filtered_proxies[i],
                    "status": "exception",
                    "error": str(result),
                    "quality_score": 0,
                    "last_check": int(time.time())
                }
                valid_results.append(error_result)
                failed_count += 1
            else:
                valid_results.append(result)
                if result.get('status') == 'active':
                    successful_count += 1
                else:
                    failed_count += 1
        
        # إحصائيات الفحص
        total_time = time.time() - start_time
        detailed_logger.info(f"📊 اكتمل فحص البروكسيات: {successful_count} نشط, {failed_count} فاشل في {total_time:.2f} ثانية")
        
        return valid_results
    
    def get_best_proxies(self, proxies: List[dict], count: int = 5) -> List[dict]:
        """الحصول على أفضل البروكسيات مرتبة حسب الجودة مع معايير محسنة"""
        active_proxies = [p for p in proxies if p.get('status') == 'active']
        
        if not active_proxies:
            detailed_logger.warning("⚠️ لا توجد بروكسيات نشطة متاحة")
            return []
        
        # ترتيب متقدم بناءً على عوامل متعددة
        def calculate_score(proxy):
            quality = proxy.get('quality_score', 0)
            ping = proxy.get('ping', 9999)
            response_time = proxy.get('response_time', 9999)
            stability = proxy.get('stability_score', 0)
            
            # حساب نقاط مركبة
            # جودة عالية + ping منخفض + استجابة سريعة + استقرار عالي
            score = (quality * 0.4) + ((5000 - min(ping, 5000)) / 5000 * 30) + ((3000 - min(response_time, 3000)) / 3000 * 20) + (stability * 0.1)
            return score
        
        sorted_proxies = sorted(active_proxies, key=calculate_score, reverse=True)
        
        best_proxies = sorted_proxies[:count]
        detailed_logger.info(f"🏆 تم اختيار أفضل {len(best_proxies)} بروكسي من أصل {len(active_proxies)}")
        
        return best_proxies
    
    def needs_recheck(self, proxy_info: dict) -> bool:
        """تحديد إذا كان البروكسي يحتاج إعادة فحص"""
        last_check = proxy_info.get('last_check', 0)
        return (time.time() - last_check) > PROXY_RECHECK_INTERVAL
    
    def get_proxy_statistics(self) -> Dict:
        """الحصول على إحصائيات شاملة للبروكسيات"""
        stats = {
            "total_tested": len(self.proxy_stats),
            "blacklisted": len(self.proxy_blacklist),
            "failed_proxies": len(self.failed_proxies),
            "avg_ping": 0,
            "avg_quality": 0,
            "stability_distribution": {"high": 0, "medium": 0, "low": 0}
        }
        
        if self.proxy_stats:
            pings = [s.ping for s in self.proxy_stats.values() if s.ping > 0]
            qualities = [s.quality_score for s in self.proxy_stats.values()]
            
            stats["avg_ping"] = sum(pings) / len(pings) if pings else 0
            stats["avg_quality"] = sum(qualities) / len(qualities) if qualities else 0
            
            # توزيع الاستقرار
            for proxy_stat in self.proxy_stats.values():
                if proxy_stat.success_rate > 80:
                    stats["stability_distribution"]["high"] += 1
                elif proxy_stat.success_rate > 50:
                    stats["stability_distribution"]["medium"] += 1
                else:
                    stats["stability_distribution"]["low"] += 1
        
        return stats
    
    def cleanup_old_stats(self, max_age_hours: int = 24):
        """تنظيف الإحصائيات القديمة"""
        current_time = time.time()
        cutoff_time = current_time - (max_age_hours * 3600)
        
        old_proxies = [
            key for key, stats in self.proxy_stats.items()
            if stats.last_check < cutoff_time
        ]
        
        for key in old_proxies:
            del self.proxy_stats[key]
        
        if old_proxies:
            detailed_logger.info(f"🧹 تم تنظيف {len(old_proxies)} إحصائية قديمة للبروكسي")

class VerifiedReporter:
    """نظام إبلاغ محسن مع تأكيد الإرسال والتحقق من النجاح"""
    
    def __init__(self, client: TelegramClient, context: ContextTypes.DEFAULT_TYPE):
        self.client = client
        self.context = context
        self.stats = {
            "success": 0,
            "failed": 0,
            "confirmed": 0,
            "unconfirmed": 0,
            "last_report": None,
            "report_ids": []
        }
        self.session_reports_count = 0
        self.last_activity = time.time()
        
    async def verify_report_success(self, report_result: Any, target: str, report_type: str) -> bool:
        """التحقق من نجاح البلاغ الفعلي"""
        try:
            # تحليل نتيجة البلاغ
            if isinstance(report_result, types.ReportResultAddComment):
                detailed_logger.info(f"✅ تم قبول البلاغ مع طلب تعليق - الهدف: {target}")
                return True
                
            elif isinstance(report_result, types.ReportResultChooseOption):
                detailed_logger.info(f"✅ تم قبول البلاغ مع خيارات - الهدف: {target}")
                return True
                
            elif hasattr(report_result, 'success') and report_result.success:
                detailed_logger.info(f"✅ تم قبول البلاغ بنجاح - الهدف: {target}")
                return True
                
            # إذا كانت النتيجة True أو None (نجاح ضمني)
            elif report_result is True or report_result is None:
                detailed_logger.info(f"✅ تم إرسال البلاغ (نجاح ضمني) - الهدف: {target}")
                return True
                
            else:
                detailed_logger.warning(f"⚠️ نتيجة غير مؤكدة للبلاغ - الهدف: {target} - النتيجة: {type(report_result)}")
                return False
                
        except Exception as e:
            detailed_logger.error(f"❌ خطأ في التحقق من البلاغ - الهدف: {target} - الخطأ: {e}")
            return False
    
    async def intelligent_delay(self, base_delay: float):
        """تأخير ذكي يتكيف مع نشاط الحساب"""
        if self.stats["last_report"]:
            elapsed = time.time() - self.stats["last_report"]
            
            # تقليل التأخير إذا مر وقت كافي
            if elapsed > 60:  # إذا مر أكثر من دقيقة
                adjusted_delay = base_delay * 0.5
            elif elapsed > 30:  # إذا مر أكثر من 30 ثانية
                adjusted_delay = base_delay * 0.7
            else:
                adjusted_delay = base_delay
                
            # إضافة عشوائية للتنويع
            randomized_delay = adjusted_delay + random.uniform(0, adjusted_delay * 0.3)
            
            if elapsed < randomized_delay:
                wait_time = randomized_delay - elapsed
                detailed_logger.info(f"⏳ تأخير ذكي: {wait_time:.1f} ثانية")
                await asyncio.sleep(wait_time)
                
        self.stats["last_report"] = time.time()
        self.last_activity = time.time()
    
    async def resolve_target_enhanced(self, target: Any) -> dict | None:
        """حل الهدف مع معلومات إضافية للتتبع"""
        try:
            target_info = {"original": target, "resolved": None, "type": None}
            
            # الحالة 1: الهدف هو قاموس (نتيجة من parse_message_link)
            if isinstance(target, dict) and 'channel' in target and 'message_id' in target:
                try:
                    # التحقق من نوع الكائن المُمرر
                    channel_ref = target['channel']
                    
                    # إذا كان كائن Telethon، استخدمه مباشرة
                    if hasattr(channel_ref, 'id') and hasattr(channel_ref, '__class__'):
                        entity = channel_ref
                    # إذا كان معرف رقمي
                    elif isinstance(channel_ref, int):
                        entity = await self.client.get_entity(channel_ref)
                    # إذا كان نص (اسم مستخدم)
                    elif isinstance(channel_ref, str):
                        username = channel_ref.lstrip('@')
                        if re.match(r'^[a-zA-Z][\w\d]{3,30}[a-zA-Z\d]$', username):
                            entity = await self.client.get_entity(username)
                        else:
                            # حل كمعرف قناة مباشرة
                            entity = await self.client.get_entity(types.PeerChannel(channel_ref))
                    else:
                        # محاولة أخيرة باستخدام الكائن مباشرة
                        entity = await self.client.get_entity(channel_ref)
                        
                except (ValueError, TypeError, RPCError) as e:
                    # المحاولة الأخيرة: حل باستخدام معرف القناة كرقم
                    try:
                        if hasattr(target['channel'], 'id'):
                            entity = await self.client.get_entity(target['channel'].id)
                        else:
                            entity = await self.client.get_entity(types.PeerChannel(int(target['channel'])))
                    except:
                        raise ValueError(f"فشل في حل القناة: {target['channel']} - {str(e)}")
                
                target_info.update({
                    "resolved": {
                        "channel": utils.get_input_peer(entity),
                        "message_id": target['message_id']
                    },
                    "type": "message",
                    "channel_id": entity.id,
                    "message_id": target['message_id']
                })
                return target_info
                
            # الحالة 2: رابط رسالة
            if isinstance(target, str) and 't.me/' in target:
                # تحليل رابط الرسالة
                parsed = self.parse_message_link(target)
                if parsed:
                    # حل القناة بنفس الطريقة المستخدمة للقاموس
                    return await self.resolve_target_enhanced(parsed)
                
                # رابط قناة أو مستخدم مباشر
                try:
                    entity = await self.client.get_entity(target)
                    target_info.update({
                        "resolved": utils.get_input_peer(entity),
                        "type": "peer",
                        "entity_id": entity.id
                    })
                    return target_info
                except Exception as e:
                    detailed_logger.error(f"❌ فشل في حل الرابط {target}: {e}")
                    return None
            
            # الحالة 3: معرف مستخدم أو قناة مباشر
            try:
                entity = await self.client.get_entity(target)
                target_info.update({
                    "resolved": utils.get_input_peer(entity),
                    "type": "peer",
                    "entity_id": entity.id
                })
                return target_info
            except Exception as e:
                detailed_logger.error(f"❌ فشل في حل الهدف {target}: {e}")
                return None
                
        except Exception as e:
            detailed_logger.error(f"❌ خطأ عام في حل الهدف {target}: {e}")
            return None
    
    def parse_message_link(self, link: str) -> dict | None:
        """تحليل رابط رسالة تليجرام المحسن"""
        try:
            # النمط الأساسي: https://t.me/channel/123
            base_pattern = r"https?://t\.me/([a-zA-Z0-9_]+)/(\d+)"
            match = re.search(base_pattern, link)
            if match:
                return {
                    "channel": match.group(1),
                    "message_id": int(match.group(2))
                }
            
            # النمط مع المعرف الخاص: https://t.me/c/1234567890/123
            private_pattern = r"https?://t\.me/c/(\d+)/(\d+)"
            match = re.search(private_pattern, link)
            if match:
                return {
                    "channel": int(match.group(1)),
                    "message_id": int(match.group(2))
                }
            
            return None
        except Exception as e:
            logger.error(f"خطأ في تحليل رابط الرسالة: {e}")
            return None
    
    async def execute_verified_report(self, target: Any, reason_obj: Any, method_type: str, 
                                    message: str, reports_count: int, cycle_delay: float) -> dict:
        """تنفيذ بلاغ محقق مع تأكيد النجاح"""
        
        # فحص حد البلاغات لكل جلسة
        if self.session_reports_count >= MAX_REPORTS_PER_SESSION:
            raise RateLimitExceeded(f"تم تجاوز الحد الأقصى {MAX_REPORTS_PER_SESSION} بلاغ لكل جلسة")
        
        target_info = await self.resolve_target_enhanced(target)
        if not target_info or not target_info["resolved"]:
            self.stats["failed"] += reports_count
            return {"success": False, "error": "فشل في حل الهدف"}
        
        report_results = []
        
        for i in range(reports_count):
            if not self.context.user_data.get("active", True):
                break
                
            try:
                await self.intelligent_delay(cycle_delay)
                
                # إنشاء معرف فريد للبلاغ
                report_id = hashlib.md5(
                    f"{target}_{method_type}_{time.time()}_{i}".encode()
                ).hexdigest()[:8]
                
                result = None
                
                if method_type == "peer":
                    result = await self.client(functions.account.ReportPeerRequest(
                        peer=target_info["resolved"],
                        reason=reason_obj,
                        message=message
                    ))
                    
                elif method_type == "message":
                    peer = target_info["resolved"]["channel"]
                    msg_id = target_info["resolved"]["message_id"]
                    
                    # خطوة أولى: طلب الخيارات
                    result = await self.client(functions.messages.ReportRequest(
                        peer=peer,
                        id=[msg_id],
                        option=b'',
                        message=''
                    ))
                    
                    # خطوة ثانية: إرسال البلاغ مع الخيار
                    if isinstance(result, types.ReportResultChooseOption) and result.options:
                        chosen_option = result.options[0].option
                        result = await self.client(functions.messages.ReportRequest(
                            peer=peer,
                            id=[msg_id],
                            option=chosen_option,
                            message=message
                        ))
                
                # التحقق من نجاح البلاغ
                verified = await self.verify_report_success(result, str(target), method_type)
                
                if verified:
                    self.stats["success"] += 1
                    self.stats["confirmed"] += 1
                    self.session_reports_count += 1
                    
                    report_info = {
                        "id": report_id,
                        "target": str(target),
                        "method": method_type,
                        "timestamp": time.time(),
                        "verified": True
                    }
                    
                    self.stats["report_ids"].append(report_info)
                    report_results.append(report_info)
                    
                    detailed_logger.info(f"✅ بلاغ محقق #{report_id} - الهدف: {target} - الطريقة: {method_type}")
                    
                else:
                    self.stats["unconfirmed"] += 1
                    detailed_logger.warning(f"⚠️ بلاغ غير محقق - الهدف: {target}")
                    
            except ChatWriteForbiddenError:
                detailed_logger.error(f"❌ ممنوع من الكتابة في الدردشة - الهدف: {target}")
                self.stats["failed"] += 1
                
            except UserBannedInChannelError:
                detailed_logger.error(f"❌ المستخدم محظور في القناة - الهدف: {target}")
                self.stats["failed"] += 1
                
            except MessageIdInvalidError:
                detailed_logger.error(f"❌ معرف رسالة غير صالح - الهدف: {target}")
                self.stats["failed"] += 1
                
            except FloodWaitError as e:
                detailed_logger.warning(f"⏳ حد المعدل: انتظار {e.seconds} ثانية")
                await asyncio.sleep(e.seconds + 1)
                
            except Exception as e:
                detailed_logger.error(f"❌ خطأ في البلاغ - الهدف: {target} - الخطأ: {e}")
                self.stats["failed"] += 1
        
        return {
            "success": len(report_results) > 0,
            "verified_reports": len(report_results),
            "total_attempts": reports_count,
            "report_ids": report_results
        }
    
    # وظيفة جديدة للإبلاغ الجماعي
    async def execute_batch_report(self, targets: List[Any], reason_obj: Any, method_type: str, 
                                 message: str, reports_count: int, cycle_delay: float) -> dict:
        """تنفيذ بلاغ جماعي على جميع الأهداف في نفس الوقت"""
        if self.session_reports_count + (len(targets) * reports_count) > MAX_REPORTS_PER_SESSION:
            raise RateLimitExceeded(f"تم تجاوز الحد الأقصى {MAX_REPORTS_PER_SESSION} بلاغ لكل جلسة")
        
        # حل جميع الأهداف أولاً
        target_infos = []
        for target in targets:
            target_info = await self.resolve_target_enhanced(target)
            if target_info and target_info["resolved"]:
                target_infos.append(target_info)
        
        if not target_infos:
            self.stats["failed"] += len(targets) * reports_count
            return {"success": False, "error": "فشل في حل الأهداف"}
        
        report_results = []
        
        # تنفيذ دورات الإبلاغ
        for rep in range(reports_count):
            if not self.context.user_data.get("active", True):
                break
                
            try:
                # تأخير ذكي بين الدورات
                await self.intelligent_delay(cycle_delay)
                
                # إنشاء مهام للإبلاغ على جميع الأهداف في نفس الوقت
                tasks = []
                for target_info in target_infos:
                    tasks.append(
                        self._report_single_target(target_info, reason_obj, method_type, message)
                    )
                
                # تنفيذ جميع البلاغات بشكل متزامن
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # معالجة النتائج
                for result in results:
                    if isinstance(result, Exception):
                        self.stats["failed"] += 1
                        detailed_logger.error(f"❌ خطأ في البلاغ الجماعي: {result}")
                    elif result.get("verified"):
                        self.stats["success"] += 1
                        self.stats["confirmed"] += 1
                        self.session_reports_count += 1
                        report_results.append(result)
                
            except Exception as e:
                detailed_logger.error(f"❌ خطأ في الدورة الجماعية {rep+1}/{reports_count}: {e}")
        
        return {
            "success": len(report_results) > 0,
            "verified_reports": len(report_results),
            "total_attempts": reports_count * len(targets),
            "report_ids": report_results
        }
    
    # وظيفة مساعدة للبلاغ الفردي
    async def _report_single_target(self, target_info: dict, reason_obj: Any, 
                                  method_type: str, message: str) -> dict:
        """تنفيذ بلاغ على هدف واحد (وظيفة مساعدة)"""
        try:
            # إنشاء معرف فريد للبلاغ
            report_id = hashlib.md5(
                f"{target_info['original']}_{method_type}_{time.time()}".encode()
            ).hexdigest()[:8]
            
            result = None
            
            if method_type == "peer":
                result = await self.client(functions.account.ReportPeerRequest(
                    peer=target_info["resolved"],
                    reason=reason_obj,
                    message=message
                ))
                
            elif method_type == "message":
                peer = target_info["resolved"]["channel"]
                msg_id = target_info["resolved"]["message_id"]
                
                # خطوة أولى: طلب الخيارات
                result = await self.client(functions.messages.ReportRequest(
                    peer=peer,
                    id=[msg_id],
                    option=b'',
                    message=''
                ))
                
                # خطوة ثانية: إرسال البلاغ مع الخيار
                if isinstance(result, types.ReportResultChooseOption) and result.options:
                    chosen_option = result.options[0].option
                    result = await self.client(functions.messages.ReportRequest(
                        peer=peer,
                        id=[msg_id],
                        option=chosen_option,
                        message=message
                    ))
            
            # التحقق من نجاح البلاغ
            verified = await self.verify_report_success(result, str(target_info['original']), method_type)
            
            return {
                "id": report_id,
                "target": str(target_info['original']),
                "method": method_type,
                "timestamp": time.time(),
                "verified": verified
            }
            
        except Exception as e:
            detailed_logger.error(f"❌ خطأ في البلاغ الفردي: {e}")
            raise e

# === دوال مساعدة محسنة ===

def convert_secret_enhanced(secret: str) -> str | None:
    """تحويل سر البروكسي محسن مع دعم جميع الصيغ والتحقق المحسن"""
    if not secret or not isinstance(secret, str):
        return None
    
    secret = secret.strip()
    original_secret = secret
    
    # محاولة 1: فحص الصيغة السداسية المباشرة (بما في ذلك الأحرف الكبيرة)
    hex_only = re.sub(r'[^A-Fa-f0-9]', '', secret)
    if re.fullmatch(r'[A-Fa-f0-9]+', hex_only) and len(hex_only) % 2 == 0:
        if 32 <= len(hex_only) <= 156:  # دعم أسرار أطول للـ MTProto
            detailed_logger.debug(f"✅ سر hex مباشر: {len(hex_only)} حرف")
            return hex_only.lower()
    
    # محاولة 2: base64 عادي مع معالجة شاملة
    base64_attempts = [
        secret,  # كما هو
        secret.replace('_', '/').replace('-', '+'),  # URL-safe base64
        re.sub(r'[^A-Za-z0-9+/=]', '', secret),  # إزالة الرموز الخاصة
    ]
    
    # إضافة محاولات مع إزالة البادئات
    for prefix in ['ee', 'dd', '00', 'ff']:
        if secret.lower().startswith(prefix):
            base64_attempts.extend([
                secret[len(prefix):],
                secret[len(prefix):].replace('_', '/').replace('-', '+'),
                re.sub(r'[^A-Za-z0-9+/=]', '', secret[len(prefix):])
            ])
    
    # تجربة جميع المحاولات
    for attempt_num, test_secret in enumerate(base64_attempts):
        if not test_secret:
            continue
            
        try:
            # إضافة padding إذا لزم الأمر
            padding_needed = 4 - (len(test_secret) % 4)
            if padding_needed != 4:
                test_secret += '=' * padding_needed
            
            # محاولة فك التشفير
            decoded = base64.b64decode(test_secret)
            hex_secret = decoded.hex()
            
            # التحقق من صحة الطول (دعم أسرار مختلفة الأطوال)
            if 32 <= len(hex_secret) <= 320:  # من 16 إلى 160 بايت
                detailed_logger.debug(f"✅ تم تحويل السر عبر base64 (محاولة {attempt_num + 1}): {len(hex_secret)} حرف")
                return hex_secret.lower()
                
        except Exception as e:
            detailed_logger.debug(f"❌ فشل في محاولة base64 {attempt_num + 1}: {e}")
            continue
    
    # محاولة 3: hex مع إزالة البادئات
    for prefix in ['ee', 'dd', '00', 'ff']:
        if secret.lower().startswith(prefix):
            remaining = secret[len(prefix):]
            hex_only = re.sub(r'[^A-Fa-f0-9]', '', remaining)
            if re.fullmatch(r'[A-Fa-f0-9]+', hex_only) and len(hex_only) % 2 == 0:
                if 32 <= len(hex_only) <= 156:
                    detailed_logger.debug(f"✅ سر hex مع بادئة {prefix}: {len(hex_only)} حرف")
                    return hex_only.lower()
    
    # محاولة 4: معالجة خاصة للأسرار المعقدة
    try:
        # إزالة جميع الرموز غير المطلوبة
        clean_secret = re.sub(r'[^A-Za-z0-9+/=_-]', '', secret)
        if clean_secret:
            # تحويل URL-safe base64
            clean_secret = clean_secret.replace('-', '+').replace('_', '/')
            
            # إضافة padding
            while len(clean_secret) % 4 != 0:
                clean_secret += '='
            
            decoded = base64.b64decode(clean_secret)
            hex_secret = decoded.hex()
            
            if 16 <= len(hex_secret) <= 320:  # أي سر معقول
                detailed_logger.debug(f"✅ تم تحويل السر بالمعالجة الخاصة: {len(hex_secret)} حرف")
                return hex_secret.lower()
                
    except Exception as e:
        detailed_logger.debug(f"❌ فشل في المعالجة الخاصة: {e}")
    
    detailed_logger.warning(f"⚠️ فشل في تحويل السر: {original_secret[:30]}... (طول: {len(original_secret)})")
    return None

def parse_proxy_link_enhanced(link: str) -> dict | None:
    """تحليل رابط البروكسي محسن مع دعم صيغ متعددة ومعالجة أفضل للأخطاء"""
    if not link or not isinstance(link, str):
        return None
    
    link = link.strip()
    
    # دعم صيغ مختلفة من الروابط
    supported_patterns = [
        r'https?://t\.me/proxy\?(.+)',
        r'tg://proxy\?(.+)',
        r't\.me/proxy\?(.+)',
        r'https?://t\.me/socks\?(.+)',
        r'tg://socks\?(.+)'
    ]
    
    parsed_query = None
    for pattern in supported_patterns:
        match = re.search(pattern, link)
        if match:
            parsed_query = match.group(1)
            break
    
    if not parsed_query:
        # محاولة تحليل الرابط بطريقة عادية
        try:
            parsed = urlparse(link)
            parsed_query = parsed.query
        except Exception:
            detailed_logger.error(f"❌ فشل في تحليل رابط البروكسي: {link}")
            return None
    
    if not parsed_query:
        return None
    
    try:
        params = parse_qs(parsed_query)
        
        # استخراج المعلمات مع دعم أسماء مختلفة
        server = (params.get('server', ['']) + params.get('host', ['']) + params.get('ip', ['']))[0]
        port = (params.get('port', ['']) + params.get('p', ['']))[0]
        secret = (params.get('secret', ['']) + params.get('s', ['']) + params.get('key', ['']))[0]
        
        # محاولة استخراج من مسار URL إذا لم تُعثر المعلمات
        if not all([server, port, secret]):
            try:
                parsed = urlparse(link)
                parts = parsed.path.strip('/').split('/')
                if len(parts) >= 3:
                    server = server or parts[0]
                    port = port or parts[1]
                    secret = secret or '/'.join(parts[2:])
            except Exception:
                pass
        
        # التحقق من وجود جميع المعلمات المطلوبة
        if not all([server, port, secret]):
            detailed_logger.error(f"❌ معلمات ناقصة في رابط البروكسي: server={server}, port={port}, secret={bool(secret)}")
            return None
        
        # تنظيف وتحقق من الخادم
        server = server.strip()
        if not server or not re.match(r'^[a-zA-Z0-9.-]+$', server):
            detailed_logger.error(f"❌ عنوان خادم غير صالح: {server}")
            return None
        
        # تحويل وتحقق من المنفذ
        try:
            port = int(port)
            if not (1 <= port <= 65535):
                detailed_logger.error(f"❌ رقم منفذ غير صالح: {port}")
                return None
        except ValueError:
            detailed_logger.error(f"❌ فشل في تحويل رقم المنفذ: {port}")
            return None
        
        # تحويل السر
        hex_secret = convert_secret_enhanced(secret)
        if not hex_secret:
            detailed_logger.error(f"❌ فشل في تحويل سر البروكسي")
            return None
        
        # إنشاء النتيجة
        result = {
            'server': server,
            'port': port,
            'secret': hex_secret,
            'format': 'hex',
            'original_link': link,
            'parsed_at': int(time.time())
        }
        
        detailed_logger.info(f"✅ تم تحليل رابط البروكسي بنجاح: {server}:{port}")
        return result
        
    except Exception as e:
        detailed_logger.error(f"❌ خطأ في تحليل رابط البروكسي {link}: {e}")
        return None

# === إنشاء المكونات المحسنة ===
enhanced_proxy_checker = EnhancedProxyChecker()

async def run_enhanced_report_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عملية إبلاغ محسنة مع تتبع مفصل وتأكيد الإرسال"""
    config = context.user_data
    sessions = config.get("accounts", [])
    
    if not sessions:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ لا توجد حسابات صالحة لبدء العملية."
        )
        return
    
    targets = config.get("targets", [])
    reports_per_account = config.get("reports_per_account", 1)
    proxies = config.get("proxies", [])
    
    # إحصائيات مفصلة
    total_expected = len(sessions) * len(targets) * reports_per_account
    config.update({
        "total_reports": total_expected,
        "progress_success": 0,
        "progress_confirmed": 0,
        "progress_failed": 0,
        "active": True,
        "lock": asyncio.Lock(),
        "start_time": time.time(),
        "detailed_stats": {
            "verified_reports": [],
            "failed_sessions": [],
            "proxy_performance": {}
        }
    })
    
    # فحص البروكسيات أولاً
    if proxies:
        progress_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔍 جاري فحص البروكسيات بشكل مفصل..."
        )
        
        # استخدام أول جلسة للفحص
        test_session = sessions[0]["session"]
        checked_proxies = await enhanced_proxy_checker.batch_check_proxies(test_session, proxies)
        
        active_proxies = [p for p in checked_proxies if p.get('status') == 'active']
        
        if not active_proxies:
            await progress_msg.edit_text(
                "❌ لا توجد بروكسيات نشطة. سيتم استخدام الاتصال المباشر."
            )
            config["proxies"] = []
        else:
            best_proxies = enhanced_proxy_checker.get_best_proxies(active_proxies, 5)
            config["proxies"] = best_proxies
            
            proxy_summary = "\n".join([
                f"• {p['server']} - جودة: {p['quality_score']}% - ping: {p['ping']}ms"
                for p in best_proxies[:3]
            ])
            
            await progress_msg.edit_text(
                f"✅ تم فحص البروكسيات\n"
                f"نشط: {len(active_proxies)}/{len(proxies)}\n\n"
                f"أفضل البروكسيات:\n{proxy_summary}"
            )
            
            await asyncio.sleep(2)
    
    # بدء عملية الإبلاغ المحسنة
    try:
        progress_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🚀 بدء عملية الإبلاغ المحققة...",
            parse_mode="HTML"
        )
        context.user_data["progress_message"] = progress_message
        
        # إنشاء مهام للحسابات
        session_tasks = []
        for session in sessions:
            task = asyncio.create_task(
                process_enhanced_session(session, targets, reports_per_account, config, context)
            )
            session_tasks.append(task)
        
        context.user_data["tasks"] = session_tasks
        
        # مراقبة التقدم المحسنة
        await monitor_enhanced_progress(context, progress_message, session_tasks)
        
    except Exception as e:
        logger.error(f"خطأ في عملية الإبلاغ المحسنة: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ خطأ في العملية: {str(e)}"
        )

async def process_enhanced_session(session: dict, targets: list, reports_per_account: int, 
                                 config: dict, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جلسة واحدة مع تحقق مفصل"""
    session_id = session.get("id", "unknown")
    session_str = session.get("session")
    proxies = config.get("proxies", [])
    
    if not session_str:
        detailed_logger.error(f"❌ جلسة فارغة للحساب {session_id}")
        return
    
    client = None
    current_proxy = None
    
    try:
        # اختيار أفضل بروكسي
        if proxies:
            current_proxy = random.choice(proxies)
            detailed_logger.info(f"🔗 استخدام البروكسي {current_proxy['server']} للحساب {session_id}")
        
        # إعداد العميل
        params = {
            "api_id": API_ID,
            "api_hash": API_HASH,
            "timeout": 30,
            "device_model": f"ReporterBot-{session_id}",
            "system_version": "2.0.0",
            "app_version": "2.0.0"
        }
        
        if current_proxy:
            # معالجة السر للتوافق مع Telethon
            secret = current_proxy["secret"]
            if isinstance(secret, bytes):
                secret_hex = secret.hex()
            elif isinstance(secret, str):
                # التحقق من أنه hex string صالح
                try:
                    bytes.fromhex(secret)  # اختبار صحة hex
                    secret_hex = secret
                except ValueError:
                    secret_hex = secret  # استخدام كما هو إذا لم يكن hex
            else:
                secret_hex = str(secret)
                
            params.update({
                "connection": ConnectionTcpMTProxyRandomizedIntermediate,
                "proxy": (current_proxy["server"], current_proxy["port"], secret_hex)
            })
        
        # الاتصال
        client = TelegramClient(StringSession(session_str), **params)
        await client.connect()
        
        if not await client.is_user_authorized():
            raise SessionCompromised(f"الجلسة {session_id} غير مفوضة")
        
        # إنشاء مبلغ محقق
        reporter = VerifiedReporter(client, context)
        
        # استخدام وظيفة الإبلاغ الجماعي الجديدة
        result = await reporter.execute_batch_report(
            targets=targets,
            reason_obj=config["reason_obj"],
            method_type=config["method_type"],
            message=config.get("message", ""),
            reports_count=reports_per_account,
            cycle_delay=config.get("cycle_delay", 1)
        )
        
        # تحديث الإحصائيات
        async with config["lock"]:
            config["progress_success"] += result.get("verified_reports", 0)
            config["progress_confirmed"] += result.get("verified_reports", 0)
            
            if result.get("verified_reports", 0) > 0:
                config["detailed_stats"]["verified_reports"].extend(
                    result.get("report_ids", [])
                )
        
        detailed_logger.info(f"✅ اكتمل الحساب {session_id} - البلاغات المحققة: {reporter.stats['confirmed']}")
        
    except Exception as e:
        detailed_logger.error(f"❌ فشل الحساب {session_id}: {e}")
        async with config["lock"]:
            config["detailed_stats"]["failed_sessions"].append({
                "session_id": session_id,
                "error": str(e),
                "timestamp": time.time()
            })
    
    finally:
        if client and client.is_connected():
            await client.disconnect()

async def monitor_enhanced_progress(context: ContextTypes.DEFAULT_TYPE, 
                                  progress_message: Any, session_tasks: list):
    """مراقبة التقدم المحسنة مع إحصائيات مفصلة"""
    config = context.user_data
    start_time = config["start_time"]
    
    while config.get("active", True) and any(not t.done() for t in session_tasks):
        async with config["lock"]:
            success = config["progress_success"]
            confirmed = config["progress_confirmed"]
            failed = config["progress_failed"]
            total = config["total_reports"]
            
        completed = success + failed
        progress_percent = min(100, int((completed / total) * 100))
        
        elapsed = time.time() - start_time
        if completed > 0:
            eta_seconds = (elapsed / completed) * (total - completed)
            eta_str = str(timedelta(seconds=int(eta_seconds)))
        else:
            eta_str = "حساب..."
        
        # شريط التقدم المحسن
        filled = int(20 * (progress_percent / 100))
        progress_bar = "█" * filled + "░" * (20 - filled)
        
        verification_rate = (confirmed / success * 100) if success > 0 else 0
        
        text = (
            f"📊 <b>تقدم الإبلاغات المحققة</b>\n\n"
            f"<code>[{progress_bar}]</code> {progress_percent}%\n\n"
            f"📈 <b>الإحصائيات:</b>\n"
            f"▫️ المطلوب: {total}\n"
            f"✅ المرسل: {success}\n"
            f"🔐 المحقق: {confirmed} ({verification_rate:.1f}%)\n"
            f"❌ الفاشل: {failed}\n"
            f"⏱ المتبقي: {eta_str}\n"
            f"⏰ المدة: {str(timedelta(seconds=int(elapsed)))}"
        )
        
        try:
            await progress_message.edit_text(text, parse_mode="HTML")
        except BadRequest:
            pass
        
        await asyncio.sleep(3)
    
    # النتائج النهائية
    async with config["lock"]:
        final_stats = {
            "success": config["progress_success"],
            "confirmed": config["progress_confirmed"],
            "failed": config["progress_failed"],
            "verification_rate": (config["progress_confirmed"] / config["progress_success"] * 100) 
                               if config["progress_success"] > 0 else 0,
            "total_time": time.time() - start_time,
            "verified_reports": len(config["detailed_stats"]["verified_reports"]),
            "failed_sessions": len(config["detailed_stats"]["failed_sessions"])
        }
    
    final_text = (
        f"🎯 <b>اكتملت العملية المحققة!</b>\n\n"
        f"📊 <b>النتائج النهائية:</b>\n"
        f"• البلاغات المرسلة: {final_stats['success']}\n"
        f"• البلاغات المحققة: {final_stats['confirmed']}\n"
        f"• معدل التحقق: {final_stats['verification_rate']:.1f}%\n"
        f"• الجلسات الفاشلة: {final_stats['failed_sessions']}\n"
        f"• المدة الإجمالية: {str(timedelta(seconds=int(final_stats['total_time'])))}\n\n"
        f"📋 تم حفظ تقرير مفصل في detailed_reports.log"
    )
    
    try:
        await progress_message.edit_text(final_text, parse_mode="HTML")
    except Exception:
        await context.bot.send_message(
            chat_id=progress_message.chat_id,
            text=final_text,
            parse_mode="HTML"
        )
    
    # حفظ التقرير المفصل
    detailed_logger.info(f"📋 تقرير نهائي: {json.dumps(final_stats, indent=2, ensure_ascii=False)}")