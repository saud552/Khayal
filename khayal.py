# DrKhayal/khayal.py - نسخة منظمة

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
#  استيراد مكتبات Telegram
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

# ===================================================================
#  استيراد الإعدادات والوحدات
# ===================================================================

# --- استيراد الإعدادات الأساسية ---
try:
    from config import BOT_TOKEN, OWNER_ID, DB_PATH, API_ID, API_HASH
except ImportError:
    logging.error("خطأ: لم يتم العثور على ملف config.py أو أنه ناقص. يجب أن يحتوي على: BOT_TOKEN, OWNER_ID, DB_PATH, API_ID, API_HASH")
    exit(1)

# --- استيراد معالجات البريد الإلكتروني ---
try:
    from Email.email_reports import email_conv_handler, start_email
except ImportError:
    logging.warning("تحذير: لم يتم العثور على وحدة البريد الإلكتروني. سيتم تجاهل هذا القسم.")
    email_conv_handler = None
    start_email = None

# --- استيراد معالجات الدعم (تم التفعيل) ---
try:
    from Telegram.support_module import register_support_handlers
except ImportError:
    register_support_handlers = None
    logging.warning("تحذير: لم يتم العثور على وحدة الدعم الخاص (support_module.py). سيتم تجاهلها.")

# --- استيراد معالجات تقارير تيليجرام ---
from Telegram.report_peer import peer_report_conv
from Telegram.report_message import message_report_conv
from Telegram.report_photo import photo_report_conv
from Telegram.report_sponsored import sponsored_report_conv
from Telegram.report_mass import mass_report_conv
from Telegram.report_bot_messages import bot_messages_report_conv

# --- استيراد الدوال المشتركة ---
from Telegram.common import get_categories, get_accounts, cancel_operation
from Telegram.common_improved import (
    socks5_proxy_checker, 
    parse_socks5_proxy, 
    run_enhanced_report_process,
    Socks5ProxyChecker,
    VerifiedReporter
)
from config_enhanced import enhanced_config

# ===================================================================
#  إعداد التسجيل
# ===================================================================
logging.getLogger('telethon').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ===================================================================
#  تعريف حالات المحادثة
# ===================================================================
(
    TELEGRAM_MENU,
    SELECT_PROXY_OPTION,
    ENTER_PROXY_LINKS,
    SELECT_CATEGORY,
    SELECT_METHOD,
) = range(5)

# ===================================================================
#  دوال القائمة الرئيسية والبدء
# ===================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعرض القائمة الرئيسية عند إرسال /start أو العودة إليها."""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ هذا البوت مخصص للمالك فقط.")
        return

    keyboard = [
        [InlineKeyboardButton("📧 قسم بلاغات ايميل", callback_data="email_reports")],
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

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دالة العودة إلى القائمة الرئيسية من أي مكان."""
    query = update.callback_query
    if query: 
        await query.answer()
    context.user_data.clear()
    await start(update, context)

# ===================================================================
#  دوال قائمة تيليجرام
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

# ===================================================================
#  دوال إعداد البروكسي
# ===================================================================

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
        "🔄 <b>التحديث الجديد:</b>\n"
        "• ❌ إزالة نظام MTProto\n"
        "• ✅ تفعيل Socks5 فقط\n"
        "• 🚀 أداء أفضل وأكثر استقراراً\n\n"
        "اختر نوع الاتصال:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_PROXY_OPTION

async def process_proxy_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة اختيار نوع البروكسي."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "use_proxy":
        await query.edit_message_text(
            "📡 <b>إدخال بروكسيات Socks5</b>\n\n"
            "أرسل بروكسيات Socks5 (كل بروكسي في سطر منفصل):\n\n"
            "📌 <b>التنسيق المطلوب:</b>\n"
            "<code>IP:PORT</code>\n\n"
            "📝 <b>مثال:</b>\n"
            "<code>159.203.61.169:1080\n"
            "96.126.96.163:9090\n"
            "139.59.1.14:1080</code>\n\n"
            "⚠️ الحد الأقصى: 50 بروكسي\n"
            "🔍 سيتم فحصها فوراً قبل المتابعة",
            parse_mode="HTML"
        )
        return ENTER_PROXY_LINKS
    else:
        context.user_data['proxies'] = []
        # عرض فئات الحسابات مباشرة بدون بروكسي
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

# ===================================================================
#  دوال اختيار الحسابات
# ===================================================================

async def choose_session_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 2: اختيار فئة الحسابات بعد إعداد البروكسي."""
    try:
        if update.callback_query:
            query = update.callback_query
            await query.answer()
        
        categories = get_categories()
        if not categories:
            text = "❌ لا توجد فئات متاحة. تأكد من وجود حسابات في قاعدة البيانات."
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_proxy_setup")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)
            return SELECT_CATEGORY
        
        keyboard = []
        for cat_id, name, count in categories:
            keyboard.append([InlineKeyboardButton(f"{name} ({count} حساب)", callback_data=f"cat_{cat_id}")])
        
        keyboard.append([InlineKeyboardButton("رجوع 🔙", callback_data="back_to_proxy_setup")])
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "📂 <b>الخطوة 2/3: اختيار فئة الحسابات</b>\n\n"
                "اختر الفئة التي تريد استخدامها للإبلاغ:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "📂 <b>الخطوة 2/3: اختيار فئة الحسابات</b>\n\n"
                "اختر الفئة التي تريد استخدامها للإبلاغ:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return SELECT_CATEGORY
        
    except Exception as e:
        logger.error(f"خطأ في choose_session_source: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء تحميل الفئات.")
        return ConversationHandler.END

async def process_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة اختيار فئة الحسابات والانتقال لقائمة طرق الإبلاغ."""
    query = update.callback_query
    await query.answer()
    
    category_id = query.data.split('_')[1]  # قد يكون UUID أو رقم
    context.user_data['selected_category'] = category_id
    
    accounts = get_accounts(category_id)
    if not accounts:
        await query.edit_message_text("❌ لا توجد حسابات في هذه الفئة.")
        return ConversationHandler.END
    
    context.user_data['accounts'] = accounts
    
    # عرض قائمة طرق الإبلاغ والانتقال لحالة اختيار الطريقة
    await select_method_menu(update, context, is_query=True)
    return SELECT_METHOD

# ===================================================================
#  دوال اختيار طريقة الإبلاغ
# ===================================================================

async def select_method_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_query=False) -> int:
    """الخطوة 3: عرض قائمة طرق الإبلاغ المتاحة."""
    proxies = context.user_data.get('proxies', [])
    proxy_status = f"✅ {len(proxies)} بروكسي نشط" if proxies else "🔗 اتصال مباشر"
    
    selected_category = context.user_data.get('selected_category')
    accounts = context.user_data.get('accounts', [])
    
    text = (
        f"🎯 <b>الخطوة 3/3: اختيار طريقة الإبلاغ</b>\n\n"
        f"📊 <b>ملخص الإعداد:</b>\n"
        f"• البروكسي: {proxy_status}\n"
        f"• الحسابات: {len(accounts)} حساب\n"
        f"• الفئة: {selected_category}\n\n"
        f"🔥 اختر نوع الإبلاغ:"
    )
    
    keyboard = [
        [InlineKeyboardButton("👤 بلاغ عضو", callback_data="method_peer")],
        [InlineKeyboardButton("💬 بلاغ رسالة", callback_data="method_message")],
        [InlineKeyboardButton("🖼️ صورة شخصية", callback_data="method_photo")],
        [InlineKeyboardButton("📢 إعلان ممول", callback_data="method_sponsored")],
        [InlineKeyboardButton("🔥 بلاغ جماعي", callback_data="method_mass")],
        [InlineKeyboardButton("🤖 رسائل بوت", callback_data="method_bot_messages")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="back_to_proxy_option")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
        
    return ConversationHandler.END

# ===================================================================
#  دوال الرجوع والإلغاء
# ===================================================================

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

async def back_to_tg_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الرجوع إلى قائمة تيليجرام."""
    return await show_telegram_menu(update, context)

async def back_to_proxy_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الرجوع إلى خيارات البروكسي."""
    return await start_proxy_setup(update, context)

# ===================================================================
#  إعداد البوت والمعالجات
# ===================================================================

def main():
    """الدالة الرئيسية لتشغيل البوت."""
    logger.info("🤖 بدء تشغيل بوت الإبلاغ المطور...")
    logger.info("🌐 نظام Socks5 الجديد محمل")
    
    # إنشاء تطبيق البوت
    logger.info("🤖 إنشاء تطبيق البوت...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    logger.info("✅ تم إنشاء التطبيق بنجاح")

    # --- المعالجات الأساسية ---
    logger.info("📱 إضافة معالجات أساسية...")
    app.add_handler(CommandHandler("start", start))
    # معالج /cancel عالمي لإيقاف أي مهمة جارية
    app.add_handler(CommandHandler("cancel", cancel_operation))
    # معالجات أزرار رئيسية عامة لضمان الاستجابة دائمًا
    # (يتم الاعتماد أساسًا على ConversationHandler للدخول إلى قسم تيليجرام)
    # معالجات عامة للبدء والرجوع لضمان الاستجابة حتى خارج حالة المحادثة
    app.add_handler(CallbackQueryHandler(start_proxy_setup, pattern='^start_proxy_setup$'))
    app.add_handler(CallbackQueryHandler(back_to_tg_menu, pattern='^back_to_tg_menu$'))
    app.add_handler(CallbackQueryHandler(back_to_proxy_option, pattern='^back_to_proxy_option$'))
    app.add_handler(CallbackQueryHandler(back_to_proxy_setup, pattern='^back_to_proxy_setup$'))
    logger.info("✅ تم إضافة المعالجات الأساسية")

    # --- معالج قسم تيليجرام (الإعداد الأولي) ---
    logger.info("🛠️ إعداد معالج التليجرام...")
    logger.info("🔧 بدء إنشاء ConversationHandler...")
    telegram_setup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_telegram_menu, pattern='^main_telegram$')],
        states={
            TELEGRAM_MENU: [
                CallbackQueryHandler(start_proxy_setup, pattern='^start_proxy_setup$'),
            ],
            SELECT_PROXY_OPTION: [
                CallbackQueryHandler(process_proxy_option, pattern='^(use_proxy|skip_proxy)$'),
                CallbackQueryHandler(back_to_tg_menu, pattern='^back_to_tg_menu$'),
            ],
            ENTER_PROXY_LINKS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_proxy_links),
                CallbackQueryHandler(back_to_proxy_option, pattern='^back_to_proxy_option$')
            ],
            SELECT_CATEGORY: [
                CallbackQueryHandler(process_category_selection, pattern='^cat_'),
                CallbackQueryHandler(back_to_proxy_setup, pattern='^back_to_proxy_setup$')
            ],
            SELECT_METHOD: [
                # هذه الحالة تنتهي المحادثة وتنتقل للمعالجات الخارجية
                # أزرار method_* يتم معالجتها بواسطة ConversationHandlers الأخرى
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_setup, pattern='^cancel_setup$'),
            CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'),
            CommandHandler('cancel', cancel_operation),
        ],
        per_user=True,
        per_chat=False,
        per_message=False,
    )
    
    # --- إضافة جميع المعالجات إلى التطبيق ---
    logger.info("🔧 إضافة معالج إعداد التليجرام...")
    app.add_handler(telegram_setup_conv)
    logger.info("✅ تم إضافة معالج التليجرام")
    
    # --- معالجات البريد الإلكتروني ---
    logger.info("📧 فحص معالج البريد الإلكتروني...")
    if email_conv_handler: 
        app.add_handler(email_conv_handler)
        logger.info("✅ معالج البريد الإلكتروني")
    else:
        logger.info("ℹ️ معالج البريد الإلكتروني غير متاح")
    
    # --- معالجات تقارير تيليجرام ---
    logger.info("📱 إضافة معالجات التقارير...")
    
    app.add_handler(peer_report_conv)
    logger.info("✅ معالج تقارير الأعضاء")
    
    app.add_handler(message_report_conv)
    logger.info("✅ معالج تقارير الرسائل")
    
    app.add_handler(photo_report_conv)
    logger.info("✅ معالج تقارير الصور")
    
    app.add_handler(sponsored_report_conv)
    logger.info("✅ معالج التقارير الممولة")
    
    app.add_handler(mass_report_conv)
    logger.info("✅ معالج التقارير الجماعية")

    app.add_handler(bot_messages_report_conv)
    logger.info("✅ معالج بلاغ رسائل البوت")
    
    # --- معالجات الدعم ---
    logger.info("🔧 إضافة معالجات الدعم...")
    if register_support_handlers: 
        register_support_handlers(app)
        logger.info("✅ تم إضافة معالجات الدعم")
    else:
        logger.info("ℹ️ معالجات الدعم غير متاحة")
    
    # --- إضافة المعالجات العامة في النهاية ---
    logger.info("🔧 إضافة المعالجات العامة...")
    app.add_handler(CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'))
    logger.info("✅ تم إضافة المعالجات العامة")
    
    logger.info("🎉 اكتمل تحميل جميع المعالجات!")
    logger.info("🚀 البوت جاهز ويبدأ التشغيل...")
    logger.info("🔗 رابط البوت: @AAAK6BOT")
    logger.info("✅ نظام Socks5 محمل وجاهز للاختبار")
    
    app.run_polling()

if __name__ == '__main__':
    main()