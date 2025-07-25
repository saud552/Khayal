# DrKhayal/khayal.py

import sys
import os
import asyncio
import logging
import time
from urllib.parse import urlparse, parse_qs

# ===================================================================
#  إضافة المجلد الرئيسي للمشروع إلى مسار بايثون
# ===================================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# ===================================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

# --- استيراد الإعدادات الأساسية ---
try:
    from config import BOT_TOKEN, OWNER_ID, DB_PATH, API_ID, API_HASH
except ImportError:
    logging.error("خطأ: لم يتم العثور على ملف config.py أو أنه ناقص. يجب أن يحتوي على: BOT_TOKEN, OWNER_ID, DB_PATH, API_ID, API_HASH")
    exit(1)
# --- استيراد معالجات المحادثة من الوحدات المنفصلة ---
try:
    from Email.Email_reports import email_conv_handler
except ImportError:
    logging.warning("تحذير: لم يتم العثور على وحدة البريد الإلكتروني. سيتم تجاهل هذا القسم.")
    email_conv_handler = None

try:
    from Telegram.support_module import register_support_handlers
except ImportError:
    logging.warning("تحذير: لم يتم العثور على وحدة الدعم الخاص (support_module.py). سيتم تجاهلها.")
    register_support_handlers = None

from Telegram.report_peer import peer_report_conv
from Telegram.report_message import message_report_conv
from Telegram.report_photo import photo_report_conv
from Telegram.report_sponsored import sponsored_report_conv
from Telegram.report_mass import mass_report_conv

# استيراد الدوال المشتركة المحدثة
from Telegram.common import get_categories, get_accounts, cancel_operation
from Telegram.common_improved import parse_proxy_link_enhanced as parse_proxy_link, enhanced_proxy_checker as proxy_checker, convert_secret_enhanced as convert_secret, simulate_manual_proxy_click, test_all_proxies_manual_style
from Telegram.common_improved import (
    run_enhanced_report_process,
    EnhancedProxyChecker,
    VerifiedReporter
)
from config_enhanced import enhanced_config

# تقليل مستوى تسجيل telethon لتجنب الرسائل غير الضرورية
logging.getLogger('telethon').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- حالات المحادثة للملف الرئيسي (للإعداد الأولي) ---
(
    TELEGRAM_MENU,
    SELECT_CATEGORY,
    SELECT_PROXY_OPTION,
    ENTER_PROXY_LINKS,
) = range(4)

# ===================================================================
#  قسم البدء والقائمة الرئيسية
# ===================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعرض القائمة الرئيسية عند إرسال /start أو العودة إليها."""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ هذا البوت مخصص للمالك فقط.")
        return

    keyboard = [
        [InlineKeyboardButton("📧 قسم بلاغات ايميل", callback_data="main_email")],
        [InlineKeyboardButton("📢 قسم بلاغات تيليجرام", callback_data="main_telegram")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "👋 <b>أهلاً بك في البوت المطور!</b>\n\n"
        "🆕 <b>جديد:</b> ميزة فحص البروكسي اليدوي!\n"
        "👆 محاكاة النقر الحقيقي على روابط البروكسي\n\n"
        "اختر القسم الذي تريد العمل عليه:"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
             welcome_text,
             parse_mode="HTML",
             reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            welcome_text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )

# ===================================================================
# قسم إعداد بلاغات تيليجرام (التدفق الأولي)
# ===================================================================

async def show_telegram_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعرض قائمة خيارات قسم تيليجرام."""
    query = update.callback_query
    logger.info(f"🔄 المستخدم دخل قائمة تيليجرام: {query.data}")
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🏴‍☠ بدء عملية الإبلاغ", callback_data="start_report_setup")],
        [InlineKeyboardButton("🛠 الدعم الخاص", callback_data="special_support")],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_menu")]
    ]
    
    await query.edit_message_text(
        "📢 <b>قسم بلاغات تيليجرام</b>\n\n"
        "اختر الإجراء الذي تريد تنفيذه:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TELEGRAM_MENU

async def choose_session_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 1: تطلب من المستخدم اختيار فئة الحسابات."""
    query = update.callback_query
    logger.info(f"🔄 المستخدم بدأ اختيار مصدر الجلسات: {query.data}")
    await query.answer()
    
    categories = get_categories()
    if not categories:
        await query.edit_message_text("❌ لا توجد فئات تحتوي على حسابات. يرجى إضافتها أولاً.")
        return ConversationHandler.END
        
    keyboard = []
    for cat_id, name, count in categories:
        keyboard.append([InlineKeyboardButton(f"{name} ({count} حساب)", callback_data=f"cat_{cat_id}")])
    
    keyboard.append([InlineKeyboardButton("رجوع 🔙", callback_data="back_to_tg_menu")])
    
    await query.edit_message_text(
        "📂 <b>الخطوة 1/3: اختيار فئة الحسابات</b>\n\n"
        "اختر الفئة التي تحتوي على الحسابات التي تريد استخدامها:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_CATEGORY

async def process_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 2: تعالج اختيار الفئة وتطلب خيار البروكسي."""
    query = update.callback_query
    logger.info(f"🔄 المستخدم اختار فئة: {query.data}")
    await query.answer()
    category_id = query.data.split("_")[1]
    
    # استخدم الدالة المحدثة من common.py
    accounts = get_accounts(category_id)
    
    if not accounts:
        await query.answer("❌ لا توجد حسابات صالحة في هذه الفئة!", show_alert=True)
        return SELECT_CATEGORY
        
    context.user_data['accounts'] = accounts
    await query.edit_message_text(
        f"✅ <b>تم تحميل {len(accounts)} حساب بنجاح!</b>\n\n"
        "📡 <b>الخطوة 2/3: إعداد البروكسي</b>\n\n"
        "هل تريد استخدام بروكسي للحسابات؟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📡 استخدام بروكسي", callback_data="use_proxy")],
            [InlineKeyboardButton("⏭️ تخطي (اتصال مباشر)", callback_data="skip_proxy")],
            [InlineKeyboardButton("رجوع 🔙", callback_data="back_to_cat_select")],
        ])
    )
    return SELECT_PROXY_OPTION

async def process_proxy_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تعالج خيار استخدام البروكسي وتطلب الروابط إذا لزم الأمر."""
    query = update.callback_query
    logger.info(f"🎯 معالجة خيار البروكسي: {query.data}")
    await query.answer()
    
    if query.data == "use_proxy":
        logger.info("📱 عرض قائمة خيارات فحص البروكسي مع الأزرار")
        await query.edit_message_text(
            "🌐 <b>إدخال روابط البروكسي</b>\n\n"
            "أرسل روابط بروكسي MTProto (كل رابط في سطر):\n\n"
            "📌 <i>مثال:</i>\n"
            "https://t.me/proxy?server=1.2.3.4&port=443&secret=ee...\n\n"
            "⚠️ الحد الأقصى: 50 بروكسي\n\n"
            "🎯 <b>طرق الاختبار:</b>\n"
            "• <b>عادي:</b> فحص فني سريع\n"
            "• <b>يدوي:</b> محاكاة النقر على الرابط",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("فحص عادي 🔧", callback_data="proxy_method_normal")],
                [InlineKeyboardButton("فحص يدوي 👆", callback_data="proxy_method_manual")],
                [InlineKeyboardButton("إلغاء ❌", callback_data="cancel_setup")]
            ])
        )
        logger.info("✅ تم عرض أزرار فحص البروكسي بنجاح")
        return ENTER_PROXY_LINKS
        
    context.user_data['proxies'] = []
    return await select_method_menu(update, context, is_query=True)

async def handle_proxy_method_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة اختيار طريقة فحص البروكسي"""
    query = update.callback_query
    logger.info(f"🔍 تم استقبال callback: {query.data}")
    await query.answer()
    
    if query.data == "proxy_method_normal":
        context.user_data['proxy_test_method'] = 'normal'
        method_name = "الفحص العادي 🔧"
    elif query.data == "proxy_method_manual":
        context.user_data['proxy_test_method'] = 'manual'
        method_name = "الفحص اليدوي 👆"
    else:
        return await select_method_menu(update, context, is_query=True)
    
    await query.edit_message_text(
        f"✅ تم اختيار: <b>{method_name}</b>\n\n"
        "🌐 <b>أرسل روابط البروكسي الآن</b>\n\n"
        "أرسل روابط بروكسي MTProto (كل رابط في سطر):\n\n"
        "📌 <i>مثال:</i>\n"
        "https://t.me/proxy?server=1.2.3.4&port=443&secret=ee...\n\n"
        "⚠️ الحد الأقصى: 50 بروكسي",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("إلغاء ❌", callback_data="cancel_setup")]])
    )
    return ENTER_PROXY_LINKS

async def process_proxy_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة روابط البروكسي مع النظام المحسن المطور"""
    input_links = update.message.text.strip().splitlines()
    if not input_links:
        await update.message.reply_text("لم يتم إدخال أي روابط.")
        return await select_method_menu(update, context)

    accounts = context.user_data.get("accounts")
    if not accounts:
        await update.message.reply_text(
            "⚠️ لا توجد حسابات مضافة لفحص البروكسيات.\n"
            "سيتم حفظ البروكسيات بدون فحص وستكون جاهزة للاستخدام.\n\n"
            "💡 لفحص البروكسيات، قم بإضافة حسابات أولاً من القائمة الرئيسية."
        )
        # متابعة بدون فحص
        session_str = None
        valid_accounts = []
    else:
        # البحث عن أفضل حساب صالح للفحص
        valid_accounts = []
        for account in accounts:
            if account.get("session") and len(account["session"]) > 10:  # تحقق أساسي من الجلسة
                valid_accounts.append(account)
        
        if not valid_accounts:
            await update.message.reply_text(
                "❌ لا توجد حسابات بجلسات صالحة لفحص البروكسي.\n"
                "تحقق من إضافة الحسابات بشكل صحيح."
            )
            session_str = None
        else:
            # استخدام أول حساب صالح
            session_str = valid_accounts[0]["session"]
            logger.info(f"🔑 استخدام حساب {valid_accounts[0].get('phone', 'غير محدد')} لفحص البروكسي")

    # تطبيق الحد الأقصى للبروكسيات
    MAX_PROXIES = enhanced_config.proxy.quality_threshold or 50
    if len(input_links) > MAX_PROXIES:
        input_links = input_links[:MAX_PROXIES]
        await update.message.reply_text(f"⚠️ تم تقليل عدد البروكسيات إلى {MAX_PROXIES} (الحد الأقصى)")

    # التحقق من طريقة الفحص المختارة
    test_method = context.user_data.get('proxy_test_method', 'normal')
    
    if test_method == 'manual':
        msg = await update.message.reply_text(f"👆 جاري الفحص اليدوي لـ {len(input_links)} بروكسي...")
    else:
        msg = await update.message.reply_text(f"🔍 جاري الفحص المحسن لـ {len(input_links)} بروكسي...")

    # تحليل الروابط بالنظام المحسن (للطريقة العادية فقط)
    if test_method == 'normal':
        parsed_proxies = []
        for link in input_links:
            proxy_info = parse_proxy_link(link)
            if proxy_info:
                parsed_proxies.append(proxy_info)
            else:
                logger.warning(f"❌ رابط بروكسي غير صالح: {link}")
                
        if not parsed_proxies:
            await msg.edit_text("❌ لم يتم العثور على أي روابط بروكسي صالحة.")
            return await select_method_menu(update, context)
        
    # فحص البروكسيات بالطريقة المختارة
    if session_str:
        try:
            if test_method == 'manual':
                await msg.edit_text(f"👆 بدء الفحص اليدوي لـ {len(input_links)} بروكسي...\n\n"
                                   f"🎯 <b>طريقة المحاكاة:</b>\n"
                                   f"• اتصال مباشر أولاً ✓\n"
                                   f"• تحليل رابط البروكسي ✓\n"
                                   f"• إعادة الاتصال عبر البروكسي ✓\n"
                                   f"• التحقق من الهوية ✓", parse_mode="HTML")
                
                # استخدام الطريقة اليدوية
                manual_results = await test_all_proxies_manual_style(session_str, input_links)
                
                # تحويل النتائج للتنسيق المتوقع
                valid_proxies = []
                for detail in manual_results["details"]:
                    proxy_data = {
                        "server": detail.get("link", "").split("server=")[1].split("&")[0] if "server=" in detail.get("link", "") else "unknown",
                        "port": int(detail.get("link", "").split("port=")[1].split("&")[0]) if "port=" in detail.get("link", "") else 0,
                        "secret": detail.get("link", "").split("secret=")[1].split("&")[0] if "secret=" in detail.get("link", "") else "",
                        "status": "active" if detail["status"] == "success" else "failed",
                        "error": detail.get("error", ""),
                        "method": "manual_simulation",
                        "connect_time": detail.get("connect_time", 0),
                        "user_name": detail.get("user_name", ""),
                        "steps": detail.get("steps", [])
                    }
                    valid_proxies.append(proxy_data)
                    
            else:
                await msg.edit_text(f"🔍 بدء الفحص العميق لـ {len(parsed_proxies)} بروكسي باستخدام الحساب المحدد...")
                
                # استخدام النظام المحسن للفحص المتوازي
                valid_proxies = await proxy_checker.batch_check_proxies(session_str, parsed_proxies)
        except Exception as e:
            logger.error(f"خطأ في فحص البروكسي: {e}")
            await msg.edit_text(f"❌ حدث خطأ في فحص البروكسي: {e}\nسيتم حفظ البروكسيات بدون فحص.")
            # إضافة البروكسيات بدون فحص
            valid_proxies = parsed_proxies
            for proxy in valid_proxies:
                proxy.update({
                    'status': 'unchecked',
                    'error': 'لم يتم الفحص بسبب خطأ',
                    'quality_score': 50  # نقاط افتراضية
                })
    else:
        await msg.edit_text(f"⚠️ سيتم حفظ {len(parsed_proxies)} بروكسي بدون فحص (لا توجد حسابات صالحة)")
        # إضافة البروكسيات بدون فحص
        valid_proxies = parsed_proxies
        for proxy in valid_proxies:
            proxy.update({
                'status': 'unchecked',
                'error': 'لا توجد حسابات للفحص',
                'quality_score': 50  # نقاط افتراضية
            })
    
    # تصفية البروكسيات النشطة وترتيبها حسب الجودة
    active_proxies = [p for p in valid_proxies if p.get('status') == 'active']
    unchecked_proxies = [p for p in valid_proxies if p.get('status') == 'unchecked']
    failed_proxies = [p for p in valid_proxies if p.get('status') not in ['active', 'unchecked']]
    
    # إحصائيات مفصلة
    total_checked = len(valid_proxies)
    active_count = len(active_proxies)
    unchecked_count = len(unchecked_proxies)
    failed_count = len(failed_proxies)
    
    # تسجيل النتائج المفصلة
    for proxy in active_proxies:
        logger.info(f"✅ بروكسي نشط: {proxy['server']} - جودة: {proxy.get('quality_score', 0)}% - ping: {proxy.get('ping', 0)}ms")
    
    for proxy in unchecked_proxies:
        logger.info(f"⚠️ بروكسي غير مفحوص: {proxy['server']} - {proxy.get('error', 'لم يتم الفحص')}")
    
    for proxy in failed_proxies:
        logger.warning(f"❌ بروكسي فاشل: {proxy['server']} - السبب: {proxy.get('error', 'غير محدد')}")
    
    # عرض النتائج المحسنة
    if not active_proxies and not unchecked_proxies:
        await msg.edit_text(
            f"⚠️ <b>نتائج الفحص</b>\n\n"
            f"• تم معالجة: {total_checked} بروكسي\n"
            f"• نشط: {active_count}\n"
            f"• فاشل: {failed_count}\n\n"
            f"سيتم استخدام الاتصال المباشر.",
            parse_mode="HTML"
        )
        context.user_data['proxies'] = []
    else:
        # دمج البروكسيات النشطة وغير المفحوصة
        all_usable_proxies = active_proxies + unchecked_proxies
        
        if active_proxies:
            # الحصول على أفضل البروكسيات المفحوصة
            best_proxies = proxy_checker.get_best_proxies(active_proxies, 3)
            best_details = "\n".join([
                f"• {p['server']} - جودة: {p.get('quality_score', 0)}% - {p.get('ping', 0)}ms"
                for p in best_proxies[:3]
            ])
            status_emoji = "✅"
            extra_info = f"• معدل النجاح: {(active_count/total_checked*100):.1f}%\n\n🏆 <b>أفضل البروكسيات:</b>\n{best_details}"
        else:
            # فقط بروكسيات غير مفحوصة
            best_details = "\n".join([
                f"• {p['server']} - غير مفحوص"
                for p in unchecked_proxies[:3]
            ])
            status_emoji = "⚠️"
            extra_info = f"\n💡 <b>البروكسيات المحفوظة (غير مفحوصة):</b>\n{best_details}"
        
        result_message = (
            f"{status_emoji} <b>نتائج المعالجة</b>\n\n"
            f"• تم معالجة: {total_checked} بروكسي\n"
            f"• نشط: {active_count}\n"
        )
        
        if unchecked_count > 0:
            result_message += f"• غير مفحوص: {unchecked_count}\n"
        
        result_message += f"• فاشل: {failed_count}\n{extra_info}"
        
        await msg.edit_text(result_message, parse_mode="HTML")
        
        # حفظ البروكسيات القابلة للاستخدام
        context.user_data['proxies'] = all_usable_proxies
    
    return await select_method_menu(update, context)

async def select_method_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_query=False) -> int:
    """الخطوة 3: تعرض قائمة طرق الإبلاغ ثم تنهي محادثة الإعداد."""
    text = (
        "🛠️ <b>الخطوة 3/3: اختيار طريقة الإبلاغ</b>\n\n"
        "اختر طريقة الإبلاغ التي تناسبك:"
    )
    keyboard = [
        [InlineKeyboardButton("👤 حساب/قناة", callback_data="method_peer")],
        [InlineKeyboardButton("💬 رسالة", callback_data="method_message")],
        [InlineKeyboardButton("🖼️ صورة شخصية", callback_data="method_photo")],
        [InlineKeyboardButton("📢 إعلان ممول", callback_data="method_sponsored")],
        [InlineKeyboardButton("🔥 بلاغ جماعي", callback_data="method_mass")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="back_to_proxy_option")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
        
    return ConversationHandler.END

# --- دوال الإلغاء والرجوع ---
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دالة العودة إلى القائمة الرئيسية من أي مكان."""
    query = update.callback_query
    if query: 
        await query.answer()
    context.user_data.clear()
    await start(update, context)
    return ConversationHandler.END

async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يلغي عملية الإعداد ويعود لقائمة تيليجرام."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("تم إلغاء عملية الإعداد.")
    await show_telegram_menu(update, context)
    return TELEGRAM_MENU

# ===================================================================
# إعداد البوت
# ===================================================================

def main() -> None:
    """إعداد وتشغيل البوت."""
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # --- معالج البدء الرئيسي ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'))

    # --- معالج قسم تيليجرام (الإعداد الأولي) ---
    telegram_setup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_telegram_menu, pattern='^main_telegram$')],
        states={
            TELEGRAM_MENU: [
                CallbackQueryHandler(choose_session_source, pattern='^start_report_setup$'),
                CallbackQueryHandler(back_to_main_menu, pattern='^special_support$'),
            ],
            SELECT_CATEGORY: [
                CallbackQueryHandler(process_category_selection, pattern='^cat_'),
                CallbackQueryHandler(show_telegram_menu, pattern='^back_to_tg_menu$')
            ],
            SELECT_PROXY_OPTION: [
                CallbackQueryHandler(process_proxy_option, pattern='^(use_proxy|skip_proxy)$'),
                CallbackQueryHandler(handle_proxy_method_selection, pattern='^proxy_method_(normal|manual)$'),
                CallbackQueryHandler(choose_session_source, pattern='^back_to_cat_select$'),
            ],
            ENTER_PROXY_LINKS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_proxy_links),
                CallbackQueryHandler(handle_proxy_method_selection, pattern='^proxy_method_(normal|manual)$'),
                CallbackQueryHandler(show_telegram_menu, pattern='^back_to_proxy_option$')
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_setup, pattern='^cancel_setup$'),
            
            CommandHandler('cancel', cancel_operation),
            CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'),
        ],
        per_user=True,
    )
    

    
    # --- إضافة جميع المعالجات إلى التطبيق ---
    app.add_handler(telegram_setup_conv)
    
    if email_conv_handler: 
        app.add_handler(email_conv_handler)
    
    app.add_handler(peer_report_conv)
    app.add_handler(message_report_conv)
    app.add_handler(photo_report_conv)
    app.add_handler(sponsored_report_conv)
    app.add_handler(mass_report_conv)
    
    if register_support_handlers: 
        register_support_handlers(app)
    
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()