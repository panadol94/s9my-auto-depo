"""
S9MY Auto Deposit Bot
Telegram bot untuk 99LAJU Auto Deposit System
"""

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Load env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
MIN_DEPOSIT = int(os.getenv("MIN_DEPOSIT", "30"))

BANK_AFFIN = {
    "name": os.getenv("BANK_AFFIN_NAME", "FARHAN CATERING ENTERPRISE"),
    "account": os.getenv("BANK_AFFIN_ACCOUNT", "100180018799"),
}

BANK_RHB = {
    "name": os.getenv("BANK_RHB_NAME", "FARHAN CATERING ENTERPRISE"),
    "account": os.getenv("BANK_RHB_ACCOUNT", "25305200039496"),
}

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ KEYBOARDS ============

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_utama")],
        [InlineKeyboardButton("💰 Auto Deposit", callback_data="auto_deposit")],
        [InlineKeyboardButton("🧼 Cara Cuci", callback_data="cara_cuci")],
        [InlineKeyboardButton("🎮 Game ID", callback_data="game_id")],
        [InlineKeyboardButton("🎁 Claim Promotion", callback_data="claim_promo")],
        [InlineKeyboardButton("📊 Customer Winning Record", callback_data="winning_record")],
        [InlineKeyboardButton("💬 Hubungi CS", callback_data="hubungi_cs")],
    ]
    return InlineKeyboardMarkup(keyboard)

def home_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🏘 Home Menu", callback_data="menu_utama")],
        [InlineKeyboardButton("💰 Auto Deposit", callback_data="auto_deposit")],
    ]
    return InlineKeyboardMarkup(keyboard)

def bank_selection_keyboard():
    keyboard = [
        [InlineKeyboardButton("🏦 Affin Bank", callback_data="bank_affin")],
        [InlineKeyboardButton("🏦 RHB Bank", callback_data="bank_rhb")],
        [InlineKeyboardButton("🔙 Back", callback_data="auto_deposit")],
    ]
    return InlineKeyboardMarkup(keyboard)

def promo_selection_keyboard():
    keyboard = [
        [InlineKeyboardButton("👑 Dep RM50 Free RM60 (120% Welcome)", callback_data="promo_rm50")],
        [InlineKeyboardButton("👑 Dep RM100 Free RM120 (120% Welcome)", callback_data="promo_rm100")],
        [InlineKeyboardButton("1️⃣ 1st Dep - 50% Welcome Bonus", callback_data="promo_1st_50")],
        [InlineKeyboardButton("2️⃣ 2nd Dep - 100% Welcome Bonus", callback_data="promo_2nd_100")],
        [InlineKeyboardButton("🧧 15% Daily Bonus", callback_data="promo_daily_15")],
        [InlineKeyboardButton("💰 6% Unlimited Bonus", callback_data="promo_unlimited_6")],
        [InlineKeyboardButton("💰 10% Unlimited Bonus (10pm-6am)", callback_data="promo_unlimited_10")],
        [InlineKeyboardButton("🍀 No Claim Promo (x1 Turnover)", callback_data="promo_no_claim")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_bank")],
    ]
    return InlineKeyboardMarkup(keyboard)

def confirmation_keyboard():
    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Upload Resit", callback_data="confirm_deposit")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="auto_deposit")],
    ]
    return InlineKeyboardMarkup(keyboard)

def cs_action_keyboard(deposit_id):
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"cs_approve_{deposit_id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"cs_reject_{deposit_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ============ USER DATA STORAGE ============

# In-memory storage for deposit flows
user_deposits = {}  # user_id -> deposit data

# ============ HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - show welcome and main menu"""
    welcome_text = """🎰 ✨ SELAMAT DATANG KE S9MY! ✨ 🎰
🤖 Auto Deposit Bot — Laju, Mudah, 24/7!

🏆 KENAPA PILIH S9MY? 🏆
✅ Deposit dalam 1 Minit ⚡
✅ Cashout dalam 3 Minit 💨
✅ Online 24/7 🌐
✅ Promo Terbaik Setiap Hari 🔥

👇 Pilih pilihan di bawah:"""

    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🆘 Bantuan

Guna menu di bawah untuk:
• 💰 Auto Deposit - Deposit dana ke akaun
• 🎮 Game ID - Dapatkan ID untuk main game
• 🎁 Claim Promotion - Tuntut bonus
• 💬 Hubungi CS - Berhubung dengan customer service

Untuk bantuan lanjut, hubungi CS kami."""
    await update.message.reply_text(help_text, reply_markup=home_menu_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all inline button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # ========== MENU UTAMA ==========
    if data == "menu_utama":
        welcome_text = """🏠 MENU UTAMA

Sila pilih:"""
        await query.edit_message_text(welcome_text, reply_markup=main_menu_keyboard())
    
    # ========== AUTO DEPOSIT FLOW ==========
    elif data == "auto_deposit":
        user_deposits[user_id] = {"step": "username", "data": {}}
        await query.edit_message_text(
            "💰 **AUTO DEPOSIT**\n\nSila masukkan username akaun S9MY anda:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_utama")]])
        )
    
    elif data == "cara_cuci":
        await query.edit_message_text(
            """🧼 **CARA CUCI (TURNOVER)**

Cara untuk qualify bagi bonus:
1. Buat deposit minima RM30
2. Claim promo yang tersedia
3. Main game sehingga jumlah turnover raggi
4. BONUS akan masuk secara automatik

💡 Tips: Cek balik promo untuk syarat turnover.""",
            parse_mode="Markdown",
            reply_markup=home_menu_keyboard()
        )
    
    elif data == "game_id":
        await query.edit_message_text(
            """🎮 **GAME ID**

Untuk mendapatkan Game ID:
1. Selesai deposit & approve
2. Login ke website S9MY
3. Pergi ke menu Game ID
4. Pilih game & copy ID & PW
5. Tekan Play Now untuk mula main

📥 Download app: https://99laju.net/""",
            parse_mode="Markdown",
            reply_markup=home_menu_keyboard()
        )
    
    elif data == "claim_promo":
        await query.edit_message_text(
            """🎁 **SEMUA PROMOSI**

👑 120% Welcome Bonus (Dep RM50-Free RM60)
👑 120% Welcome Bonus (Dep RM100-Free RM120)
1️⃣ 1st Deposit - 50% Welcome Bonus
2️⃣ 2nd Deposit - 100% Welcome Bonus
🧧 15% Daily Bonus
💰 6% Unlimited Bonus
💰 10% Unlimited Bonus (10pm-6am)
🍀 No Claim Promo (x1 Turnover)

Pilih promo semasa deposit!""",
            parse_mode="Markdown",
            reply_markup=home_menu_keyboard()
        )
    
    elif data == "winning_record":
        await query.edit_message_text(
            """📊 **CUSTOMER WINNING RECORD**

Untuk tengok rekod kemenangan:
• Login ke website S9MY
• Pergi ke Profile/Wallet
• Sini boleh tengok semua transaksi

有任何问题? Hubungi CS kami!""",
            parse_mode="Markdown",
            reply_markup=home_menu_keyboard()
        )
    
    elif data == "hubungi_cs":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Hubungi CS", url="https://t.me/m/4ujBD3wnZmI1")],
            [InlineKeyboardButton("🏘 Home Menu", callback_data="menu_utama")],
        ])
        await query.edit_message_text(
            "💬 **hubungungi CS**\n\nTekan button di bawah untuk chat dengan CS kami:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    
    # ========== BANK SELECTION ==========
    elif data in ["bank_affin", "bank_rhb"]:
        bank = BANK_AFFIN if data == "bank_affin" else BANK_RHB
        bank_name = "Affin Bank" if data == "bank_affin" else "RHB Bank"
        
        user_deposits[user_id]["data"]["bank"] = bank_name
        user_deposits[user_id]["data"]["bank_info"] = bank
        
        deposit_data = user_deposits[user_id]["data"]
        
        summary = f"""🏦 **Bank: {bank_name}**

Name: {bank['name']}
Account: {bank['account']}

💰 Amount: RM{deposit_data.get('amount', '?')}

Sila transfer ke akaun di atas, kemudian upload screenshot resit."""

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Saya Dah Transfer", callback_data="confirm_deposit")],
            [InlineKeyboardButton("🔙 Back", callback_data="auto_deposit")],
        ])
        
        await query.edit_message_text(summary, parse_mode="Markdown", reply_markup=keyboard)
    
    elif data == "back_to_bank":
        await query.edit_message_text(
            "🏦 **Pilih Bank**\n\nSila pilih bank untuk transfer:",
            parse_mode="Markdown",
            reply_markup=bank_selection_keyboard()
        )
    
    # ========== PROMO SELECTION ==========
    elif data.startswith("promo_"):
        promo_names = {
            "promo_rm50": "120% Welcome (RM50 Dep → Free RM60)",
            "promo_rm100": "120% Welcome (RM100 Dep → Free RM120)",
            "promo_1st_50": "1st Dep 50% Welcome Bonus",
            "promo_2nd_100": "2nd Dep 100% Welcome Bonus",
            "promo_daily_15": "15% Daily Bonus",
            "promo_unlimited_6": "6% Unlimited Bonus",
            "promo_unlimited_10": "10% Unlimited Bonus (10pm-6am)",
            "promo_no_claim": "No Claim Promo (x1 Turnover)",
        }
        promo_name = promo_names.get(data, "Unknown")
        user_deposits[user_id]["data"]["promo"] = promo_name
        
        deposit_data = user_deposits[user_id]["data"]
        bank = deposit_data.get("bank_info", {})
        bank_name = deposit_data.get("bank", "Unknown")
        
        summary = f"""📋 **Summary Deposit**

👤 Username: {deposit_data.get('username', '?')}
💰 Amount: RM{deposit_data.get('amount', '?')}
🏦 Bank: {bank_name}
🎁 Promo: {promo_name}

🏦 Account:
Name: {bank.get('name', '?')}
Account: {bank.get('account', '?')}

Sila transfer dan click button di bawah untuk upload resit."""

        await query.edit_message_text(summary, parse_mode="Markdown", reply_markup=confirmation_keyboard())
    
    elif data == "confirm_deposit":
        await query.edit_message_text(
            "📸 **Upload Resit**

Sila upload screenshot resit transfer anda.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="auto_deposit")]])
        )
    
    # ========== CS ACTIONS ==========
    elif data.startswith("cs_approve_"):
        deposit_id = data.replace("cs_approve_", "")
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Admin only!", show_alert=True)
            return
        
        success_msg = """✅ **Deposit Approved!**

💰 Deposit anda telah berjaya diuruskan.
Sila Login ke website kami untuk dapatkan Game ID anda.

Semoga Bos menang beribu ribuan! 🍀"""

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏘 Home Menu", callback_data="menu_utama")],
        ])
        await query.edit_message_text(success_msg, parse_mode="Markdown", reply_markup=keyboard)
        await query.answer("✅ Approved!")
    
    elif data.startswith("cs_reject_"):
        deposit_id = data.replace("cs_reject_", "")
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Admin only!", show_alert=True)
            return
        
        reject_msg = """❌ **Deposit Rejected**

‼️ Maaf, Deposit anda ada sikit masalah.
Sila hubungi CS kami untuk urusan deposit anda 🙏"""

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Hubungi CS", url="https://t.me/m/4ujBD3wnZmI1")],
            [InlineKeyboardButton("🏘 Home Menu", callback_data="menu_utama")],
        ])
        await query.edit_message_text(reject_msg, parse_mode="Markdown", reply_markup=keyboard)
        await query.answer("❌ Rejected!")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages - username and amount input"""
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if user_id not in user_deposits:
        await update.message.reply_text(
            "Sila tekan /start untuk mula.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    deposit = user_deposits[user_id]
    step = deposit.get("step")
    
    if step == "username":
        deposit["data"]["username"] = text
        deposit["step"] = "amount"
        
        await update.message.reply_text(
            f"✅ Username: **{text}**\n\n💰 Masukkan jumlah deposit (Min: RM{MIN_DEPOSIT}):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="auto_deposit")]])
        )
    
    elif step == "amount":
        try:
            amount = int(text)
            if amount < MIN_DEPOSIT:
                await update.message.reply_text(
                    f"❌ Minimum deposit adalah RM{MIN_DEPOSIT}. Sila masukkan semula:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="auto_deposit")]])
                )
                return
            
            deposit["data"]["amount"] = amount
            deposit["step"] = "done"
            
            # Show bank selection
            await update.message.reply_text(
                f"✅ Amount: **RM{amount}**\n\n🏦 Pilih bank untuk transfer:",
                parse_mode="Markdown",
                reply_markup=bank_selection_keyboard()
            )
        
        except ValueError:
            await update.message.reply_text(
                "❌ Sila masukkan nombor yang sah. Contoh: 50",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="auto_deposit")]])
            )

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads (receipts)"""
    user_id = update.message.from_user.id
    
    if user_id not in user_deposits:
        await update.message.reply_text("Sila tekan /start untuk mula.", reply_markup=main_menu_keyboard())
        return
    
    deposit = user_deposits[user_id]
    deposit_data = deposit.get("data", {})
    
    # Forward to admin group
    admin_text = f"""📥 **DEPOSIT BARU!**

👤 Username: {deposit_data.get('username', '?')}
💰 Amount: RM{deposit_data.get('amount', '?')}
🏦 Bank: {deposit_data.get('bank', '?')}
🎁 Promo: {deposit_data.get('promo', '?')}

🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

    # Send photo to all admins
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=update.message.photo[-1].file_id,
                caption=admin_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send to admin {admin_id}: {e}")
    
    await update.message.reply_text(
        "✅ Resit diterima! Mohon tunggu, CS kami akan semak dan approve/reject. 💬",
        reply_markup=home_menu_keyboard()
    )
    
    # Clear user deposit data
    del user_deposits[user_id]

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

# ============ ADMIN COMMANDS ==========

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /approve <user_id>")
        return
    
    await update.message.reply_text("✅ Deposit approved!")

async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /reject <user_id>")
        return
    
    await update.message.reply_text("❌ Deposit rejected!")

# ============ MAIN ==========

def main():
    logger.info("Starting S9MY Auto Deposit Bot...")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("reject", reject_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)
    
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
