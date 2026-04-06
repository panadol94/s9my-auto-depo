"""
S9MY Auto Deposit Bot
Telegram bot untuk 99LAJU Auto Deposit System
Full button-to-button flow
"""

import os
import uuid
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
MIN_DEPOSIT = int(os.getenv("MIN_DEPOSIT", "30"))

BANK_AFFIN = {
    "name": os.getenv("BANK_AFFIN_NAME", "FARHAN CATERING ENTERPRISE"),
    "account": os.getenv("BANK_AFFIN_ACCOUNT", "100180018799"),
}
BANK_RHB = {
    "name": os.getenv("BANK_RHB_NAME", "FARHAN CATERING ENTERPRISE"),
    "account": os.getenv("BANK_RHB_ACCOUNT", "25305200039496"),
}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

AFFILIATE_LINK = os.getenv("AFFILIATE_LINK", "https://99laju.net/register?affiliate=911295")

# ============ STORAGE ============
registered_users = {}   # user_id -> {"username": ..., "registered_at": ...}
user_deposits = {}      # user_id -> {"step": ..., "data": {...}}
pending_deposits = {}   # deposit_id -> {"user_id": ..., "data": {...}, "status": ...}

# ============ PERSISTENT BOTTOM KEYBOARD ============

def kb_reply():
    """Persistent reply keyboard at bottom of chat"""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🏠 Menu Utama"), KeyboardButton("Auto Deposit 💰")]],
        resize_keyboard=True,
        is_persistent=True,
    )

# ============ KEYBOARDS ============

def kb_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Auto Deposit", callback_data="auto_deposit")],
        [InlineKeyboardButton("🧼 Cara Cuci", callback_data="cara_cuci")],
        [InlineKeyboardButton("🎮 Cari Game ID", callback_data="game_id")],
        [InlineKeyboardButton("🎁 Claim Promotion", callback_data="claim_promo")],
        [InlineKeyboardButton("📊 Winning Record", callback_data="winning_record")],
        [InlineKeyboardButton("💬 Hubungi CS", callback_data="hubungi_cs")],
    ])

def kb_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_utama")],
    ])

def kb_home_deposit():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_utama")],
        [InlineKeyboardButton("💰 Auto Deposit", callback_data="auto_deposit")],
    ])

def kb_amounts():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("RM30", callback_data="amt_30"), InlineKeyboardButton("RM50", callback_data="amt_50")],
        [InlineKeyboardButton("RM100", callback_data="amt_100"), InlineKeyboardButton("RM200", callback_data="amt_200")],
        [InlineKeyboardButton("RM500", callback_data="amt_500"), InlineKeyboardButton("RM1000", callback_data="amt_1000")],
        [InlineKeyboardButton("✏️ Custom Amount", callback_data="amt_custom")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_utama")],
    ])

def kb_banks():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 Affin Bank", callback_data="bank_affin")],
        [InlineKeyboardButton("🏦 RHB Bank", callback_data="bank_rhb")],
        [InlineKeyboardButton("🔙 Back", callback_data="auto_deposit")],
    ])

def kb_promos():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 RM50 Free RM60 (120%)", callback_data="promo_rm50")],
        [InlineKeyboardButton("👑 RM100 Free RM120 (120%)", callback_data="promo_rm100")],
        [InlineKeyboardButton("1️⃣ 1st Dep - 50% Welcome", callback_data="promo_1st_50")],
        [InlineKeyboardButton("2️⃣ 2nd Dep - 100% Welcome", callback_data="promo_2nd_100")],
        [InlineKeyboardButton("🧧 15% Daily Bonus", callback_data="promo_daily_15")],
        [InlineKeyboardButton("💰 6% Unlimited", callback_data="promo_unlimited_6")],
        [InlineKeyboardButton("💰 10% Unlimited (10pm-6am)", callback_data="promo_unlimited_10")],
        [InlineKeyboardButton("🍀 No Claim (x1 TO)", callback_data="promo_no_claim")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_bank")],
    ])

def kb_cs_actions(dep_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"cs_approve_{dep_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"cs_reject_{dep_id}"),
        ],
    ])

PROMO_NAMES = {
    "promo_rm50": "👑 120% Welcome (RM50→Free RM60)",
    "promo_rm100": "👑 120% Welcome (RM100→Free RM120)",
    "promo_1st_50": "1️⃣ 1st Dep 50% Welcome",
    "promo_2nd_100": "2️⃣ 2nd Dep 100% Welcome",
    "promo_daily_15": "🧧 15% Daily Bonus",
    "promo_unlimited_6": "💰 6% Unlimited",
    "promo_unlimited_10": "💰 10% Unlimited (10pm-6am)",
    "promo_no_claim": "🍀 No Claim (x1 TO)",
}

# ============ HELPERS ============

def get_or_init_deposit(user_id, step="amount"):
    if user_id not in user_deposits:
        user_deposits[user_id] = {"step": step, "data": {}}
    if user_id in registered_users:
        user_deposits[user_id]["data"]["username"] = registered_users[user_id]["username"]
    return user_deposits[user_id]

# ============ HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id in registered_users:
        name = registered_users[user_id]["username"]
        await update.message.reply_text(
            f"🎰 ✨ SELAMAT KEMBALI, {name}! ✨ 🎰\n"
            f"🤖 Auto Deposit Bot — Laju, Mudah, 24/7!\n\n👇 Pilih pilihan di bawah:",
            reply_markup=kb_main_menu()
        )
        # Send persistent bottom keyboard
        await update.message.reply_text("⬇️", reply_markup=kb_reply())
    else:
        user_deposits[user_id] = {"step": "register", "data": {}}
        await update.message.reply_text(
            f"🆕 Daftar Sekarang di sini 👇\n"
            f"🔗 {AFFILIATE_LINK}\n\n"
            f"🧑 Sila masukkan Username 99LAJU anda :",
            reply_markup=kb_reply()
        )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *BANTUAN S9MY*\n\n"
        "• 💰 Auto Deposit — Deposit dana\n"
        "• 🎮 Game ID — Dapatkan ID game\n"
        "• 🎁 Claim Promo — Tuntut bonus\n"
        "• 💬 Hubungi CS — Chat CS\n\n"
        "Tekan /start untuk mula.",
        parse_mode="Markdown", reply_markup=kb_home_deposit()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # --- MENU UTAMA ---
    if data == "menu_utama":
        name = registered_users.get(user_id, {}).get("username", "")
        label = f"👤 {name}\n\n" if name else ""
        await query.edit_message_text(f"🏠 MENU UTAMA\n\n{label}Sila pilih:", reply_markup=kb_main_menu())

    # --- AUTO DEPOSIT ---
    elif data == "auto_deposit":
        dep = get_or_init_deposit(user_id, "amount")
        dep["step"] = "amount"
        dep["data"] = {"username": dep["data"].get("username", "")}
        await query.edit_message_text(
            f"💰 *AUTO DEPOSIT*\n\nMinimum deposit: RM{MIN_DEPOSIT}\nSila pilih jumlah deposit:",
            parse_mode="Markdown", reply_markup=kb_amounts()
        )

    # --- AMOUNT BUTTONS ---
    elif data.startswith("amt_"):
        dep = get_or_init_deposit(user_id)
        if data == "amt_custom":
            dep["step"] = "custom_amount"
            await query.edit_message_text(
                f"✏️ *Custom Amount*\n\nTaipkan jumlah deposit (Min: RM{MIN_DEPOSIT}):",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="auto_deposit")]])
            )
        else:
            amount = int(data.replace("amt_", ""))
            dep["data"]["amount"] = amount
            dep["step"] = "bank"
            await query.edit_message_text(
                f"✅ Amount: *RM{amount}*\n\n🏦 Pilih bank untuk transfer:",
                parse_mode="Markdown", reply_markup=kb_banks()
            )

    # --- BANK SELECTION ---
    elif data in ("bank_affin", "bank_rhb"):
        bank = BANK_AFFIN if data == "bank_affin" else BANK_RHB
        bank_name = "Affin Bank" if data == "bank_affin" else "RHB Bank"
        dep = get_or_init_deposit(user_id)
        dep["data"]["bank"] = bank_name
        dep["data"]["bank_info"] = bank
        dep["step"] = "promo"
        amt = dep["data"].get("amount", "?")
        await query.edit_message_text(
            f"🏦 *DETAIL AKAUN BANK*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏦 Bank: {bank_name}\n"
            f"👤 Nama: `{bank['name']}`\n"
            f"💳 Akaun: `{bank['account']}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Jumlah: *RM{amt}*\n\n"
            f"⚠️ Transfer tepat jumlah di atas.\n\nPilih promosi anda:",
            parse_mode="Markdown", reply_markup=kb_promos()
        )

    elif data == "back_to_bank":
        await query.edit_message_text(
            "🏦 *Pilih Bank*\n\nSila pilih bank untuk transfer:",
            parse_mode="Markdown", reply_markup=kb_banks()
        )

    # --- PROMO SELECTION ---
    elif data.startswith("promo_"):
        promo = PROMO_NAMES.get(data, "Unknown")
        dep = get_or_init_deposit(user_id)
        dep["data"]["promo"] = promo
        dep["step"] = "upload_resit"
        d = dep["data"]
        bi = d.get("bank_info", {})
        await query.edit_message_text(
            f"📋 *RINGKASAN DEPOSIT*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 Username: {d.get('username','?')}\n"
            f"💰 Amount: RM{d.get('amount','?')}\n"
            f"🏦 Bank: {d.get('bank','?')}\n"
            f"🎁 Promo: {promo}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏦 Transfer ke:\n"
            f"Nama: `{bi.get('name','?')}`\n"
            f"Akaun: `{bi.get('account','?')}`\n\n"
            f"📸 Sila upload screenshot resit transfer anda sekarang.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="auto_deposit")]])
        )

    # --- INFO PAGES ---
    elif data == "cara_cuci":
        await query.edit_message_text(
            "🧼 *CARA CUCI (TURNOVER)*\n\n"
            "1️⃣ Deposit minima RM30\n2️⃣ Claim promo\n"
            "3️⃣ Main game sehingga turnover dicapai\n4️⃣ BONUS masuk automatik\n\n"
            "💡 Cek promo untuk syarat turnover.",
            parse_mode="Markdown", reply_markup=kb_home_deposit()
        )
    elif data == "game_id":
        await query.edit_message_text(
            "🎮 *CARI GAME ID*\n\n"
            "1️⃣ Deposit & approve\n2️⃣ Login website S9MY\n"
            "3️⃣ Menu Game ID\n4️⃣ Copy ID & PW\n5️⃣ Play Now!\n\n"
            "📥 Download: https://99laju.net/",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎮 Play Now", url="https://99laju.net/")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_utama")],
            ])
        )
    elif data == "claim_promo":
        await query.edit_message_text(
            "🎁 *SEMUA PROMOSI S9MY*\n\n"
            "👑 120% Welcome (RM50→Free RM60)\n"
            "👑 120% Welcome (RM100→Free RM120)\n"
            "1️⃣ 1st Dep — 50% Welcome\n2️⃣ 2nd Dep — 100% Welcome\n"
            "🧧 15% Daily Bonus\n💰 6% Unlimited\n"
            "💰 10% Unlimited (10pm-6am)\n🍀 No Claim (x1 TO)\n\n"
            "💡 Pilih promo semasa deposit!",
            parse_mode="Markdown", reply_markup=kb_home_deposit()
        )
    elif data == "winning_record":
        await query.edit_message_text(
            "📊 *WINNING RECORD*\n\n"
            "1️⃣ Login website S9MY\n2️⃣ Profile → Wallet\n3️⃣ Semak transaksi\n\n"
            "Ada soalan? Hubungi CS!",
            parse_mode="Markdown", reply_markup=kb_home_deposit()
        )
    elif data == "hubungi_cs":
        await query.edit_message_text(
            "💬 *HUBUNGI CS*\n\nTekan button untuk chat CS:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Chat CS", url="https://t.me/m/4ujBD3wnZmI1")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_utama")],
            ])
        )

    # --- CS APPROVE ---
    elif data.startswith("cs_approve_"):
        dep_id = data.replace("cs_approve_", "")
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Admin only!", show_alert=True)
            return
        if dep_id not in pending_deposits:
            await query.answer("⚠️ Deposit not found.", show_alert=True)
            return
        dep = pending_deposits[dep_id]
        dep["status"] = "approved"
        d = dep["data"]
        try:
            await context.bot.send_message(
                chat_id=dep["user_id"],
                text=(
                    f"✅ *DEPOSIT BERJAYA!* 🎉\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 Username: {d.get('username','?')}\n"
                    f"💰 Amount: RM{d.get('amount','?')}\n"
                    f"🎁 Promo: {d.get('promo','?')}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Sila login untuk dapatkan Game ID!\n"
                    f"Semoga Bos menang beribu-ribu! 🍀"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎮 Dapatkan Game ID", callback_data="game_id")],
                    [InlineKeyboardButton("🎮 Play Now!", url="https://99laju.net/")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_utama")],
                ])
            )
        except Exception as e:
            logger.error(f"Notify user failed: {e}")
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n✅ *APPROVED* at {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="Markdown"
        )

    # --- CS REJECT ---
    elif data.startswith("cs_reject_"):
        dep_id = data.replace("cs_reject_", "")
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Admin only!", show_alert=True)
            return
        if dep_id not in pending_deposits:
            await query.answer("⚠️ Deposit not found.", show_alert=True)
            return
        dep = pending_deposits[dep_id]
        dep["status"] = "rejected"
        try:
            await context.bot.send_message(
                chat_id=dep["user_id"],
                text="❌ *DEPOSIT DITOLAK*\n\n‼️ Maaf, deposit ada masalah.\nSila hubungi CS. 🙏",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Hubungi CS", url="https://t.me/m/4ujBD3wnZmI1")],
                    [InlineKeyboardButton("💰 Cuba Lagi", callback_data="auto_deposit")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_utama")],
                ])
            )
        except Exception as e:
            logger.error(f"Notify user failed: {e}")
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n❌ *REJECTED* at {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="Markdown"
        )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    # Handle persistent reply keyboard buttons
    if text == "🏠 Menu Utama":
        name = registered_users.get(user_id, {}).get("username", "")
        label = f"👤 {name}\n\n" if name else ""
        await update.message.reply_text(
            f"🏠 MENU UTAMA\n\n{label}Sila pilih:",
            reply_markup=kb_main_menu()
        )
        return
    elif text == "Auto Deposit 💰":
        dep = get_or_init_deposit(user_id, "amount")
        dep["step"] = "amount"
        dep["data"] = {"username": dep["data"].get("username", "")}
        await update.message.reply_text(
            f"💰 *AUTO DEPOSIT*\n\nMinimum deposit: RM{MIN_DEPOSIT}\nSila pilih jumlah deposit:",
            parse_mode="Markdown", reply_markup=kb_amounts()
        )
        return

    if user_id not in user_deposits:
        await update.message.reply_text("Sila tekan /start untuk mula.", reply_markup=kb_reply())
        return

    dep = user_deposits[user_id]
    step = dep.get("step")

    if step == "register":
        registered_users[user_id] = {"username": text, "registered_at": datetime.now().isoformat()}
        user_deposits.pop(user_id, None)
        await update.message.reply_text(
            f"✅ *Berjaya Didaftarkan!*\n\n👤 Username: *{text}*\n\nSelamat datang ke S9MY! 🎰\nPilih pilihan di bawah:",
            parse_mode="Markdown", reply_markup=kb_main_menu()
        )
        await update.message.reply_text("⬇️", reply_markup=kb_reply())

    elif step == "custom_amount":
        try:
            amount = int(text)
            if amount < MIN_DEPOSIT:
                await update.message.reply_text(
                    f"❌ Minimum RM{MIN_DEPOSIT}. Cuba lagi:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="auto_deposit")]])
                )
                return
            dep["data"]["amount"] = amount
            dep["step"] = "bank"
            await update.message.reply_text(
                f"✅ Amount: *RM{amount}*\n\n🏦 Pilih bank:",
                parse_mode="Markdown", reply_markup=kb_banks()
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Nombor tidak sah. Contoh: 50",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="auto_deposit")]])
            )
    else:
        await update.message.reply_text("Sila tekan /start untuk mula.", reply_markup=kb_reply())

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_deposits or user_deposits[user_id].get("step") != "upload_resit":
        await update.message.reply_text("⚠️ Sila ikut flow deposit.", reply_markup=kb_home_deposit())
        return

    d = user_deposits[user_id]["data"]
    dep_id = str(uuid.uuid4())[:8]

    pending_deposits[dep_id] = {
        "user_id": user_id, "data": d, "status": "pending",
        "created_at": datetime.now().isoformat(),
    }

    admin_text = (
        f"📥 *DEPOSIT BARU!* #{dep_id}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Username: {d.get('username','?')}\n"
        f"💰 Amount: RM{d.get('amount','?')}\n"
        f"🏦 Bank: {d.get('bank','?')}\n"
        f"🎁 Promo: {d.get('promo','?')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🆔 User: {user_id}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id, photo=update.message.photo[-1].file_id,
                caption=admin_text, parse_mode="Markdown",
                reply_markup=kb_cs_actions(dep_id)
            )
        except Exception as e:
            logger.error(f"Send to admin {admin_id} failed: {e}")

    await update.message.reply_text(
        f"✅ *RESIT DITERIMA!*\n\n🔖 ID: `#{dep_id}`\n\n"
        f"⏳ CS akan semak & approve. Tunggu notifikasi ya! 💬",
        parse_mode="Markdown", reply_markup=kb_home_deposit()
    )
    del user_deposits[user_id]

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

def main():
    logger.info("Starting S9MY Auto Deposit Bot...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
