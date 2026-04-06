# S9MY Auto Deposit Bot

Telegram bot untuk 99LAJU Auto Deposit System.

## Flow

1. **Menu Utama** - Daftar ID / Cara Cuci / Game ID / Promosi / Hubungi CS
2. **Auto Deposit** - Username → Amount → Bank (Affin/RHB) → Promo → Upload Resit
3. **CS Actions** - Approve/Reject deposit
4. **Game ID** - Get game ID & password selepas deposit berjaya

## Setup

```bash
cp .env.example .env
# Edit .env dengan credentials anda
npm install
npm run dev
```

## Environment Variables

- `BOT_TOKEN` - Telegram bot token dari @BotFather
- `ADMIN_ID` - Telegram user ID untuk CS/admin
- `BANK_ACCOUNTS` - JSON string untuk bank details

## Bot Commands

- `/start` - Mulakan bot, show main menu
- `/help` - Bantuan
- `/approve <reply_id>` - Approve deposit (admin only)
- `/reject <reply_id>` - Reject deposit (admin only)