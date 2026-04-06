# S9MY Auto Deposit Bot

Telegram bot untuk **99LAJU Auto Deposit System** — automated deposit flow dengan inline keyboards.

## Features

- 🏠 **Menu Utama** — Daftar ID / Cara Cuci / Game ID / Promosi / Hubungi CS
- 💰 **Auto Deposit** — Username → Amount → Bank (Affin/RHB) → Promo → Upload Resit
- ✅ **CS Actions** — Approve/Reject deposit melalui inline buttons
- 🎮 **Game ID** — Get game ID & password selepas deposit berjaya
- 🎁 **Promotions** — 120% Welcome, Daily Bonus, Unlimited Bonus, dan lagi

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Mulakan bot, show main menu |
| `/help` | Bantuan |
| `/approve <user_id>` | Approve deposit (admin only) |
| `/reject <user_id>` | Reject deposit (admin only) |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token dari @BotFather | — |
| `ADMIN_IDS` | Comma-separated Telegram user IDs untuk CS/admin | — |
| `MIN_DEPOSIT` | Minimum deposit amount (RM) | `30` |
| `BANK_AFFIN_NAME` | Nama akaun Affin Bank | `FARHAN CATERING ENTERPRISE` |
| `BANK_AFFIN_ACCOUNT` | Nombor akaun Affin Bank | `100180018799` |
| `BANK_RHB_NAME` | Nama akaun RHB Bank | `FARHAN CATERING ENTERPRISE` |
| `BANK_RHB_ACCOUNT` | Nombor akaun RHB Bank | `25305200039496` |

## Deploy via Coolify

1. **Create New Resource** di Coolify → pilih **Docker Compose**
2. **Connect Repository** → `panadol94/s9my-auto-depo` (branch: `main`)
3. **Set Environment Variables** di Coolify dashboard:
   - `BOT_TOKEN` — token dari @BotFather
   - `ADMIN_IDS` — Telegram user ID admin (comma-separated)
   - Bank details jika nak tukar dari default
4. **Deploy** — Coolify akan build dan run container secara automatik

## Local Development

```bash
# Clone repo
git clone https://github.com/panadol94/s9my-auto-depo.git
cd s9my-auto-depo

# Setup environment
cp .env.example .env
# Edit .env dengan credentials anda

# Install & run
pip install -r requirements.txt
python bot.py
```

## Tech Stack

- **Python 3.11** — Runtime
- **python-telegram-bot 21.6** — Telegram Bot API
- **Docker** — Containerization
- **Coolify** — Deployment platform