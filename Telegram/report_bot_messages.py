import asyncio
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
    CommandHandler,
)

from .common import cancel_operation, REPORT_TYPES
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from config import API_ID, API_HASH

# States
(
    SELECT_REASON,
    ENTER_BOT_USERNAME,
    ENTER_DETAILS,
    ENTER_REPORT_COUNT,
    ENTER_MSG_LIMIT,
    ENTER_DELAY,
    CONFIRM_START,
) = range(70, 77)

async def start_bot_messages_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["method_type"] = "bot_messages"

    keyboard = [[InlineKeyboardButton(r[0], callback_data=f"reason_{k}")] for k, r in REPORT_TYPES.items()]
    keyboard.append([InlineKeyboardButton("إلغاء ❌", callback_data="cancel")])
    
    await query.edit_message_text(
        "🤖 <b>طريقة الإبلاغ عن رسائل بوت</b>\n\n"
        "اختر سبب الإبلاغ:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_REASON

async def select_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reason_num = int(query.data.split("_")[1])
    context.user_data["reason_obj"] = REPORT_TYPES[reason_num][1]
    
    await query.edit_message_text(
        "🤖 <b>إدخال يوزر البوت</b>\n\n"
        "أرسل يوزر البوت المستهدف (مثال: @examplebot)",
        parse_mode="HTML"
    )
    return ENTER_BOT_USERNAME

async def process_bot_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    if username.startswith("https://t.me/"):
        username = username.split("/")[-1]
    if not username.startswith("@"):
        username = "@" + username
    context.user_data["bot_username"] = username
    
    await update.message.reply_text(
        "💬 <b>التفاصيل الإضافية</b>\n\n"
        "أرسل رسالة تفصيلية للبلاغ (أو أرسل /skip للتخطي):",
        parse_mode="HTML"
    )
    return ENTER_DETAILS

async def process_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() != '/skip':
        context.user_data["message"] = update.message.text
    else:
        context.user_data["message"] = ""

    keyboard = [
        [InlineKeyboardButton("1 مرة", callback_data="count_1")],
        [InlineKeyboardButton("2 مرات", callback_data="count_2")],
        [InlineKeyboardButton("3 مرات", callback_data="count_3")],
        [InlineKeyboardButton("مخصص", callback_data="count_custom")]
    ]
    await update.message.reply_text(
        "🔄 <b>عدد مرات الإبلاغ</b>\n\n"
        "اختر عدد مرات الإبلاغ من كل حساب:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_REPORT_COUNT

async def process_report_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "count_custom":
        await query.edit_message_text(
            "🔢 <b>عدد مخصص</b>\n\n"
            "أدخل عدد مرات الإبلاغ من كل حساب:",
            parse_mode="HTML"
        )
        return ENTER_REPORT_COUNT

    count = int(query.data.split("_")[1])
    context.user_data["reports_per_account"] = count

    keyboard = [
        [InlineKeyboardButton("10 رسائل", callback_data="limit_10")],
        [InlineKeyboardButton("20 رسالة", callback_data="limit_20")],
        [InlineKeyboardButton("50 رسالة", callback_data="limit_50")],
        [InlineKeyboardButton("مخصص", callback_data="limit_custom")]
    ]
    await query.edit_message_text(
        "🔢 <b>عدد الرسائل</b>\n\n"
        "اختر عدد آخر الرسائل (من البوت) التي تريد الإبلاغ عنها من كل حساب:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_MSG_LIMIT

async def custom_report_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text)
        if count <= 0:
            await update.message.reply_text("❌ يجب أن يكون العدد أكبر من الصفر.")
            return ENTER_REPORT_COUNT
        context.user_data["reports_per_account"] = count
    except ValueError:
        await update.message.reply_text("❌ أدخل رقمًا صحيحًا فقط.")
        return ENTER_REPORT_COUNT

    keyboard = [
        [InlineKeyboardButton("10 رسائل", callback_data="limit_10")],
        [InlineKeyboardButton("20 رسالة", callback_data="limit_20")],
        [InlineKeyboardButton("50 رسالة", callback_data="limit_50")],
        [InlineKeyboardButton("مخصص", callback_data="limit_custom")]
    ]
    await update.message.reply_text(
        "🔢 <b>عدد الرسائل</b>\n\n"
        "اختر عدد آخر الرسائل (من البوت) التي تريد الإبلاغ عنها من كل حساب:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_MSG_LIMIT

async def process_msg_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "limit_custom":
        await query.edit_message_text(
            "🔢 <b>عدد مخصص</b>\n\n"
            "أدخل عدد الرسائل المطلوب الإبلاغ عنها لكل حساب:",
            parse_mode="HTML"
        )
        return ENTER_MSG_LIMIT

    limit = int(query.data.split("_")[1])
    context.user_data["msg_limit"] = limit

    keyboard = [
        [InlineKeyboardButton("5 ثواني", callback_data="delay_5")],
        [InlineKeyboardButton("10 ثواني", callback_data="delay_10")],
        [InlineKeyboardButton("30 ثواني", callback_data="delay_30")],
        [InlineKeyboardButton("مخصص", callback_data="delay_custom")]
    ]
    await query.edit_message_text(
        "⏱️ <b>الفاصل الزمني</b>\n\n"
        "اختر الفاصل الزمني بين عمليات الإبلاغ لكل حساب:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_DELAY

async def custom_msg_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        limit = int(update.message.text)
        if limit <= 0:
            await update.message.reply_text("❌ يجب أن يكون العدد أكبر من الصفر.")
            return ENTER_MSG_LIMIT
        context.user_data["msg_limit"] = limit
    except ValueError:
        await update.message.reply_text("❌ أدخل رقمًا صحيحًا فقط.")
        return ENTER_MSG_LIMIT

    keyboard = [
        [InlineKeyboardButton("5 ثواني", callback_data="delay_5")],
        [InlineKeyboardButton("10 ثواني", callback_data="delay_10")],
        [InlineKeyboardButton("30 ثواني", callback_data="delay_30")],
        [InlineKeyboardButton("مخصص", callback_data="delay_custom")]
    ]
    await update.message.reply_text(
        "⏱️ <b>الفاصل الزمني</b>\n\n"
        "اختر الفاصل الزمني بين عمليات الإبلاغ لكل حساب:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ENTER_DELAY

async def process_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "delay_custom":
        await query.edit_message_text(
            "⏳ <b>فاصل زمني مخصص</b>\n\n"
            "أدخل الفاصل الزمني (بالثواني):",
            parse_mode="HTML"
        )
        return ENTER_DELAY

    delay = int(query.data.split("_")[1])
    context.user_data["cycle_delay"] = delay

    # عرض ملخص وتأكيد
    cfg = context.user_data
    num_accounts = len(cfg.get("accounts", []))
    total_reports = num_accounts * cfg.get("msg_limit", 0) * cfg.get("reports_per_account", 1)
    
    summary = (
        f"📝 <b>ملخص العملية</b>\n\n"
        f"• البوت: {cfg.get('bot_username')}\n"
        f"• الرسائل/حساب (في كل تكرار): {cfg.get('msg_limit')}\n"
        f"• مرات التكرار/حساب: {cfg.get('reports_per_account')}\n"
        f"• الفاصل الزمني بين التكرارات: {cfg.get('cycle_delay')} ثانية\n"
        f"• إجمالي المستهدف: {total_reports}\n\n"
        f"هل تريد بدء العملية؟"
    )
    keyboard = [
        [InlineKeyboardButton("بدء العملية ✅", callback_data="confirm")],
        [InlineKeyboardButton("إلغاء ❌", callback_data="cancel")],
    ]
    await query.edit_message_text(
        summary,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM_START

async def custom_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        delay = int(update.message.text)
        if delay <= 0:
            await update.message.reply_text("❌ يجب أن يكون الفاصل الزمني أكبر من الصفر.")
            return ENTER_DELAY
        context.user_data["cycle_delay"] = delay
    except ValueError:
        await update.message.reply_text("❌ أدخل رقمًا صحيحًا فقط.")
        return ENTER_DELAY

    cfg = context.user_data
    num_accounts = len(cfg.get("accounts", []))
    total_reports = num_accounts * cfg.get("msg_limit", 0) * cfg.get("reports_per_account", 1)

    summary = (
        f"📝 <b>ملخص العملية</b>\n\n"
        f"• البوت: {cfg.get('bot_username')}\n"
        f"• الرسائل/حساب (في كل تكرار): {cfg.get('msg_limit')}\n"
        f"• مرات التكرار/حساب: {cfg.get('reports_per_account')}\n"
        f"• الفاصل الزمني بين التكرارات: {cfg.get('cycle_delay')} ثانية\n"
        f"• إجمالي المستهدف: {total_reports}\n\n"
        f"هل تريد بدء العملية؟"
    )
    keyboard = [
        [InlineKeyboardButton("بدء العملية ✅", callback_data="confirm")],
        [InlineKeyboardButton("إلغاء ❌", callback_data="cancel")],
    ]
    await update.message.reply_text(
        summary,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM_START

async def confirm_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["active"] = True

    cfg = context.user_data
    num_accounts = len(cfg.get("accounts", []))
    total_reports = num_accounts * cfg.get("msg_limit", 0) * cfg.get("reports_per_account", 1)
    est_time = (cfg.get("cycle_delay", 1) * cfg.get("reports_per_account", 1))

    msg = await query.edit_message_text(
        f"⏳ <b>جاري بدء عملية الإبلاغ عن رسائل البوت...</b>\n\n"
        f"• عدد الحسابات: {num_accounts}\n"
        f"• إجمالي الرسائل المستهدفة (تقريبي): {total_reports}\n"
        f"• الوقت المتوقع بين تكرارات الحساب: {est_time:.1f} دقيقة\n\n"
        "سيتم تحديث التقدم هنا...",
        parse_mode="HTML"
    )
    context.user_data["progress_message"] = msg

    asyncio.create_task(run_bot_messages_report(update, context))
    return ConversationHandler.END

async def run_bot_messages_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = context.user_data
    sessions = cfg.get("accounts", [])
    reason_obj = cfg.get("reason_obj")
    bot_username = cfg.get("bot_username")
    msg_limit = cfg.get("msg_limit", 10)
    cycle_delay = cfg.get("cycle_delay", 5)
    detail_message = cfg.get("message", "")
    reports_per_account = cfg.get("reports_per_account", 1)

    # تتبع
    cfg.setdefault("lock", asyncio.Lock())
    cfg["progress_success"] = 0
    cfg["progress_failed"] = 0

    async def report_for_session(session):
        if not context.user_data.get("active", True):
            return
        client = TelegramClient(StringSession(session["session"]), API_ID, API_HASH)
        try:
            await client.connect()
            entity = await client.get_entity(bot_username)

            for rep in range(reports_per_account):
                if not context.user_data.get("active", True):
                    break

                # جلب آخر الرسائل من البوت فقط (قد تختلف من حساب لآخر)
                bot_messages = []
                async for m in client.iter_messages(entity, limit=msg_limit):
                    if m.from_id and getattr(m.from_id, 'user_id', None) == entity.id:
                        bot_messages.append(m.id)
                if not bot_messages:
                    async with cfg["lock"]:
                        cfg["progress_failed"] += 1
                else:
                    # طلب الخيارات أولاً
                    result = await client(functions.messages.ReportRequest(
                        peer=entity,
                        id=bot_messages,
                        option=b'',
                        message=''
                    ))

                    chosen_option = None
                    if isinstance(result, types.ReportResultChooseOption):
                        # محاولة المطابقة بالاسم كما في common.py
                        for opt in result.options:
                            if reason_obj.__class__.__name__.lower().find(opt.text.lower()) != -1 or reason_obj.__class__.__name__.lower() == opt.text.lower():
                                chosen_option = opt.option
                                break
                        if not chosen_option and result.options:
                            chosen_option = result.options[0].option

                        await client(functions.messages.ReportRequest(
                            peer=entity,
                            id=bot_messages,
                            option=chosen_option or b'',
                            message=detail_message
                        ))
                    async with cfg["lock"]:
                        cfg["progress_success"] += len(bot_messages)

                # تأخير بين تكرارات الحساب الواحد
                if rep < reports_per_account - 1:
                    for _ in range(int(cycle_delay)):
                        if not context.user_data.get("active", True):
                            break
                        await asyncio.sleep(1)
        except Exception:
            async with cfg["lock"]:
                cfg["progress_failed"] += 1
        finally:
            if client and client.is_connected():
                await client.disconnect()

    # تشغيل كل حساب بشكل مستقل
    tasks = []
    for session in sessions:
        if not context.user_data.get("active", True):
            break
        t = asyncio.create_task(report_for_session(session))
        context.user_data.setdefault("tasks", []).append(t)
        tasks.append(t)

    for t in tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass

    # تحديث نهائي
    async with cfg["lock"]:
        success = cfg.get("progress_success", 0)
        failed = cfg.get("progress_failed", 0)
    text = (
        f"✅ <b>اكتملت عملية إبلاغ رسائل البوت</b>\n\n"
        f"• الناجحة: {success}\n"
        f"• الفاشلة: {failed}"
    )
    try:
        await context.bot.edit_message_text(
            chat_id=cfg["progress_message"].chat_id,
            message_id=cfg["progress_message"].message_id,
            text=text,
            parse_mode="HTML"
        )
    except Exception:
        pass

    # عرض قائمة البداية
    try:
        start_keyboard = [
            [InlineKeyboardButton("📧 قسم بلاغات ايميل", callback_data="email_reports")],
            [InlineKeyboardButton("📢 قسم بلاغات تيليجرام", callback_data="main_telegram")]
        ]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👋 اختر القسم للبدء من جديد:",
            reply_markup=InlineKeyboardMarkup(start_keyboard)
        )
    except Exception:
        pass

bot_messages_report_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_bot_messages_report, pattern='^method_bot_messages$')],
    states={
        SELECT_REASON: [CallbackQueryHandler(select_reason, pattern='^reason_')],
        ENTER_BOT_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_bot_username)],
        ENTER_DETAILS: [MessageHandler(filters.TEXT | filters.COMMAND, process_details)],
        ENTER_REPORT_COUNT: [
            CallbackQueryHandler(process_report_count, pattern='^count_'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, custom_report_count)
        ],
        ENTER_MSG_LIMIT: [
            CallbackQueryHandler(process_msg_limit, pattern='^limit_'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, custom_msg_limit)
        ],
        ENTER_DELAY: [
            CallbackQueryHandler(process_delay, pattern='^delay_'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, custom_delay)
        ],
        CONFIRM_START: [
            CallbackQueryHandler(confirm_and_start, pattern='^confirm$'),
            CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_operation, pattern='^cancel$'),
        CallbackQueryHandler(cancel_operation, pattern='^back$'),
        CommandHandler('cancel', cancel_operation)
    ],
    per_user=True,
)