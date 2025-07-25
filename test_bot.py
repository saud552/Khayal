#!/usr/bin/env python3
"""
نسخة مبسطة من البوت للاختبار السريع
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إعدادات البوت من config.py
BOT_TOKEN = '7557280783:AAF44S35fdkcURM4j4Rp5-OOkASZ3_uCSR4'
OWNER_ID = 985612253

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دالة /start"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ هذا البوت خاص بالمالك فقط.")
        return
    
    keyboard = [
        [InlineKeyboardButton("🛠️ إعداد التليجرام", callback_data="setup_telegram")],
        [InlineKeyboardButton("📧 إعداد البريد الإلكتروني", callback_data="setup_email")],
        [InlineKeyboardButton("🔧 الدعم الخاص", callback_data="private_support")]
    ]
    
    await update.message.reply_text(
        "🎯 <b>مرحباً بك في بوت الإبلاغ المطور</b>\n\n"
        "🔥 <b>النظام الجديد يدعم:</b>\n"
        "• بروكسيات Socks5 (بدلاً من MTProto)\n"
        "• تحليل IP:PORT مباشر\n"
        "• فحص متطور للجودة\n\n"
        "اختر الخدمة المطلوبة:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def setup_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعداد التليجرام مع نظام Socks5"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📡 استخدام بروكسي Socks5", callback_data="use_socks5")],
        [InlineKeyboardButton("⏭️ تخطي (اتصال مباشر)", callback_data="skip_proxy")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(
        "🌐 <b>إعداد نظام البروكسي الجديد</b>\n\n"
        "🔄 <b>تم التحديث:</b>\n"
        "• ❌ إزالة نظام MTProto القديم\n"
        "• ✅ تفعيل نظام Socks5 الجديد\n"
        "• 🚀 أداء أفضل وأكثر استقراراً\n\n"
        "هل تريد استخدام بروكسيات Socks5؟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def use_socks5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب بروكسيات Socks5"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🌐 <b>إدخال بروكسيات Socks5</b>\n\n"
        "أرسل بروكسيات Socks5 (كل بروكسي في سطر):\n\n"
        "📌 <b>التنسيق الجديد:</b>\n"
        "<code>159.203.61.169:1080\n"
        "96.126.96.163:9090\n"
        "139.59.1.14:1080</code>\n\n"
        "⚠️ الحد الأقصى: 50 بروكسي\n"
        "✅ سيتم فحصها تلقائياً",
        parse_mode="HTML"
    )

async def skip_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تخطي البروكسي"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "✅ <b>تم اختيار الاتصال المباشر</b>\n\n"
        "🔥 النظام جاهز للاستخدام!\n"
        "سيتم استخدام الاتصال المباشر بدون بروكسي.\n\n"
        "💡 يمكنك إضافة بروكسيات Socks5 لاحقاً لتحسين الأداء.",
        parse_mode="HTML"
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "setup_telegram":
        await setup_telegram(update, context)
    elif query.data == "use_socks5":
        await use_socks5(update, context)
    elif query.data == "skip_proxy":
        await skip_proxy(update, context)
    elif query.data == "main_menu":
        await start(update, context)
    else:
        await query.edit_message_text(
            f"🔧 <b>قيد التطوير</b>\n\n"
            f"الوظيفة '{query.data}' قيد التطوير.\n"
            f"✅ نظام Socks5 جاهز للاختبار!",
            parse_mode="HTML"
        )

def main():
    """تشغيل البوت"""
    print("🚀 بدء تشغيل البوت المحدث...")
    
    # إنشاء التطبيق
    app = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("✅ البوت جاهز ويعمل...")
    print("🔗 رابط البوت: @AAAK6BOT")
    print("🎯 اختبر نظام Socks5 الجديد!")
    
    # تشغيل البوت
    app.run_polling()

if __name__ == '__main__':
    main()