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
# Removed MTProto proxy import - now using Socks5

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

# تعطيل support_module مؤقتاً لحل مشكلة التعليق
# try:
#     from Telegram.support_module import register_support_handlers
# except ImportError:
#     logging.warning("تحذير: لم يتم العثور على وحدة الدعم الخاص (support_module.py). سيتم تجاهلها.")
register_support_handlers = None
logging.info("ℹ️ تم تعطيل support_module مؤقتاً لحل مشكلة التعليق")

from Telegram.report_peer import peer_report_conv
from Telegram.report_message import message_report_conv
from Telegram.report_photo import photo_report_conv
from Telegram.report_sponsored import sponsored_report_conv
from Telegram.report_mass import mass_report_conv

# استيراد الدوال المشتركة المحدثة
from Telegram.common import get_categories, get_accounts, cancel_operation
from Telegram.common_improved import (
    socks5_proxy_checker, 
    parse_socks5_proxy, 
    run_enhanced_report_process,
    Socks5ProxyChecker,
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
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
             "👋 أهلاً بك! اختر القسم الذي تريد العمل عليه:",
             reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "👋 أهلاً بك! اختر القسم الذي تريد العمل عليه:",
            reply_markup=reply_markup
        )

# ===================================================================
# قسم إعداد بلاغات تيليجرام (التدفق الأولي)
# ===================================================================

async def show_telegram_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يعرض قائمة خيارات قسم تيليجرام."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🏴‍☠ بدء عملية الإبلاغ", callback_data="start_proxy_setup")],
        [InlineKeyboardButton("🛠 الدعم الخاص", callback_data="special_support")],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_menu")]
    ]
    
    await query.edit_message_text(
        "📢 <b>قسم بلاغات تيليجرام</b>\n\n"
        "🔥 <b>نظام البروكسي الجديد:</b>\n"
        "• ✅ دعم Socks5\n"
        "• ❌ إزالة MTProto\n"
        "• 🚀 أداء محسن\n\n"
        "اختر الإجراء الذي تريد تنفيذه:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TELEGRAM_MENU

async def start_proxy_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 1: اختيار نوع البروكسي قبل تحميل الحسابات."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📡 استخدام بروكسي Socks5", callback_data="use_proxy")],
        [InlineKeyboardButton("⏭️ تخطي (اتصال مباشر)", callback_data="skip_proxy")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_tg_menu")]
    ]
    
    await query.edit_message_text(
        "🌐 <b>الخطوة 1/3: إعداد البروكسي</b>\n\n"
        "🔄 <b>النظام الجديد - Socks5:</b>\n"
        "• تنسيق بسيط: IP:PORT\n"
        "• فحص تلقائي للجودة\n"
        "• أداء أفضل من MTProto\n\n"
        "هل تريد استخدام بروكسيات Socks5؟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_PROXY_OPTION

async def choose_session_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 2: تطلب من المستخدم اختيار فئة الحسابات (بعد إعداد البروكسي)."""
    query = update.callback_query
    await query.answer()
    
    categories = get_categories()
    if not categories:
        await query.edit_message_text("❌ لا توجد فئات تحتوي على حسابات. يرجى إضافتها أولاً.")
        return ConversationHandler.END
        
    keyboard = []
    for cat_id, name, count in categories:
        keyboard.append([InlineKeyboardButton(f"{name} ({count} حساب)", callback_data=f"cat_{cat_id}")])
    
    keyboard.append([InlineKeyboardButton("رجوع 🔙", callback_data="back_to_proxy_setup")])
    
    await query.edit_message_text(
        "📂 <b>الخطوة 2/3: اختيار فئة الحسابات</b>\n\n"
        "✅ تم إعداد البروكسي بنجاح\n\n"
        "اختر الفئة التي تحتوي على الحسابات التي تريد استخدامها:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_CATEGORY

async def process_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 2: تعالج اختيار الفئة وتطلب خيار البروكسي."""
    query = update.callback_query
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
    await query.answer()
    
    if query.data == "use_proxy":
        await query.edit_message_text(
            "🌐 <b>إدخال بروكسيات Socks5</b>\n\n"
            "أرسل بروكسيات Socks5 (كل بروكسي في سطر):\n\n"
            "📌 <i>مثال:</i>\n"
            "159.203.61.169:1080\n"
            "96.126.96.163:9090\n"
            "139.59.1.14:1080\n\n"
            "⚠️ الحد الأقصى: 50 بروكسي",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("إلغاء ❌", callback_data="cancel_setup")]])
        )
        return ENTER_PROXY_LINKS
        
    context.user_data['proxies'] = []
    return await choose_session_source(update, context)

async def process_proxy_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة بروكسيات Socks5 مع الفحص الفوري"""
    input_proxies = update.message.text.strip().splitlines()
    if not input_proxies:
        await update.message.reply_text("لم يتم إدخال أي بروكسيات.")
        return await choose_session_source(update, context)

    # تطبيق الحد الأقصى للبروكسيات
    MAX_PROXIES = 50
    if len(input_proxies) > MAX_PROXIES:
        input_proxies = input_proxies[:MAX_PROXIES]
        await update.message.reply_text(f"⚠️ تم تقليل عدد البروكسيات إلى {MAX_PROXIES} (الحد الأقصى)")

    msg = await update.message.reply_text(f"🔍 جاري فحص {len(input_proxies)} بروكسي Socks5...")

    # تحليل البروكسيات
    parsed_proxies = []
    for proxy_line in input_proxies:
        proxy_info = parse_socks5_proxy(proxy_line.strip())
        if proxy_info:
            parsed_proxies.append(proxy_info)
        else:
            logger.warning(f"❌ بروكسي غير صالح: {proxy_line}")
            
    if not parsed_proxies:
        await msg.edit_text("❌ لم يتم العثور على أي بروكسيات صالحة.")
        return await choose_session_source(update, context)
        
    # فحص البروكسيات فوراً بدون جلسات (فحص اتصال أساسي)
    try:
        await msg.edit_text(f"🔍 بدء فحص {len(parsed_proxies)} بروكسي Socks5...")
        
        # فحص بسيط للبروكسيات بدون جلسات تليجرام
        valid_proxies = []
        failed_count = 0
        
        for proxy in parsed_proxies:
            try:
                import socks
                import socket
                import time
                
                # اختبار الاتصال البسيط
                start_time = time.time()
                
                # إنشاء socket واختبار الاتصال
                sock = socks.socksocket()
                sock.set_proxy(socks.SOCKS5, proxy['host'], proxy['port'])
                sock.settimeout(10)
                
                # محاولة الاتصال بـ Google DNS للاختبار
                sock.connect(("8.8.8.8", 53))
                ping = int((time.time() - start_time) * 1000)
                sock.close()
                
                proxy['status'] = 'active'
                proxy['ping'] = ping
                valid_proxies.append(proxy)
                
            except Exception as e:
                proxy['status'] = 'failed'
                proxy['error'] = str(e)
                failed_count += 1
        
        # عرض النتائج
        active_count = len(valid_proxies)
        total_checked = len(parsed_proxies)
        
        if not valid_proxies:
            await msg.edit_text(
                f"⚠️ <b>نتائج فحص Socks5</b>\n\n"
                f"• تم فحص: {total_checked} بروكسي\n"
                f"• نشط: {active_count}\n"
                f"• فاشل: {failed_count}\n\n"
                f"سيتم استخدام الاتصال المباشر.",
                parse_mode="HTML"
            )
            context.user_data['proxies'] = []
        else:
            # ترتيب البروكسيات حسب السرعة
            valid_proxies.sort(key=lambda x: x.get('ping', 9999))
            best_details = "\n".join([
                f"• {p['host']}:{p['port']} - ping: {p['ping']}ms"
                for p in valid_proxies[:3]
            ])
            
            await msg.edit_text(
                f"✅ <b>نتائج فحص Socks5</b>\n\n"
                f"• تم فحص: {total_checked} بروكسي\n"
                f"• نشط: {active_count}\n"
                f"• فاشل: {failed_count}\n"
                f"• معدل النجاح: {(active_count/total_checked*100):.1f}%\n\n"
                f"🏆 <b>أفضل البروكسيات:</b>\n{best_details}",
                parse_mode="HTML"
            )
            
            # حفظ البروكسيات النشطة
            context.user_data['proxies'] = valid_proxies
            
    except Exception as e:
        logger.error(f"خطأ في فحص البروكسيات: {e}")
        await msg.edit_text("❌ حدث خطأ أثناء فحص البروكسيات.")
        context.user_data['proxies'] = []
    
    # الانتقال لاختيار الحسابات
    return await choose_session_source(update, context)

async def select_method_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_query=False) -> int:
    """الخطوة 3: تعرض قائمة طرق الإبلاغ ثم تنهي محادثة الإعداد."""
    text = (
        "🛠️ <b>الخطوة 3/3: اختيار طريقة الإبلاغ</b>\n\n"
        "✅ تم إعداد البروكسي والحسابات بنجاح\n\n"
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

async def back_to_proxy_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الرجوع إلى إعداد البروكسي."""
    return await start_proxy_setup(update, context)

# ===================================================================
# إعداد البوت
# ===================================================================

def main() -> None:
    """إعداد وتشغيل البوت."""
    logger.info("🚀 بدء تشغيل البوت الأساسي...")
    logger.info("🤖 إنشاء تطبيق البوت...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    logger.info("✅ تم إنشاء التطبيق بنجاح")

    # --- معالج البدء الرئيسي ---
    logger.info("📱 إضافة معالجات أساسية...")
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'))
    logger.info("✅ تم إضافة المعالجات الأساسية")

    # --- معالج قسم تيليجرام (الإعداد الأولي) ---
    logger.info("🛠️ إعداد معالج التليجرام...")
    telegram_setup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_telegram_menu, pattern='^main_telegram$')],
        states={
            TELEGRAM_MENU: [
                CallbackQueryHandler(start_proxy_setup, pattern='^start_proxy_setup$'),
                CallbackQueryHandler(back_to_main_menu, pattern='^special_support$'),
            ],
            SELECT_PROXY_OPTION: [
                CallbackQueryHandler(process_proxy_option, pattern='^(use_proxy|skip_proxy)$'),
                CallbackQueryHandler(show_telegram_menu, pattern='^back_to_tg_menu$'),
            ],
            ENTER_PROXY_LINKS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_proxy_links),
                CallbackQueryHandler(start_proxy_setup, pattern='^back_to_proxy_option$')
            ],
            SELECT_CATEGORY: [
                CallbackQueryHandler(process_category_selection, pattern='^cat_'),
                CallbackQueryHandler(start_proxy_setup, pattern='^back_to_proxy_setup$')
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
    logger.info("🔧 إضافة معالج إعداد التليجرام...")
    app.add_handler(telegram_setup_conv)
    logger.info("✅ تم إضافة معالج التليجرام")
    
    logger.info("📧 فحص معالج البريد الإلكتروني...")
    if email_conv_handler: 
        app.add_handler(email_conv_handler)
        logger.info("✅ تم إضافة معالج البريد الإلكتروني")
    else:
        logger.info("ℹ️ معالج البريد الإلكتروني غير متاح")
    
    logger.info("📋 إضافة معالجات التقارير...")
    app.add_handler(peer_report_conv)
    logger.info("✅ معالج تقارير الأشخاص")
    
    app.add_handler(message_report_conv)
    logger.info("✅ معالج تقارير الرسائل")
    
    app.add_handler(photo_report_conv)
    logger.info("✅ معالج تقارير الصور")
    
    app.add_handler(sponsored_report_conv)
    logger.info("✅ معالج التقارير المدعومة")
    
    app.add_handler(mass_report_conv)
    logger.info("✅ معالج التقارير الجماعية")
    
    logger.info("🔧 إضافة معالجات الدعم...")
    if register_support_handlers: 
        register_support_handlers(app)
        logger.info("✅ تم إضافة معالجات الدعم")
    else:
        logger.info("ℹ️ معالجات الدعم غير متاحة")
    
    logger.info("🎉 اكتمل تحميل جميع المعالجات!")
    logger.info("🚀 البوت جاهز ويبدأ التشغيل...")
    logger.info("🔗 رابط البوت: @AAAK6BOT")
    logger.info("✅ نظام Socks5 محمل وجاهز للاختبار")
    
    app.run_polling()

if __name__ == '__main__':
    main()