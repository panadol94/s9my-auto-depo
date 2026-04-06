# S9MY Auto Deposit Bot

Telegram bot platform untuk **99LAJU Auto Deposit System** — multi-tenant, Flask webhook, PostgreSQL.

## Architecture

Same pattern as scanner bot (boda8):
- **Flask** webhook mode (not polling)
- **PostgreSQL 15** persistent storage
- **Multi-tenant** — one deployment, multiple bots via `/addbot`
- **Customizable messages** — `/setstart`, `/setdepositsuccess`, `/setdepositreject`
- **Admin group** — CS approve/reject deposits
- **Docker Compose** — bot + postgres

## Quick Start (Coolify)

1. **Create Resource** → Docker Compose → connect `panadol94/s9my-auto-depo`
2. **Set Environment**:
   - `PUBLIC_BASE_URL` = your Coolify domain (e.g. `https://s9my.example.com`)
   - `DATABASE_URL` = auto from compose
3. **Deploy**
4. **Register bot**: Send `/addbot <BOT_TOKEN>` to any registered bot
5. **Configure**: `/settings` to see all options

## Bot Commands

### User
| Command | Description |
|---------|-------------|
| `/start` | Register & show menu |
| `/help` | Help |

### Admin/Owner
| Command | Description |
|---------|-------------|
| `/addbot <token>` | Register new bot |
| `/settings` | Settings panel + stats |
| `/setadmingroup` | Set CS group (run in group) |
| `/addadmin <uid>` | Add CS admin |
| `/removeadmin <uid>` | Remove CS admin |
| `/setstart` | Set welcome message (reply) |
| `/setdepositsuccess` | Set approve message (reply) |
| `/setdepositreject` | Set reject message (reply) |
| `/setbank` | Configure bank accounts |
| `/setmindeposit <amt>` | Set min deposit |
| `/setaffiliate <link>` | Set affiliate link |
| `/setcslink <link>` | Set CS contact link |
| `/setgamelink <link>` | Set game website link |
| `/stats` | View statistics |

## Deposit Flow

```
/start → Daftar (affiliate link) → Username → Menu
  └─ Auto Deposit → Amount → Bank → Bank Details → Promo → Upload Resit
     → CS Approve/Reject → User Notification → Game ID → Play Now
```