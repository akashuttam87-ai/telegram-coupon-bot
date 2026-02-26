import os
import sqlite3
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

TOKEN = os.getenv("8271855633:AAEOQ0ymg-NFiXHhIu2QtNC3dL_cWtmTwxQ")
ADMIN_ID = int(os.getenv("7662708655"))

DB = "bot.db"
QR_FILE = "qr.jpg"
SUPPORT = "https://t.me/yourusername"

# ---------------- DATABASE ----------------

conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
cur.execute("CREATE TABLE IF NOT EXISTS coupons500 (code TEXT UNIQUE)")
cur.execute("CREATE TABLE IF NOT EXISTS coupons1000 (code TEXT UNIQUE)")
cur.execute("CREATE TABLE IF NOT EXISTS used (code TEXT UNIQUE)")
cur.execute("CREATE TABLE IF NOT EXISTS utr (utr TEXT UNIQUE)")
cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
conn.commit()

def get_price(key, default):
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = cur.fetchone()
    return int(r[0]) if r else default

def set_price(key, val):
    cur.execute("REPLACE INTO settings VALUES (?,?)", (key, val))
    conn.commit()

PRICE500 = get_price("price500", 20)
PRICE1000 = get_price("price1000", 110)

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (uid,))
    conn.commit()

    kb = [
        ["🛒 Buy Coupon"],
        ["📞 Support"]
    ]

    if uid == ADMIN_ID:
        kb.append(["⚙ Admin Panel"])

    await update.message.reply_text(
        "Welcome",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

# ---------------- BUY ----------------

async def buy(update: Update, context):
    kb = [
        [
            InlineKeyboardButton(f"500₹ (₹{get_price('price500',20)})", callback_data="type_500"),
            InlineKeyboardButton(f"1000₹ (₹{get_price('price1000',110)})", callback_data="type_1000"),
        ]
    ]
    await update.message.reply_text(
        "Select Coupon Type",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def select_type(update: Update, context):
    q = update.callback_query
    await q.answer()

    t = q.data.split("_")[1]
    context.user_data["type"] = t

    kb = [
        [
            InlineKeyboardButton("1", callback_data="qty_1"),
            InlineKeyboardButton("2", callback_data="qty_2"),
            InlineKeyboardButton("5", callback_data="qty_5"),
        ],
        [InlineKeyboardButton("Custom", callback_data="qty_custom")]
    ]

    await q.message.reply_text("Select quantity", reply_markup=InlineKeyboardMarkup(kb))

async def qty(update: Update, context):
    q = update.callback_query
    await q.answer()

    qty = q.data.split("_")[1]

    if qty == "custom":
        context.user_data["custom"] = True
        await q.message.reply_text("Send quantity number")
        return

    await show_qr(q, context, int(qty))

async def custom_qty(update: Update, context):
    if context.user_data.get("custom"):
        qty = int(update.message.text)
        context.user_data["custom"] = False
        await show_qr(update.message, context, qty)

async def show_qr(msg, context, qty):
    t = context.user_data["type"]
    price = get_price(f"price{t}", 0) * qty

    context.user_data["qty"] = qty
    context.user_data["price"] = price

    kb = [
        [InlineKeyboardButton("Send UTR", callback_data="sendutr")],
        [InlineKeyboardButton("Cancel Order", callback_data="cancel")]
    ]

    await msg.reply_photo(
        photo=open(QR_FILE, "rb"),
        caption=f"Pay ₹{price}",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ---------------- UTR ----------------

async def sendutr(update: Update, context):
    await update.callback_query.answer()
    context.user_data["waitutr"] = True
    await update.callback_query.message.reply_text("Send UTR")

async def utr_msg(update: Update, context):
    if not context.user_data.get("waitutr"):
        return

    utr = update.message.text

    try:
        cur.execute("INSERT INTO utr VALUES (?)", (utr,))
        conn.commit()
    except:
        await update.message.reply_text("UTR already used")
        return

    context.user_data["waitutr"] = False

    kb = [
        [
            InlineKeyboardButton("Confirm", callback_data=f"ok_{update.effective_user.id}"),
            InlineKeyboardButton("Wrong", callback_data=f"bad_{update.effective_user.id}")
        ]
    ]

    await context.bot.send_message(
        ADMIN_ID,
        f"UTR: {utr}",
        reply_markup=InlineKeyboardMarkup(kb)
    )

    await update.message.reply_text("Waiting admin confirm")

# ---------------- ADMIN CONFIRM ----------------

async def confirm(update: Update, context):
    q = update.callback_query
    await q.answer()

    uid = int(q.data.split("_")[1])
    t = context.user_data.get("type")
    qty = context.user_data.get("qty")

    table = f"coupons{t}"

    cur.execute(f"SELECT code FROM {table} LIMIT ?", (qty,))
    rows = cur.fetchall()

    if not rows:
        await context.bot.send_message(uid, "Out of stock")
        return

    codes = [r[0] for r in rows]

    for c in codes:
        cur.execute(f"DELETE FROM {table} WHERE code=?", (c,))
        cur.execute("INSERT INTO used VALUES (?)", (c,))

    conn.commit()

    await context.bot.send_message(uid, "\n".join(codes))

async def wrong(update: Update, context):
    q = update.callback_query
    await q.answer()

    uid = int(q.data.split("_")[1])
    await context.bot.send_message(uid, "Wrong UTR, send again")

# ---------------- ADMIN PANEL ----------------

async def admin(update: Update, context):
    kb = [
        ["Add 500 Coupon", "Add 1000 Coupon"],
        ["Set Price 500", "Set Price 1000"],
        ["Set QR"],
        ["Stock"],
        ["Users"],
        ["Broadcast"]
    ]
    await update.message.reply_text(
        "Admin Panel",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

# ---------------- ADD COUPON ----------------

async def add500(update: Update, context):
    context.user_data["add500"] = True
    await update.message.reply_text("Send 500 coupon")

async def add1000(update: Update, context):
    context.user_data["add1000"] = True
    await update.message.reply_text("Send 1000 coupon")

async def save_coupon(update: Update, context):
    code = update.message.text

    if context.user_data.get("add500"):
        cur.execute("INSERT INTO coupons500 VALUES (?)", (code,))
        conn.commit()
        await update.message.reply_text("Added 500 coupon")
        context.user_data["add500"] = False

    elif context.user_data.get("add1000"):
        cur.execute("INSERT INTO coupons1000 VALUES (?)", (code,))
        conn.commit()
        await update.message.reply_text("Added 1000 coupon")
        context.user_data["add1000"] = False

# ---------------- STOCK ----------------

async def stock(update: Update, context):
    cur.execute("SELECT COUNT(*) FROM coupons500")
    s500 = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM coupons1000")
    s1000 = cur.fetchone()[0]

    await update.message.reply_text(
        f"500 stock: {s500}\n1000 stock: {s1000}"
    )

# ---------------- USERS ----------------

async def users(update: Update, context):
    cur.execute("SELECT COUNT(*) FROM users")
    n = cur.fetchone()[0]
    await update.message.reply_text(f"Users: {n}")

# ---------------- BROADCAST ----------------

async def broadcast(update: Update, context):
    context.user_data["bc"] = True
    await update.message.reply_text("Send message")

async def send_bc(update: Update, context):
    if context.user_data.get("bc"):
        cur.execute("SELECT id FROM users")
        for u in cur.fetchall():
            try:
                await context.bot.send_message(u[0], update.message.text)
            except:
                pass

        context.user_data["bc"] = False
        await update.message.reply_text("Sent")

# ---------------- MAIN ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Buy Coupon"), buy))
app.add_handler(CallbackQueryHandler(select_type, pattern="type_"))
app.add_handler(CallbackQueryHandler(qty, pattern="qty_"))

app.add_handler(CallbackQueryHandler(sendutr, pattern="sendutr"))
app.add_handler(MessageHandler(filters.TEXT, utr_msg))

app.add_handler(CallbackQueryHandler(confirm, pattern="ok_"))
app.add_handler(CallbackQueryHandler(wrong, pattern="bad_"))

app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Admin Panel"), admin))

app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Add 500"), add500))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Add 1000"), add1000))
app.add_handler(MessageHandler(filters.TEXT, save_coupon))

app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Stock"), stock))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Users"), users))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Broadcast"), broadcast))
app.add_handler(MessageHandler(filters.TEXT, send_bc))

app.run_polling()
