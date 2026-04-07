import os, json, uuid, html, re, logging, time
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import requests
from flask import Flask, request, jsonify
import sqlalchemy as sa
from sqlalchemy import text

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# ---------------------------
# CONFIG
# ---------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("s9my")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var required")

APP_TZ_NAME = os.getenv("TZ", "Asia/Kuala_Lumpur")
LOCAL_TZ = ZoneInfo(APP_TZ_NAME) if ZoneInfo else None
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "3"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "7"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
SERVICE_NAME = os.getenv("SERVICE_NAME", "s9my-bot")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = os.getenv("OWNER_ID", "").strip()
TG_MAX_TEXT = 4096
TG_MAX_CAPTION = 1024

# ---------------------------
# FLASK & DB
# ---------------------------
app = Flask(__name__)
app.url_map.strict_slashes = False

engine = sa.create_engine(
    DATABASE_URL, pool_pre_ping=True, pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW, pool_recycle=1800, future=True,
)

TG_API = "https://api.telegram.org/bot{token}/{method}"
SESSION = requests.Session()

# ---------------------------
# DB INIT
# ---------------------------
def init_db():
    ddl = """
    CREATE EXTENSION IF NOT EXISTS pgcrypto;

    CREATE TABLE IF NOT EXISTS bots (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      token TEXT NOT NULL,
      bot_username TEXT,
      secret_token TEXT UNIQUE NOT NULL,
      owner_id BIGINT NOT NULL,
      admin_group_id BIGINT,
      min_deposit NUMERIC NOT NULL DEFAULT 30,
      affiliate_link TEXT DEFAULT 'https://99laju.net/register?affiliate=911295',
      bank_affin_name TEXT DEFAULT 'FARHAN CATERING ENTERPRISE',
      bank_affin_account TEXT DEFAULT '100180018799',
      bank_rhb_name TEXT DEFAULT 'FARHAN CATERING ENTERPRISE',
      bank_rhb_account TEXT DEFAULT '25305200039496',
      start_text TEXT,
      start_media_type TEXT,
      start_media_file_id TEXT,
      deposit_success_text TEXT,
      deposit_success_media_type TEXT,
      deposit_success_media_file_id TEXT,
      deposit_rejected_text TEXT,
      deposit_rejected_media_type TEXT,
      deposit_rejected_media_file_id TEXT,
      cs_link TEXT DEFAULT 'https://t.me/m/4ujBD3wnZmI1',
      game_link TEXT DEFAULT 'https://99laju.net/',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS admins (
      bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
      admin_user_id BIGINT NOT NULL,
      added_by BIGINT NOT NULL,
      PRIMARY KEY (bot_id, admin_user_id)
    );

    CREATE TABLE IF NOT EXISTS users (
      bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
      user_id BIGINT NOT NULL,
      username TEXT,
      first_name TEXT,
      game_username TEXT,
      registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (bot_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS deposits (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
      user_id BIGINT NOT NULL,
      game_username TEXT,
      amount NUMERIC NOT NULL,
      bank TEXT,
      promo TEXT,
      receipt_file_id TEXT,
      status TEXT NOT NULL DEFAULT 'PENDING',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      processed_at TIMESTAMPTZ,
      processed_by BIGINT,
      admin_msg_id BIGINT
    );

    CREATE TABLE IF NOT EXISTS user_states (
      bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
      user_id BIGINT NOT NULL,
      state TEXT NOT NULL,
      payload JSONB,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (bot_id, user_id)
    );

    -- Promo list per bot
    CREATE TABLE IF NOT EXISTS promos (
      bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
      key TEXT NOT NULL,
      label TEXT NOT NULL,
      sort_order INT DEFAULT 0,
      PRIMARY KEY (bot_id, key)
    );
    """
    stmts = [s.strip() for s in ddl.split(";") if s.strip()]
    with engine.begin() as conn:
        for s in stmts:
            conn.execute(text(s))
    logger.info("DB Init OK")

init_db()

def auto_register_bot():
    """Auto-register first bot from BOT_TOKEN env var on startup."""
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN not set — skip auto-register")
        return
    existing = get_bot_by_token(BOT_TOKEN)
    if existing:
        logger.info(f"Bot @{existing.get('bot_username','')} already registered")
        return
    # Verify token
    try:
        r = SESSION.post(TG_API.format(token=BOT_TOKEN, method="getMe"), timeout=15)
        js = r.json()
        if not js.get("ok"):
            logger.error(f"getMe failed: {js}")
            return
        me = js["result"]
    except Exception as e:
        logger.error(f"Auto-register getMe error: {e}")
        return
    bot_username = me.get("username", "")
    owner = int(OWNER_ID) if OWNER_ID else 0
    secret = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO bots (token, bot_username, secret_token, owner_id)
            VALUES (:t, :u, :s, :o)
        """), {"t": BOT_TOKEN, "u": bot_username, "s": secret, "o": owner})
    bot_row = get_bot_by_token(BOT_TOKEN)
    if bot_row:
        add_default_promos(str(bot_row["id"]))
    # Set webhook
    if PUBLIC_BASE_URL:
        wh_url = f"{PUBLIC_BASE_URL}/telegram/{secret}"
        try:
            SESSION.post(TG_API.format(token=BOT_TOKEN, method="setWebhook"),
                        data={"url": wh_url, "secret_token": secret,
                              "allowed_updates": json.dumps(["message", "callback_query"])}, timeout=15)
            logger.info(f"✅ Bot @{bot_username} auto-registered! Webhook: {wh_url}")
        except Exception as e:
            logger.error(f"Webhook set error: {e}")
    else:
        logger.warning(f"Bot @{bot_username} registered but PUBLIC_BASE_URL not set — webhook skipped")

auto_register_bot()

# ---------------------------
# UTILS
# ---------------------------
def utcnow():
    return datetime.now(timezone.utc)

def now_str(fmt="%Y-%m-%d %H:%M:%S"):
    if LOCAL_TZ:
        return datetime.now(LOCAL_TZ).strftime(fmt)
    return datetime.now().strftime(fmt)

def _trim(s, limit):
    if not s: return ""
    return s[:limit] + "…" if len(s) > limit else s

def _h(s):
    return html.escape(str(s)) if s else ""

# ---------------------------
# TELEGRAM API
# ---------------------------
def tg_call(token, method, data=None, files=None):
    try:
        r = SESSION.post(TG_API.format(token=token, method=method), data=data, files=files, timeout=25)
        js = r.json()
        if not js.get("ok"):
            desc = (js.get("description") or "").lower()
            code = js.get("error_code")
            if code == 403 and any(x in desc for x in ["bot was blocked", "user is deactivated"]):
                return None
            if code == 400 and any(x in desc for x in ["chat not found", "message is not modified"]):
                return None
            logger.error(f"TG {method}: {js}")
            return None
        return js.get("result")
    except Exception as e:
        logger.error(f"TG {method} exc: {e}")
        return None

def send_msg(token, chat_id, text_, reply_markup=None, parse_mode="HTML", reply_to=None):
    if not text_: return None
    text_ = _trim(text_, TG_MAX_TEXT)
    d = {"chat_id": chat_id, "text": text_, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_to: d["reply_to_message_id"] = reply_to
    if reply_markup: d["reply_markup"] = json.dumps(reply_markup)
    return tg_call(token, "sendMessage", data=d)

def send_media(token, chat_id, media_type, file_id, caption=None, reply_markup=None, parse_mode="HTML"):
    method_map = {"photo": "sendPhoto", "video": "sendVideo", "animation": "sendAnimation", "document": "sendDocument"}
    field_map = {"photo": "photo", "video": "video", "animation": "animation", "document": "document"}
    if media_type not in method_map:
        return send_msg(token, chat_id, caption or "", reply_markup=reply_markup)
    cap = _trim(caption or "", TG_MAX_CAPTION)
    d = {"chat_id": chat_id, field_map[media_type]: file_id, "parse_mode": parse_mode}
    if cap: d["caption"] = cap
    if reply_markup: d["reply_markup"] = json.dumps(reply_markup)
    return tg_call(token, method_map[media_type], data=d)

def edit_msg(token, chat_id, msg_id, text_, reply_markup=None, parse_mode="HTML"):
    text_ = _trim(text_, TG_MAX_TEXT)
    d = {"chat_id": chat_id, "message_id": msg_id, "text": text_, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup: d["reply_markup"] = json.dumps(reply_markup)
    return tg_call(token, "editMessageText", data=d)

def edit_caption(token, chat_id, msg_id, caption_, reply_markup=None, parse_mode="HTML"):
    d = {"chat_id": chat_id, "message_id": msg_id, "caption": _trim(caption_, TG_MAX_CAPTION), "parse_mode": parse_mode}
    if reply_markup: d["reply_markup"] = json.dumps(reply_markup)
    return tg_call(token, "editMessageCaption", data=d)

def answer_cb(token, cb_id, text_=None, show_alert=False):
    d = {"callback_query_id": cb_id, "show_alert": show_alert}
    if text_: d["text"] = text_
    return tg_call(token, "answerCallbackQuery", data=d)

def send_or_media(token, chat_id, mt, mf, text_, reply_markup=None):
    if mt and mf:
        return send_media(token, chat_id, mt, mf, caption=text_, reply_markup=reply_markup)
    return send_msg(token, chat_id, text_, reply_markup=reply_markup)

# ---------------------------
# DB HELPERS
# ---------------------------
def get_bot_by_secret(secret):
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM bots WHERE secret_token=:s"), {"s": secret}).mappings().first()

def get_bot_by_id(bot_id):
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM bots WHERE id=:i"), {"i": bot_id}).mappings().first()

def get_bot_by_token(tok):
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM bots WHERE token=:t"), {"t": tok}).mappings().first()

def is_owner(uid, bot_row):
    return int(uid) == int(bot_row.get("owner_id", 0))

def is_admin(uid, bot_id):
    with engine.connect() as c:
        r = c.execute(text("SELECT 1 FROM admins WHERE bot_id=:b AND admin_user_id=:u"), {"b": bot_id, "u": uid}).first()
        return r is not None

def require_admin(bot_row, uid):
    return is_owner(uid, bot_row) or is_admin(uid, str(bot_row["id"]))

def get_admin_chat(bot_row):
    return int(bot_row.get("admin_group_id") or bot_row.get("owner_id") or 0)

def upsert_user(bot_id, user, game_username=None):
    uid = int(user["id"])
    with engine.begin() as c:
        r = c.execute(text("""
            INSERT INTO users (bot_id, user_id, username, first_name, game_username)
            VALUES (:b, :u, :un, :fn, :gu)
            ON CONFLICT (bot_id, user_id) DO UPDATE SET username=:un, first_name=:fn
        """), {"b": bot_id, "u": uid, "un": user.get("username"), "fn": user.get("first_name",""), "gu": game_username})
        row = c.execute(text("SELECT * FROM users WHERE bot_id=:b AND user_id=:u"), {"b": bot_id, "u": uid}).mappings().first()
    return row

def set_game_username(bot_id, uid, game_username):
    with engine.begin() as c:
        c.execute(text("UPDATE users SET game_username=:g WHERE bot_id=:b AND user_id=:u"), {"g": game_username, "b": bot_id, "u": uid})

def get_user(bot_id, uid):
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM users WHERE bot_id=:b AND user_id=:u"), {"b": bot_id, "u": uid}).mappings().first()

def set_state(bot_id, uid, state, payload=None):
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO user_states (bot_id, user_id, state, payload, updated_at)
            VALUES (:b, :u, :s, CAST(:p AS jsonb), NOW())
            ON CONFLICT (bot_id, user_id) DO UPDATE SET state=excluded.state, payload=excluded.payload, updated_at=NOW()
        """), {"b": bot_id, "u": uid, "s": state, "p": json.dumps(payload or {})})

def get_state(bot_id, uid):
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM user_states WHERE bot_id=:b AND user_id=:u"), {"b": bot_id, "u": uid}).mappings().first()

def clear_state(bot_id, uid):
    with engine.begin() as c:
        c.execute(text("DELETE FROM user_states WHERE bot_id=:b AND user_id=:u"), {"b": bot_id, "u": uid})

def create_deposit(bot_id, uid, game_username, amount, bank, promo, receipt_file_id):
    dep_id = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO deposits (id, bot_id, user_id, game_username, amount, bank, promo, receipt_file_id)
            VALUES (:id, :b, :u, :gu, :a, :bk, :pr, :rf)
        """), {"id": dep_id, "b": bot_id, "u": uid, "gu": game_username, "a": amount, "bk": bank, "pr": promo, "rf": receipt_file_id})
    return dep_id

def update_deposit_status(dep_id, status, processed_by):
    with engine.begin() as c:
        c.execute(text("""
            UPDATE deposits SET status=:s, processed_at=NOW(), processed_by=:pb WHERE id=:id
        """), {"s": status, "pb": processed_by, "id": dep_id})

def update_deposit_admin_msg(dep_id, admin_msg_id):
    with engine.begin() as c:
        c.execute(text("UPDATE deposits SET admin_msg_id=:m WHERE id=:id"), {"m": admin_msg_id, "id": dep_id})

def get_deposit(dep_id):
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM deposits WHERE id=:id"), {"id": dep_id}).mappings().first()

def get_promos(bot_id):
    with engine.connect() as c:
        rows = c.execute(text("SELECT * FROM promos WHERE bot_id=:b ORDER BY sort_order, key"), {"b": bot_id}).mappings().all()
        return list(rows)

def add_default_promos(bot_id):
    defaults = [
        ("rm50", "👑 RM50 Free RM60 (120%)", 1),
        ("rm100", "👑 RM100 Free RM120 (120%)", 2),
        ("1st_50", "1️⃣ 1st Dep - 50% Welcome", 3),
        ("2nd_100", "2️⃣ 2nd Dep - 100% Welcome", 4),
        ("daily_15", "🧧 15% Daily Bonus", 5),
        ("unlimited_6", "💰 6% Unlimited", 6),
        ("unlimited_10", "💰 10% Unlimited (10pm-6am)", 7),
        ("no_claim", "🍀 No Claim (x1 TO)", 8),
    ]
    with engine.begin() as c:
        for key, label, sort in defaults:
            c.execute(text("""
                INSERT INTO promos (bot_id, key, label, sort_order)
                VALUES (:b, :k, :l, :s) ON CONFLICT DO NOTHING
            """), {"b": bot_id, "k": key, "l": label, "s": sort})

def save_content_from_reply(msg):
    txt = msg.get("text") or msg.get("caption") or ""
    mt, mf = None, None
    if msg.get("photo"): mt, mf = "photo", msg["photo"][-1]["file_id"]
    elif msg.get("video"): mt, mf = "video", msg["video"]["file_id"]
    elif msg.get("animation"): mt, mf = "animation", msg["animation"]["file_id"]
    elif msg.get("document"): mt, mf = "document", msg["document"]["file_id"]
    return mt, mf, txt

def get_deposit_stats(bot_id):
    with engine.connect() as c:
        total = c.execute(text("SELECT COUNT(*) FROM deposits WHERE bot_id=:b"), {"b": bot_id}).scalar() or 0
        pending = c.execute(text("SELECT COUNT(*) FROM deposits WHERE bot_id=:b AND status='PENDING'"), {"b": bot_id}).scalar() or 0
        approved = c.execute(text("SELECT COUNT(*) FROM deposits WHERE bot_id=:b AND status='APPROVED'"), {"b": bot_id}).scalar() or 0
        rejected = c.execute(text("SELECT COUNT(*) FROM deposits WHERE bot_id=:b AND status='REJECTED'"), {"b": bot_id}).scalar() or 0
        users_count = c.execute(text("SELECT COUNT(*) FROM users WHERE bot_id=:b"), {"b": bot_id}).scalar() or 0
        total_amount = c.execute(text("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE bot_id=:b AND status='APPROVED'"), {"b": bot_id}).scalar() or 0
    return {"total": total, "pending": pending, "approved": approved, "rejected": rejected, "users": users_count, "total_amount": float(total_amount)}


# ---------------------------
# KEYBOARDS
# ---------------------------
def kb_main_menu():
    return {"inline_keyboard": [
        [{"text": "💰 Auto Deposit", "callback_data": "deposit"}],
        [{"text": "🧼 Cara Cuci", "callback_data": "info:cuci"}],
        [{"text": "🎮 Cari Game ID", "callback_data": "info:gameid"}],
        [{"text": "🎁 Claim Promotion", "callback_data": "info:promo"}],
        [{"text": "📊 Winning Record", "callback_data": "info:record"}],
        [{"text": "💬 Hubungi CS", "callback_data": "info:cs"}],
    ]}

def kb_reply_persistent():
    return {"keyboard": [[{"text": "🏠 Menu Utama"}, {"text": "Auto Deposit 💰"}]], "resize_keyboard": True, "is_persistent": True}

def kb_amounts(bot_row):
    mn = int(bot_row.get("min_deposit") or 30)
    btns = []
    for a in [30, 50, 100, 200, 500, 1000]:
        if a >= mn:
            btns.append({"text": f"RM{a}", "callback_data": f"amt:{a}"})
    rows = [btns[i:i+2] for i in range(0, len(btns), 2)]
    rows.append([{"text": "✏️ Custom Amount", "callback_data": "amt:custom"}])
    rows.append([{"text": "🔙 Back", "callback_data": "menu"}])
    return {"inline_keyboard": rows}

def kb_banks():
    return {"inline_keyboard": [
        [{"text": "🏦 Affin Bank", "callback_data": "bank:affin"}],
        [{"text": "🏦 RHB Bank", "callback_data": "bank:rhb"}],
        [{"text": "🔙 Back", "callback_data": "deposit"}],
    ]}

def kb_promos(bot_id):
    promos = get_promos(bot_id)
    if not promos:
        add_default_promos(bot_id)
        promos = get_promos(bot_id)
    rows = [[{"text": p["label"], "callback_data": f"promo:{p['key']}"}] for p in promos]
    rows.append([{"text": "🔙 Back", "callback_data": "bank:back"}])
    return {"inline_keyboard": rows}

def kb_cs_actions(dep_id):
    return {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"cs:approve:{dep_id}"},
        {"text": "❌ Reject", "callback_data": f"cs:reject:{dep_id}"},
    ]]}

def kb_home():
    return {"inline_keyboard": [[{"text": "🏠 Menu Utama", "callback_data": "menu"}]]}

def kb_home_deposit():
    return {"inline_keyboard": [
        [{"text": "🏠 Menu Utama", "callback_data": "menu"}],
        [{"text": "💰 Auto Deposit", "callback_data": "deposit"}],
    ]}

# ---------------------------
# FLOW HANDLERS
# ---------------------------
def handle_start(bot_row, chat_id, uid, user_from):
    token = bot_row["token"]
    bot_id = str(bot_row["id"])

    # --- Auto-claim owner: first /start user becomes owner ---
    if int(bot_row.get("owner_id", 0)) == 0:
        with engine.begin() as c:
            c.execute(text("UPDATE bots SET owner_id=:o WHERE id=:i"), {"o": uid, "i": bot_id})
        bot_row = get_bot_by_id(bot_id) or bot_row
        send_msg(token, chat_id,
                 f"👑 <b>ANDA ADALAH OWNER BOT INI!</b>\n\n"
                 f"🆔 Owner ID: <code>{uid}</code>\n\n"
                 f"Guna /settings untuk configure bot.\n"
                 f"Guna /setadmingroup di dalam group untuk set admin group.\n\n"
                 f"Tekan /start sekali lagi untuk mula.")
        return

    user_row = get_user(bot_id, uid)

    if user_row and user_row.get("game_username"):
        name = user_row["game_username"]
        txt = bot_row.get("start_text") or f"🎰 ✨ SELAMAT KEMBALI, <b>{_h(name)}</b>! ✨ 🎰\n🤖 Auto Deposit Bot — Laju, Mudah, 24/7!\n\n👇 Pilih pilihan di bawah:"
        mt = bot_row.get("start_media_type")
        mf = bot_row.get("start_media_file_id")
        send_or_media(token, chat_id, mt, mf, txt, reply_markup=kb_main_menu())
        send_msg(token, chat_id, "⬇️", reply_markup=kb_reply_persistent())
    else:
        upsert_user(bot_id, user_from)
        aff = bot_row.get("affiliate_link") or "https://99laju.net/register?affiliate=911295"
        txt = f"🆕 Daftar Sekarang di sini 👇\n🔗 {aff}\n\n🧑 Sila masukkan Username 99LAJU anda :"
        set_state(bot_id, uid, "register")
        send_msg(token, chat_id, txt, reply_markup=kb_reply_persistent())


def handle_menu(bot_row, chat_id, uid, msg_id=None):
    token = bot_row["token"]
    bot_id = str(bot_row["id"])
    user_row = get_user(bot_id, uid)
    name = (user_row or {}).get("game_username") or ""
    label = f"👤 <b>{_h(name)}</b>\n\n" if name else ""
    txt = f"🏠 <b>MENU UTAMA</b>\n\n{label}Sila pilih:"
    if msg_id:
        edit_msg(token, chat_id, msg_id, txt, reply_markup=kb_main_menu())
    else:
        send_msg(token, chat_id, txt, reply_markup=kb_main_menu())

def handle_deposit_start(bot_row, chat_id, uid, msg_id=None):
    token = bot_row["token"]
    bot_id = str(bot_row["id"])
    user_row = get_user(bot_id, uid)
    if not user_row or not user_row.get("game_username"):
        set_state(bot_id, uid, "register")
        send_msg(token, chat_id, "⚠️ Sila daftar username dulu.\nTaipkan username 99LAJU anda:")
        return
    clear_state(bot_id, uid)
    set_state(bot_id, uid, "deposit_amount", {"game_username": user_row["game_username"]})
    mn = int(bot_row.get("min_deposit") or 30)
    txt = f"💰 <b>AUTO DEPOSIT</b>\n\nMinimum deposit: RM{mn}\nSila pilih jumlah deposit:"
    if msg_id:
        edit_msg(token, chat_id, msg_id, txt, reply_markup=kb_amounts(bot_row))
    else:
        send_msg(token, chat_id, txt, reply_markup=kb_amounts(bot_row))

def handle_amount(bot_row, chat_id, uid, amount, msg_id):
    token = bot_row["token"]
    bot_id = str(bot_row["id"])
    st = get_state(bot_id, uid)
    payload = json.loads(st["payload"]) if st and st.get("payload") else {}
    payload["amount"] = amount
    set_state(bot_id, uid, "deposit_bank", payload)
    txt = f"✅ Amount: <b>RM{amount}</b>\n\n🏦 Pilih bank untuk transfer:"
    edit_msg(token, chat_id, msg_id, txt, reply_markup=kb_banks())

def handle_bank(bot_row, chat_id, uid, bank_key, msg_id):
    token = bot_row["token"]
    bot_id = str(bot_row["id"])
    if bank_key == "affin":
        bank_name = "Affin Bank"
        acc_name = bot_row.get("bank_affin_name") or "FARHAN CATERING ENTERPRISE"
        acc_num = bot_row.get("bank_affin_account") or "100180018799"
    else:
        bank_name = "RHB Bank"
        acc_name = bot_row.get("bank_rhb_name") or "FARHAN CATERING ENTERPRISE"
        acc_num = bot_row.get("bank_rhb_account") or "25305200039496"

    st = get_state(bot_id, uid)
    payload = json.loads(st["payload"]) if st and st.get("payload") else {}
    payload["bank"] = bank_name
    payload["bank_acc_name"] = acc_name
    payload["bank_acc_num"] = acc_num
    set_state(bot_id, uid, "deposit_promo", payload)

    amt = payload.get("amount", "?")
    txt = (f"🏦 <b>DETAIL AKAUN BANK</b>\n━━━━━━━━━━━━━━━━━━\n"
           f"🏦 Bank: {bank_name}\n👤 Nama: <code>{_h(acc_name)}</code>\n💳 Akaun: <code>{acc_num}</code>\n"
           f"━━━━━━━━━━━━━━━━━━\n💰 Jumlah: <b>RM{amt}</b>\n\n"
           f"⚠️ Transfer tepat jumlah di atas.\n\nPilih promosi anda:")
    edit_msg(token, chat_id, msg_id, txt, reply_markup=kb_promos(bot_id))

def handle_promo(bot_row, chat_id, uid, promo_key, msg_id):
    token = bot_row["token"]
    bot_id = str(bot_row["id"])
    promos = get_promos(bot_id)
    promo_label = next((p["label"] for p in promos if p["key"] == promo_key), promo_key)

    st = get_state(bot_id, uid)
    payload = json.loads(st["payload"]) if st and st.get("payload") else {}
    payload["promo"] = promo_label
    set_state(bot_id, uid, "upload_resit", payload)

    txt = (f"📋 <b>RINGKASAN DEPOSIT</b>\n━━━━━━━━━━━━━━━━━━\n"
           f"👤 Username: {_h(payload.get('game_username','?'))}\n"
           f"💰 Amount: RM{payload.get('amount','?')}\n"
           f"🏦 Bank: {payload.get('bank','?')}\n"
           f"🎁 Promo: {_h(promo_label)}\n━━━━━━━━━━━━━━━━━━\n"
           f"🏦 Transfer ke:\nNama: <code>{_h(payload.get('bank_acc_name','?'))}</code>\n"
           f"Akaun: <code>{payload.get('bank_acc_num','?')}</code>\n\n"
           f"📸 Sila upload screenshot resit transfer anda sekarang.")
    kb = {"inline_keyboard": [[{"text": "🔙 Cancel", "callback_data": "deposit"}]]}
    edit_msg(token, chat_id, msg_id, txt, reply_markup=kb)

def handle_receipt(bot_row, chat_id, uid, file_id):
    token = bot_row["token"]
    bot_id = str(bot_row["id"])
    st = get_state(bot_id, uid)
    if not st or st.get("state") != "upload_resit":
        send_msg(token, chat_id, "⚠️ Sila ikut flow deposit.", reply_markup=kb_home_deposit())
        return
    payload = json.loads(st["payload"]) if st.get("payload") else {}
    dep_id = create_deposit(bot_id, uid, payload.get("game_username"), payload.get("amount", 0),
                            payload.get("bank"), payload.get("promo"), file_id)
    clear_state(bot_id, uid)

    # Notify admin
    admin_chat = get_admin_chat(bot_row)
    short_id = dep_id[:8]
    admin_txt = (f"📥 <b>DEPOSIT BARU!</b> #{short_id}\n━━━━━━━━━━━━━━━━━━\n"
                 f"👤 Username: {_h(payload.get('game_username','?'))}\n"
                 f"💰 Amount: RM{payload.get('amount','?')}\n"
                 f"🏦 Bank: {payload.get('bank','?')}\n"
                 f"🎁 Promo: {_h(payload.get('promo','?'))}\n━━━━━━━━━━━━━━━━━━\n"
                 f"🕐 {now_str()}\n🆔 User: {uid}")
    result = send_media(token, admin_chat, "photo", file_id, caption=admin_txt, reply_markup=kb_cs_actions(dep_id))
    if result and result.get("message_id"):
        update_deposit_admin_msg(dep_id, result["message_id"])

    send_msg(token, chat_id,
             f"✅ <b>RESIT DITERIMA!</b>\n\n🔖 ID: <code>#{short_id}</code>\n\n⏳ CS akan semak & approve. Tunggu notifikasi ya! 💬",
             reply_markup=kb_home_deposit())

def handle_cs_action(bot_row, chat_id, uid, action, dep_id, msg_id, cb_id):
    token = bot_row["token"]
    bot_id = str(bot_row["id"])
    if not require_admin(bot_row, uid):
        answer_cb(token, cb_id, "❌ Admin only!", show_alert=True)
        return
    dep = get_deposit(dep_id)
    if not dep:
        answer_cb(token, cb_id, "⚠️ Not found", show_alert=True)
        return
    if dep["status"] != "PENDING":
        answer_cb(token, cb_id, f"Already {dep['status']}", show_alert=True)
        return

    target_uid = int(dep["user_id"])
    game_link = bot_row.get("game_link") or "https://99laju.net/"
    cs_link = bot_row.get("cs_link") or "https://t.me/m/4ujBD3wnZmI1"

    if action == "approve":
        update_deposit_status(dep_id, "APPROVED", uid)
        txt = bot_row.get("deposit_success_text") or (
            f"✅ <b>DEPOSIT BERJAYA!</b> 🎉\n━━━━━━━━━━━━━━━━━━\n"
            f"👤 Username: {_h(dep['game_username'])}\n💰 Amount: RM{dep['amount']}\n"
            f"🎁 Promo: {_h(dep['promo'])}\n━━━━━━━━━━━━━━━━━━\n"
            f"Sila login untuk dapatkan Game ID!\nSemoga Bos menang beribu-ribu! 🍀")
        mt = bot_row.get("deposit_success_media_type")
        mf = bot_row.get("deposit_success_media_file_id")
        kb = {"inline_keyboard": [
            [{"text": "🎮 Dapatkan Game ID", "callback_data": "info:gameid"}],
            [{"text": "🎮 Play Now!", "url": game_link}],
            [{"text": "🏠 Menu Utama", "callback_data": "menu"}],
        ]}
        send_or_media(token, target_uid, mt, mf, txt, reply_markup=kb)
        # Update admin msg
        try:
            edit_caption(token, chat_id, msg_id,
                        f"✅ <b>APPROVED</b> by admin at {now_str('%H:%M:%S')}")
        except Exception:
            pass
        answer_cb(token, cb_id, "✅ Approved!")
    else:
        update_deposit_status(dep_id, "REJECTED", uid)
        txt = bot_row.get("deposit_rejected_text") or "❌ <b>DEPOSIT DITOLAK</b>\n\n‼️ Maaf, deposit ada masalah.\nSila hubungi CS. 🙏"
        mt = bot_row.get("deposit_rejected_media_type")
        mf = bot_row.get("deposit_rejected_media_file_id")
        kb = {"inline_keyboard": [
            [{"text": "💬 Hubungi CS", "url": cs_link}],
            [{"text": "💰 Cuba Lagi", "callback_data": "deposit"}],
            [{"text": "🏠 Menu Utama", "callback_data": "menu"}],
        ]}
        send_or_media(token, target_uid, mt, mf, txt, reply_markup=kb)
        try:
            edit_caption(token, chat_id, msg_id,
                        f"❌ <b>REJECTED</b> by admin at {now_str('%H:%M:%S')}")
        except Exception:
            pass
        answer_cb(token, cb_id, "❌ Rejected!")

# ---------------------------
# INFO PAGES
# ---------------------------
def handle_info(bot_row, chat_id, uid, page, msg_id):
    token = bot_row["token"]
    game_link = bot_row.get("game_link") or "https://99laju.net/"
    cs_link = bot_row.get("cs_link") or "https://t.me/m/4ujBD3wnZmI1"

    if page == "cuci":
        txt = "🧼 <b>CARA CUCI (TURNOVER)</b>\n\n1️⃣ Deposit minima RM30\n2️⃣ Claim promo\n3️⃣ Main game sehingga turnover dicapai\n4️⃣ BONUS masuk automatik\n\n💡 Cek promo untuk syarat turnover."
        edit_msg(token, chat_id, msg_id, txt, reply_markup=kb_home_deposit())
    elif page == "gameid":
        txt = "🎮 <b>CARI GAME ID</b>\n\n1️⃣ Deposit & approve\n2️⃣ Login website S9MY\n3️⃣ Menu Game ID\n4️⃣ Copy ID & PW\n5️⃣ Play Now!"
        kb = {"inline_keyboard": [
            [{"text": "🎮 Play Now", "url": game_link}],
            [{"text": "🏠 Menu Utama", "callback_data": "menu"}],
        ]}
        edit_msg(token, chat_id, msg_id, txt, reply_markup=kb)
    elif page == "promo":
        txt = "🎁 <b>SEMUA PROMOSI S9MY</b>\n\n👑 120% Welcome (RM50→Free RM60)\n👑 120% Welcome (RM100→Free RM120)\n1️⃣ 1st Dep — 50% Welcome\n2️⃣ 2nd Dep — 100% Welcome\n🧧 15% Daily Bonus\n💰 6% Unlimited\n💰 10% Unlimited (10pm-6am)\n🍀 No Claim (x1 TO)\n\n💡 Pilih promo semasa deposit!"
        edit_msg(token, chat_id, msg_id, txt, reply_markup=kb_home_deposit())
    elif page == "record":
        txt = "📊 <b>WINNING RECORD</b>\n\n1️⃣ Login website S9MY\n2️⃣ Profile → Wallet\n3️⃣ Semak transaksi"
        edit_msg(token, chat_id, msg_id, txt, reply_markup=kb_home_deposit())
    elif page == "cs":
        txt = "💬 <b>HUBUNGI CS</b>\n\nTekan button untuk chat CS:"
        kb = {"inline_keyboard": [
            [{"text": "💬 Chat CS", "url": cs_link}],
            [{"text": "🏠 Menu Utama", "callback_data": "menu"}],
        ]}
        edit_msg(token, chat_id, msg_id, txt, reply_markup=kb)

# ---------------------------
# ADMIN COMMANDS
# ---------------------------
def handle_admin_cmd(bot_row, chat_id, uid, cmd, args, msg):
    token = bot_row["token"]
    bot_id = str(bot_row["id"])

    if cmd == "/settings":
        if not require_admin(bot_row, uid): return
        bot_row = get_bot_by_id(bot_id) or bot_row
        mn = bot_row.get("min_deposit") or 30
        aff = bot_row.get("affiliate_link") or "-"
        ag = bot_row.get("admin_group_id") or "Not set"
        stats = get_deposit_stats(bot_id)
        txt = (f"⚙️ <b>SETTINGS — {_h(bot_row.get('bot_username',''))}</b>\n━━━━━━━━━━━━━━━━━━\n"
               f"💰 Min Deposit: RM{mn}\n🔗 Affiliate: {_h(aff)}\n👥 Admin Group: {ag}\n"
               f"🏦 Affin: {bot_row.get('bank_affin_account','?')}\n🏦 RHB: {bot_row.get('bank_rhb_account','?')}\n"
               f"━━━━━━━━━━━━━━━━━━\n📊 <b>Stats</b>\n👥 Users: {stats['users']}\n"
               f"📥 Total Deposits: {stats['total']}\n✅ Approved: {stats['approved']}\n"
               f"⏳ Pending: {stats['pending']}\n❌ Rejected: {stats['rejected']}\n"
               f"💰 Total Approved: RM{stats['total_amount']:.2f}\n━━━━━━━━━━━━━━━━━━\n"
               f"<b>Commands:</b>\n/setstart — Set welcome msg\n/setdepositsuccess — Set approve msg\n"
               f"/setdepositreject — Set reject msg\n/setbank — Set bank details\n"
               f"/setmindeposit <i>amount</i>\n/setaffiliate <i>link</i>\n/setcslink <i>link</i>\n"
               f"/setgamelink <i>link</i>\n/setadmingroup — Run in target group\n"
               f"/addadmin <i>user_id</i>\n/removeadmin <i>user_id</i>\n/stats")
        send_msg(token, chat_id, txt)

    elif cmd == "/stats":
        if not require_admin(bot_row, uid): return
        stats = get_deposit_stats(bot_id)
        txt = (f"📊 <b>STATISTIK BOT</b>\n━━━━━━━━━━━━━━━━━━\n"
               f"👥 Jumlah Users: {stats['users']}\n📥 Total Deposits: {stats['total']}\n"
               f"✅ Approved: {stats['approved']}\n⏳ Pending: {stats['pending']}\n"
               f"❌ Rejected: {stats['rejected']}\n💰 Total Approved: RM{stats['total_amount']:.2f}")
        send_msg(token, chat_id, txt)

    elif cmd == "/setadmingroup":
        if not is_owner(uid, bot_row): return
        with engine.begin() as c:
            c.execute(text("UPDATE bots SET admin_group_id=:g WHERE id=:i"), {"g": chat_id, "i": bot_id})
        send_msg(token, chat_id, f"✅ Admin group set to this chat ({chat_id})")

    elif cmd == "/addadmin":
        if not is_owner(uid, bot_row): return
        if not args: send_msg(token, chat_id, "Usage: /addadmin <user_id>"); return
        try:
            admin_uid = int(args[0])
            with engine.begin() as c:
                c.execute(text("INSERT INTO admins (bot_id, admin_user_id, added_by) VALUES (:b,:u,:a) ON CONFLICT DO NOTHING"),
                         {"b": bot_id, "u": admin_uid, "a": uid})
            send_msg(token, chat_id, f"✅ Admin {admin_uid} added")
        except Exception: send_msg(token, chat_id, "❌ Invalid user_id")

    elif cmd == "/removeadmin":
        if not is_owner(uid, bot_row): return
        if not args: send_msg(token, chat_id, "Usage: /removeadmin <user_id>"); return
        try:
            admin_uid = int(args[0])
            with engine.begin() as c:
                c.execute(text("DELETE FROM admins WHERE bot_id=:b AND admin_user_id=:u"), {"b": bot_id, "u": admin_uid})
            send_msg(token, chat_id, f"✅ Admin {admin_uid} removed")
        except Exception: send_msg(token, chat_id, "❌ Invalid user_id")

    elif cmd == "/setmindeposit":
        if not require_admin(bot_row, uid): return
        if not args: send_msg(token, chat_id, "Usage: /setmindeposit <amount>"); return
        try:
            amt = int(args[0])
            with engine.begin() as c:
                c.execute(text("UPDATE bots SET min_deposit=:a WHERE id=:i"), {"a": amt, "i": bot_id})
            send_msg(token, chat_id, f"✅ Min deposit set to RM{amt}")
        except Exception: send_msg(token, chat_id, "❌ Invalid amount")

    elif cmd == "/setaffiliate":
        if not require_admin(bot_row, uid): return
        if not args: send_msg(token, chat_id, "Usage: /setaffiliate <link>"); return
        link = args[0]
        with engine.begin() as c:
            c.execute(text("UPDATE bots SET affiliate_link=:l WHERE id=:i"), {"l": link, "i": bot_id})
        send_msg(token, chat_id, f"✅ Affiliate link updated")

    elif cmd == "/setcslink":
        if not require_admin(bot_row, uid): return
        if not args: send_msg(token, chat_id, "Usage: /setcslink <link>"); return
        with engine.begin() as c:
            c.execute(text("UPDATE bots SET cs_link=:l WHERE id=:i"), {"l": args[0], "i": bot_id})
        send_msg(token, chat_id, "✅ CS link updated")

    elif cmd == "/setgamelink":
        if not require_admin(bot_row, uid): return
        if not args: send_msg(token, chat_id, "Usage: /setgamelink <link>"); return
        with engine.begin() as c:
            c.execute(text("UPDATE bots SET game_link=:l WHERE id=:i"), {"l": args[0], "i": bot_id})
        send_msg(token, chat_id, "✅ Game link updated")

    elif cmd in ("/setstart", "/setdepositsuccess", "/setdepositreject"):
        if not require_admin(bot_row, uid): return
        reply = msg.get("reply_to_message")
        if not reply:
            send_msg(token, chat_id, f"⚠️ Reply to a message with {cmd}")
            return
        mt, mf, txt_content = save_content_from_reply(reply)
        col_map = {"/setstart": ("start", "start"), "/setdepositsuccess": ("deposit_success", "deposit_success"),
                   "/setdepositreject": ("deposit_rejected", "deposit_rejected")}
        prefix = col_map[cmd][1]
        with engine.begin() as c:
            c.execute(text(f"UPDATE bots SET {prefix}_text=:t, {prefix}_media_type=:mt, {prefix}_media_file_id=:mf WHERE id=:i"),
                     {"t": txt_content, "mt": mt, "mf": mf, "i": bot_id})
        send_msg(token, chat_id, f"✅ {cmd} updated!")

    elif cmd == "/setbank":
        if not require_admin(bot_row, uid): return
        set_state(bot_id, uid, "admin_setbank")
        send_msg(token, chat_id, "🏦 Sila hantar bank details dalam format:\n<code>affin|NAMA|ACCOUNT</code>\natau\n<code>rhb|NAMA|ACCOUNT</code>")

# ---------------------------
# ADDBOT (master command via env TOKEN)
# ---------------------------
MASTER_TOKEN = os.getenv("MASTER_TOKEN", "").strip()

def handle_addbot(token, chat_id, uid, bot_token_str):
    """Register a new child bot."""
    # Verify token with getMe
    me = tg_call(bot_token_str, "getMe")
    if not me:
        send_msg(token, chat_id, "❌ Invalid bot token")
        return
    bot_username = me.get("username", "")

    existing = get_bot_by_token(bot_token_str)
    if existing:
        send_msg(token, chat_id, f"⚠️ Bot @{bot_username} already registered")
        return

    secret = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO bots (token, bot_username, secret_token, owner_id)
            VALUES (:t, :u, :s, :o)
        """), {"t": bot_token_str, "u": bot_username, "s": secret, "o": uid})

    bot_row = get_bot_by_token(bot_token_str)
    if bot_row:
        add_default_promos(str(bot_row["id"]))

    # Set webhook
    if PUBLIC_BASE_URL:
        wh_url = f"{PUBLIC_BASE_URL}/telegram/{secret}"
        tg_call(bot_token_str, "setWebhook", data={"url": wh_url, "secret_token": secret, "allowed_updates": json.dumps(["message", "callback_query"])})
        send_msg(token, chat_id, f"✅ Bot @{bot_username} registered!\n🔗 Webhook: {wh_url}\n\nGuna /settings di bot tu untuk configure.")
    else:
        send_msg(token, chat_id, f"✅ Bot @{bot_username} registered!\n⚠️ PUBLIC_BASE_URL not set, webhook not configured.\nSet it and re-addbot.")

# ---------------------------
# WEBHOOK ROUTE
# ---------------------------
@app.get("/healthz")
@app.get("/")
def healthz():
    return jsonify({"status": "ok", "service": SERVICE_NAME}), 200

@app.post("/telegram/<secret>")
def telegram_webhook(secret):
    bot_row = get_bot_by_secret(secret)
    if not bot_row:
        return "not found", 404

    data = request.get_json(force=True, silent=True) or {}
    token = bot_row["token"]
    bot_id = str(bot_row["id"])

    # --- CALLBACK QUERY ---
    cq = data.get("callback_query")
    if cq:
        uid = cq["from"]["id"]
        chat_id = cq["message"]["chat"]["id"]
        msg_id = cq["message"]["message_id"]
        cb_data = cq.get("data", "")

        if cb_data == "menu":
            handle_menu(bot_row, chat_id, uid, msg_id)
        elif cb_data == "deposit":
            handle_deposit_start(bot_row, chat_id, uid, msg_id)
        elif cb_data.startswith("amt:"):
            val = cb_data.split(":")[1]
            if val == "custom":
                st = get_state(bot_id, uid)
                payload = json.loads(st["payload"]) if st and st.get("payload") else {}
                set_state(bot_id, uid, "custom_amount", payload)
                mn = int(bot_row.get("min_deposit") or 30)
                edit_msg(token, chat_id, msg_id, f"✏️ <b>Custom Amount</b>\n\nTaipkan jumlah deposit (Min: RM{mn}):",
                        reply_markup={"inline_keyboard": [[{"text": "🔙 Back", "callback_data": "deposit"}]]})
            else:
                handle_amount(bot_row, chat_id, uid, int(val), msg_id)
        elif cb_data.startswith("bank:"):
            bk = cb_data.split(":")[1]
            if bk == "back":
                handle_deposit_start(bot_row, chat_id, uid, msg_id)
            else:
                handle_bank(bot_row, chat_id, uid, bk, msg_id)
        elif cb_data.startswith("promo:"):
            handle_promo(bot_row, chat_id, uid, cb_data.split(":")[1], msg_id)
        elif cb_data.startswith("info:"):
            handle_info(bot_row, chat_id, uid, cb_data.split(":")[1], msg_id)
        elif cb_data.startswith("cs:"):
            parts = cb_data.split(":")
            handle_cs_action(bot_row, chat_id, uid, parts[1], parts[2], msg_id, cq["id"])
            return "OK", 200

        answer_cb(token, cq["id"])
        return "OK", 200

    # --- MESSAGE ---
    msg = data.get("message")
    if not msg:
        return "OK", 200

    chat_id = msg["chat"]["id"]
    user_from = msg.get("from", {})
    uid = user_from.get("id", 0)
    text_ = (msg.get("text") or "").strip()

    # Commands
    if text_.startswith("/"):
        parts = text_.split()
        cmd = parts[0].split("@")[0].lower()
        args = parts[1:]

        if cmd == "/start":
            handle_start(bot_row, chat_id, uid, user_from)
        elif cmd == "/help":
            send_msg(token, chat_id, "🆘 <b>BANTUAN</b>\n\n• 💰 Auto Deposit\n• 🎮 Game ID\n• 🎁 Promo\n• 💬 CS\n\nTekan /start", reply_markup=kb_home_deposit())
        elif cmd == "/addbot" and args:
            handle_addbot(token, chat_id, uid, args[0])
        elif cmd in ("/settings", "/stats", "/setadmingroup", "/addadmin", "/removeadmin",
                      "/setmindeposit", "/setaffiliate", "/setcslink", "/setgamelink",
                      "/setstart", "/setdepositsuccess", "/setdepositreject", "/setbank"):
            handle_admin_cmd(bot_row, chat_id, uid, cmd, args, msg)
        return "OK", 200

    # Reply keyboard buttons
    if text_ == "🏠 Menu Utama":
        handle_menu(bot_row, chat_id, uid)
        return "OK", 200
    if text_ == "Auto Deposit 💰":
        handle_deposit_start(bot_row, chat_id, uid)
        return "OK", 200

    # State-based input
    st = get_state(bot_id, uid)
    if st:
        state = st.get("state", "")
        payload = json.loads(st["payload"]) if st.get("payload") else {}

        if state == "register":
            game_un = text_
            set_game_username(bot_id, uid, game_un)
            upsert_user(bot_id, user_from, game_un)
            clear_state(bot_id, uid)
            send_msg(token, chat_id, f"✅ <b>Berjaya Didaftarkan!</b>\n\n👤 Username: <b>{_h(game_un)}</b>\n\nSelamat datang ke S9MY! 🎰\nPilih pilihan di bawah:",
                    reply_markup=kb_main_menu())
            send_msg(token, chat_id, "⬇️", reply_markup=kb_reply_persistent())
            return "OK", 200

        if state == "custom_amount":
            mn = int(bot_row.get("min_deposit") or 30)
            try:
                amt = int(text_)
                if amt < mn:
                    send_msg(token, chat_id, f"❌ Minimum RM{mn}. Cuba lagi:",
                            reply_markup={"inline_keyboard": [[{"text": "🔙 Back", "callback_data": "deposit"}]]})
                    return "OK", 200
                payload["amount"] = amt
                set_state(bot_id, uid, "deposit_bank", payload)
                send_msg(token, chat_id, f"✅ Amount: <b>RM{amt}</b>\n\n🏦 Pilih bank:", reply_markup=kb_banks())
            except ValueError:
                send_msg(token, chat_id, "❌ Nombor tidak sah. Contoh: 50",
                        reply_markup={"inline_keyboard": [[{"text": "🔙 Back", "callback_data": "deposit"}]]})
            return "OK", 200

        if state == "admin_setbank":
            try:
                parts = text_.split("|")
                bank_type = parts[0].strip().lower()
                name = parts[1].strip()
                acc = parts[2].strip()
                col_name = f"bank_{bank_type}_name"
                col_acc = f"bank_{bank_type}_account"
                with engine.begin() as c:
                    c.execute(text(f"UPDATE bots SET {col_name}=:n, {col_acc}=:a WHERE id=:i"), {"n": name, "a": acc, "i": bot_id})
                clear_state(bot_id, uid)
                send_msg(token, chat_id, f"✅ Bank {bank_type.upper()} updated!\nNama: {name}\nAkaun: {acc}")
            except Exception:
                send_msg(token, chat_id, "❌ Format salah. Guna: <code>affin|NAMA|ACCOUNT</code>")
            return "OK", 200

    # Photo = receipt
    if msg.get("photo"):
        file_id = msg["photo"][-1]["file_id"]
        handle_receipt(bot_row, chat_id, uid, file_id)
        return "OK", 200

    # Fallback
    send_msg(token, chat_id, "Sila tekan /start untuk mula.", reply_markup=kb_reply_persistent())
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
