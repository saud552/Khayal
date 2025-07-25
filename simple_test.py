#!/usr/bin/env python3
"""
بوت اختبار بسيط لاختبار أزرار فئات الحسابات
"""

import sys
import os
import logging

# إضافة المجلد الرئيسي للمشروع إلى مسار بايثون
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# إعدادات البوت
from config import BOT_TOKEN, OWNER_ID
from Telegram.common import get_categories, get_accounts

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """القائمة الرئيسية"""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ هذا البوت مخصص للمالك فقط.")
        return

    keyboard = [
        [InlineKeyboardButton("📢 اختبار فئات الحسابات", callback_data="test_categories")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🧪 بوت اختبار أزرار فئات الحسابات",
        reply_markup=reply_markup
    )

async def test_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """اختبار عرض فئات الحسابات"""
    query = update.callback_query
    await query.answer()
    
    try:
        categories = get_categories()
        if not categories:
            await query.edit_message_text("❌ لا توجد فئات متاحة.")
            return
        
        keyboard = []
        for cat_id, name, count in categories:
            keyboard.append([InlineKeyboardButton(f"{name} ({count} حساب)", callback_data=f"cat_{cat_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")])
        
        await query.edit_message_text(
            "📂 <b>اختبار فئات الحسابات:</b>\n\nاختر فئة:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"خطأ في test_categories: {e}")
        await query.edit_message_text(f"❌ خطأ: {str(e)}")

async def test_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """اختبار اختيار فئة محددة"""
    query = update.callback_query
    await query.answer()
    
    try:
        category_id = int(query.data.split('_')[1])
        
        accounts = get_accounts(category_id)
        if not accounts:
            await query.edit_message_text("❌ لا توجد حسابات في هذه الفئة.")
            return
        
        context.user_data['selected_category'] = category_id
        context.user_data['accounts'] = accounts
        
        keyboard = [
            [InlineKeyboardButton("👤 بلاغ عضو", callback_data="method_peer")],
            [InlineKeyboardButton("💬 بلاغ رسالة", callback_data="method_message")],
            [InlineKeyboardButton("🖼️ صورة شخصية", callback_data="method_photo")],
            [InlineKeyboardButton("📢 إعلان ممول", callback_data="method_sponsored")],
            [InlineKeyboardButton("🔥 بلاغ جماعي", callback_data="method_mass")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="test_categories")],
        ]
        
        await query.edit_message_text(
            f"✅ <b>تم اختيار الفئة {category_id}</b>\n\n"
            f"📊 عدد الحسابات: {len(accounts)}\n\n"
            f"🔥 اختر نوع الإبلاغ:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"خطأ في test_category_selection: {e}")
        await query.edit_message_text(f"❌ خطأ: {str(e)}")

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """العودة للبداية"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📢 اختبار فئات الحسابات", callback_data="test_categories")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🧪 بوت اختبار أزرار فئات الحسابات",
        reply_markup=reply_markup
    )

async def method_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج أزرار طرق الإبلاغ"""
    query = update.callback_query
    await query.answer()
    
    method = query.data.replace('method_', '')
    category = context.user_data.get('selected_category', 'غير محدد')
    accounts_count = len(context.user_data.get('accounts', []))
    
    await query.edit_message_text(
        f"🎯 <b>تم اختيار: {method}</b>\n\n"
        f"📊 الفئة: {category}\n"
        f"📱 عدد الحسابات: {accounts_count}\n\n"
        f"✅ الاختبار نجح! الأزرار تعمل بشكل صحيح."
    )

def main():
    """الدالة الرئيسية"""
    logger.info("🧪 بدء تشغيل بوت الاختبار...")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # المعالجات الأساسية
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(test_categories, pattern='^test_categories$'))
    app.add_handler(CallbackQueryHandler(test_category_selection, pattern='^cat_'))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern='^back_to_start$'))
    app.add_handler(CallbackQueryHandler(method_handler, pattern='^method_'))
    
    logger.info("✅ بوت الاختبار جاهز!")
    app.run_polling()

if __name__ == '__main__':
    main()