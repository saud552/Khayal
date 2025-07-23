# DrKhayal/Telegram/common_improved.py - نسخة محسنة ومطورة

import asyncio
import sqlite3
import base64
import logging
import time
import random
import re
import json
import hashlib
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from telethon import TelegramClient, functions, types, utils
from telethon.errors import (
    AuthKeyDuplicatedError,
    FloodWaitError,
    PeerFloodError,
    SessionPasswordNeededError,
    RPCError,
    TimeoutError as TelethonTimeoutError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    MessageIdInvalidError,
    PeerIdInvalidError
)
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate
from telethon.sessions import StringSession
from encryption import decrypt_session
from config import API_ID, API_HASH
from add import safe_db_query

logger = logging.getLogger(__name__)
# استيراد DB_PATH من config.py
try:
    from config import DB_PATH
except ImportError:
    DB_PATH = 'accounts.db'  # قيمة افتراضية

# إعداد نظام تسجيل مفصل للتتبع
detailed_logger = logging.getLogger('detailed_reporter')
detailed_handler = logging.FileHandler('detailed_reports.log', encoding='utf-8')
detailed_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
detailed_handler.setFormatter(detailed_formatter)
detailed_logger.addHandler(detailed_handler)
detailed_logger.setLevel(logging.INFO)

# === الثوابت المحسنة ===
PROXY_CHECK_TIMEOUT = 25  # ثانية
PROXY_RECHECK_INTERVAL = 3000  # 5 دقائق
MAX_PROXY_RETRIES = 30
REPORT_CONFIRMATION_TIMEOUT = 10  # ثانية للتأكيد
MAX_REPORTS_PER_SESSION = 1000000  # الحد الأقصى للبلاغات لكل جلسة

# استثناءات مخصصة محسنة
class ProxyTestFailed(Exception):
    """فشل في اختبار البروكسي"""
    pass

class ReportNotConfirmed(Exception):
    """لم يتم تأكيد وصول البلاغ"""
    pass

class SessionCompromised(Exception):
    """الجلسة معرضة للخطر"""
    pass

class RateLimitExceeded(Exception):
    """تم تجاوز حد المعدل"""
    pass

# === أنواع البلاغات مع معرفات التأكيد ===
REPORT_TYPES_ENHANCED = {
    2: ("رسائل مزعجة", types.InputReportReasonSpam(), "spam"),
    3: ("إساءة أطفال", types.InputReportReasonChildAbuse(), "child_abuse"),
    4: ("محتوى جنسي", types.InputReportReasonPornography(), "pornography"),
    5: ("عنف", types.InputReportReasonViolence(), "violence"),
    6: ("انتهاك خصوصية", types.InputReportReasonPersonalDetails(), "privacy"),
    7: ("مخدرات", types.InputReportReasonIllegalDrugs(), "drugs"),
    8: ("حساب مزيف", types.InputReportReasonFake(), "fake"),
    9: ("حقوق النشر", types.InputReportReasonCopyright(), "copyright"),
    11: ("أخرى", types.InputReportReasonOther(), "other"),
}

class EnhancedProxyChecker:
    """نظام فحص بروكسي محسن مع تتبع مفصل وتحقق حقيقي"""
    
    def __init__(self):
        self.proxy_stats = {}
        self.failed_proxies = set()
        self.last_check_times = {}
        self.concurrent_checks = 3  # عدد الفحوصات المتزامنة
        
    async def deep_proxy_test(self, session_str: str, proxy_info: dict) -> dict:
        """اختبار عميق للبروكسي مع فحوصات متعددة"""
        result = proxy_info.copy()
        client = None
        
        try:
            # إعداد العميل مع timeout صارم
            params = {
                "api_id": API_ID,
                "api_hash": API_HASH,
                "timeout": PROXY_CHECK_TIMEOUT,
                "connection": ConnectionTcpMTProxyRandomizedIntermediate,
                "device_model": "Proxy Test Bot",
                "system_version": "1.0.0",
                "app_version": "1.0.0",
                "lang_code": "ar"
            }
            
            # تحضير السر
            secret = proxy_info["secret"]
            if isinstance(secret, str):
                try:
                    secret_bytes = bytes.fromhex(secret)
                except ValueError:
                    raise ProxyTestFailed(f"سر غير صالح: {secret}")
            else:
                secret_bytes = secret
                
            params["proxy"] = (
                proxy_info["server"],
                proxy_info["port"],
                secret_bytes
            )
            
            # اختبار الاتصال الأولي
            start_time = time.time()
            client = TelegramClient(StringSession(session_str), **params)
            
            # اختبار الاتصال مع timeout
            await asyncio.wait_for(client.connect(), timeout=PROXY_CHECK_TIMEOUT)
            connection_time = time.time() - start_time
            
            # التحقق من التفويض
            if not await client.is_user_authorized():
                raise ProxyTestFailed("الجلسة غير مفوضة")
            
            # اختبار سرعة الاستجابة
            response_start = time.time()
            me = await asyncio.wait_for(client.get_me(), timeout=PROXY_CHECK_TIMEOUT)
            response_time = time.time() - response_start
            
            # اختبار إضافي: جلب الحوارات
            dialogs_start = time.time()
            async for dialog in client.iter_dialogs(limit=5):
                break
            dialogs_time = time.time() - dialogs_start
            
            # تقييم جودة البروكسي
            ping = int(connection_time * 1000)
            responsiveness = int(response_time * 1000)
            
            quality_score = 100
            if ping > 3000:
                quality_score -= 30
            elif ping > 1500:
                quality_score -= 15
                
            if responsiveness > 2000:
                quality_score -= 20
            elif responsiveness > 1000:
                quality_score -= 10
                
            result.update({
                "status": "active",
                "ping": ping,
                "response_time": responsiveness,
                "dialogs_time": int(dialogs_time * 1000),
                "quality_score": max(0, quality_score),
                "last_check": int(time.time()),
                "user_id": me.id,
                "connection_successful": True,
                "error": None
            })
            
            detailed_logger.info(f"✅ بروكسي نشط: {proxy_info['server']} - ping: {ping}ms - جودة: {quality_score}%")
            
        except asyncio.TimeoutError:
            result.update({
                "status": "timeout",
                "ping": 9999,
                "response_time": 9999,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": "انتهت مهلة الاتصال"
            })
            self.failed_proxies.add(proxy_info["server"])
            
        except ProxyTestFailed as e:
            result.update({
                "status": "failed",
                "ping": 0,
                "response_time": 0,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": str(e)
            })
            self.failed_proxies.add(proxy_info["server"])
            
        except Exception as e:
            result.update({
                "status": "error",
                "ping": 0,
                "response_time": 0,
                "quality_score": 0,
                "last_check": int(time.time()),
                "connection_successful": False,
                "error": str(e)
            })
            logger.error(f"خطأ في فحص البروكسي {proxy_info['server']}: {e}")
            
        finally:
            if client and client.is_connected():
                try:
                    await client.disconnect()
                except:
                    pass
                    
        return result
    
    async def batch_check_proxies(self, session_str: str, proxies: List[dict]) -> List[dict]:
        """فحص مجموعة من البروكسيات بشكل متوازي"""
        semaphore = asyncio.Semaphore(self.concurrent_checks)
        
        async def check_single(proxy):
            async with semaphore:
                return await self.deep_proxy_test(session_str, proxy)
        
        tasks = [check_single(proxy) for proxy in proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"خطأ في فحص البروكسي {proxies[i]['server']}: {result}")
                proxies[i].update({
                    "status": "error",
                    "error": str(result),
                    "quality_score": 0
                })
                valid_results.append(proxies[i])
            else:
                valid_results.append(result)
                
        return valid_results
    
    def get_best_proxies(self, proxies: List[dict], count: int = 5) -> List[dict]:
        """الحصول على أفضل البروكسيات مرتبة حسب الجودة"""
        active_proxies = [p for p in proxies if p.get('status') == 'active']
        
        # ترتيب حسب نقاط الجودة ثم السرعة
        sorted_proxies = sorted(
            active_proxies,
            key=lambda x: (x.get('quality_score', 0), -x.get('ping', 9999)),
            reverse=True
        )
        
        return sorted_proxies[:count]
    
    def needs_recheck(self, proxy_info: dict) -> bool:
        """تحديد إذا كان البروكسي يحتاج إعادة فحص"""
        last_check = proxy_info.get('last_check', 0)
        return (time.time() - last_check) > PROXY_RECHECK_INTERVAL

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
            
            # الحالة 0: الهدف هو كائن Telethon مباشر (محفوظ من قبل)
            if hasattr(target, 'id') and hasattr(target, '__class__'):
                # التحقق من أن الكائن هو من أنواع Telethon
                if any(isinstance(target, cls) for cls in [types.Channel, types.Chat, types.User]):
                    target_info.update({
                        "resolved": utils.get_input_peer(target),
                        "type": "peer",
                        "entity_id": target.id
                    })
                    return target_info
            
            # الحالة 1: الهدف هو قاموس (نتيجة من parse_message_link)
            if isinstance(target, dict) and 'channel' in target and 'message_id' in target:
                try:
                    # إذا كان channel هو كائن Telethon
                    if hasattr(target['channel'], 'id') and hasattr(target['channel'], '__class__'):
                        entity = target['channel']
                    # إذا كان channel هو معرف رقمي
                    elif isinstance(target['channel'], int):
                        entity = await self.client.get_entity(target['channel'])
                    else:
                        # التحقق من صحة اسم المستخدم
                        username = target['channel'].lstrip('@')
                        if re.match(r'^[a-zA-Z][\w\d]{3,30}[a-zA-Z\d]$', username):
                            entity = await self.client.get_entity(username)
                        else:
                            # حل كمعرف قناة مباشرة
                            entity = await self.client.get_entity(types.PeerChannel(target['channel']))
                except (ValueError, TypeError, RPCError) as e:
                    # المحاولة الأخيرة: حل باستخدام معرف القناة كرقم
                    try:
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
    """تحويل سر البروكسي محسن مع دعم جميع الصيغ"""
    secret = secret.strip()
    
    # إزالة المسافات والأحرف الخاصة
    clean_secret = re.sub(r'[^A-Fa-f0-9]', '', secret)
    
    # فحص الصيغة السداسية
    if re.fullmatch(r'[A-Fa-f0-9]+', clean_secret) and len(clean_secret) % 2 == 0:
        if len(clean_secret) >= 32:  # سر صالح
            return clean_secret.lower()
    
    # محاولة فك base64
    try:
        # إزالة البادئات
        for prefix in ['ee', 'dd', '00']:
            if secret.startswith(prefix):
                secret = secret[len(prefix):]
                break
        
        # تحويل base64 URL-safe
        cleaned = secret.replace('-', '+').replace('_', '/')
        padding = '=' * (-len(cleaned) % 4)
        decoded = base64.b64decode(cleaned + padding)
        
        hex_secret = decoded.hex()
        if len(hex_secret) >= 32:
            return hex_secret
            
    except Exception:
        pass
    
    return None

def parse_proxy_link_enhanced(link: str) -> dict | None:
    """تحليل رابط البروكسي محسن مع دعم صيغ متعددة"""
    try:
        parsed = urlparse(link)
        params = parse_qs(parsed.query)
        
        server = params.get('server', [''])[0]
        port = params.get('port', [''])[0]
        secret = params.get('secret', [''])[0]
        
        if not all([server, port, secret]):
            # محاولة استخراج من المسار
            parts = parsed.path.strip('/').split('/')
            if len(parts) >= 3:
                server, port, secret = parts[0], parts[1], '/'.join(parts[2:])
        
        if not all([server, port, secret]):
            return None
        
        try:
            port = int(port)
        except ValueError:
            return None
        
        hex_secret = convert_secret_enhanced(secret)
        if not hex_secret:
            return None
        
        return {
            'server': server.strip(),
            'port': port,
            'secret': hex_secret,
            'format': 'hex',
            'original_link': link
        }
        
    except Exception as e:
        logger.error(f"خطأ في تحليل رابط البروكسي: {e}")
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
            secret_bytes = bytes.fromhex(current_proxy["secret"])
            params.update({
                "connection": ConnectionTcpMTProxyRandomizedIntermediate,
                "proxy": (current_proxy["server"], current_proxy["port"], secret_bytes)
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