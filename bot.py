import os
import sqlite3
from telegram import (
    Update, InlineKeyboardButton,
    InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("8271855633:AAEOQ0ymg-NFiXHhIu2QtNC3dL_cWtmTwxQ")
ADMIN_ID = int(os.getenv("7662708655"))

DB = "database.db"
QR_FILE = "qr.jpg"

# ---------------- DATABASE ----------------

conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
cur.execute("CREATE TABLE IF NOT EXISTS coupons500 (code TEXT UNIQUE)")
cur.execute("CREATE TABLE IF NOT EXISTS coupons1000 (code TEXT UNIQUE)")
cur.execute("CREATE TABLE IF NOT EXISTS used_utrs (utr TEXT UNIQUE)")
cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
conn.commit()

def get_setting(key, default):
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row else default

def set_setting(key, value):
    cur.execute("REPLACE INTO settings VALUES (?,?)", (key, str(value)))
    conn.commit()

# Default Prices
if not get_setting("price500", None):
    set_setting("price500", 20)
if not get_setting("price1000", None):
    set_setting("price1000", 110)

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (uid,))
    conn.commit()

    text = (
        "⚠ Coupon apne risk me le\n"
        "⚡ Instant use kare\n"
        "❌ No replacement"
    )

    buttons = [["🛒 Buy Coupon"], ["📞 Support"]]

    if uid == ADMIN_ID:
        buttons.append(["⚙ Admin Panel"])

    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

# ---------------- BUY SYSTEM ----------------

async def buy(update: Update, context):
    s500 = cur.execute("SELECT COUNT(*) FROM coupons500").fetchone()[0]
    s1000 = cur.execute("SELECT COUNT(*) FROM coupons1000").fetchone()[0]

    p500 = get_setting("price500", 20)
    p1000 = get_setting("price1000", 110)

    keyboard = []

    if s500 > 0:
        keyboard.append([InlineKeyboardButton(f"500₹ (₹{p500}) | Stock {s500}", callback_data="type_500")])
    else:
        keyboard.append([InlineKeyboardButton("❌ 500₹ Out of Stock", callback_data="none")])

    if s1000 > 0:
        keyboard.append([InlineKeyboardButton(f"1000₹ (₹{p1000}) | Stock {s1000}", callback_data="type_1000")])
    else:
        keyboard.append([InlineKeyboardButton("❌ 1000₹ Out of Stock", callback_data="none")])

    await update.message.reply_text("Select Coupon Type",
        reply_markup=InlineKeyboardMarkup(keyboard))

# ---------------- TYPE SELECT ----------------

async def select_type(update: Update, context):
    query = update.callback_query
    await query.answer()

    context.user_data["type"] = query.data.split("_")[1]

    keyboard = [
        [InlineKeyboardButton("1", callback_data="qty_1"),
         InlineKeyboardButton("2", callback_data="qty_2"),
         InlineKeyboardButton("5", callback_data="qty_5")],
        [InlineKeyboardButton("Custom", callback_data="qty_custom")]
    ]

    await query.message.reply_text("Select Quantity",
        reply_markup=InlineKeyboardMarkup(keyboard))

# ---------------- QUANTITY ----------------

async def select_qty(update: Update, context):
    query = update.callback_query
    await query.answer()

    qty = query.data.split("_")[1]

    if qty == "custom":
        context.user_data["custom"] = True
        await query.message.reply_text("Send quantity number")
        return

    await show_payment(query.message, context, int(qty))

async def custom_qty(update: Update, context):
    if context.user_data.get("custom"):
        qty = int(update.message.text)
        context.user_data["custom"] = False
        await show_payment(update.message, context, qty)

# ---------------- PAYMENT ----------------

async def show_payment(msg, context, qty):
    ctype = context.user_data["type"]
    price = int(get_setting(f"price{ctype}", 0))
    total = price * qty

    context.user_data["qty"] = qty

    keyboard = [
        [InlineKeyboardButton("Send UTR", callback_data="sendutr")]
    ]

    await msg.reply_photo(
        photo=open(QR_FILE, "rb"),
        caption=f"Pay ₹{total} and send UTR",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------------- UTR ----------------

async def ask_utr(update: Update, context):
    await update.callback_query.answer()
    context.user_data["wait_utr"] = True
    await update.callback_query.message.reply_text("Send 12 digit UTR")

async def receive_utr(update: Update, context):
    if not context.user_data.get("wait_utr"):
        return

    utr = update.message.text

    if not utr.isdigit() or len(utr) != 12:
        await update.message.reply_text("Invalid UTR")
        return

    try:
        cur.execute("INSERT INTO used_utrs VALUES (?)", (utr,))
        conn.commit()
    except:
        await update.message.reply_text("UTR already used")
        return

    context.user_data["wait_utr"] = False

    user_id = update.effective_user.id
    qty = context.user_data["qty"]
    ctype = context.user_data["type"]

    keyboard = [[
        InlineKeyboardButton("Approve", callback_data=f"ok_{user_id}_{ctype}_{qty}"),
        InlineKeyboardButton("Wrong", callback_data=f"bad_{user_id}")
    ]]

    await context.bot.send_message(
        ADMIN_ID,
        f"Payment Received\nUser: {user_id}\nUTR: {utr}\nQty: {qty}\nType: {ctype}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text("Waiting for admin approval")

# ---------------- ADMIN CONFIRM ----------------

async def confirm(update: Update, context):
    query = update.callback_query
    await query.answer()

    _, uid, ctype, qty = query.data.split("_")
    uid = int(uid)
    qty = int(qty)

    table = f"coupons{ctype}"

    available = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    if available < qty:
        await context.bot.send_message(uid, "❌ Out of Stock")
        return

    rows = cur.execute(f"SELECT code FROM {table} LIMIT ?", (qty,)).fetchall()
    codes = [r[0] for r in rows]

    for code in codes:
        cur.execute(f"DELETE FROM {table} WHERE code=?", (code,))
    conn.commit()

    await context.bot.send_message(uid, "✅ Coupons:\n" + "\n".join(codes))

async def wrong(update: Update, context):
    await update.callback_query.answer()
    uid = int(update.callback_query.data.split("_")[1])
    await context.bot.send_message(uid, "Wrong UTR")

# ---------------- ADMIN PANEL ----------------

async def admin_panel(update: Update, context):
    buttons = [
        ["➕ Add 500 Coupon", "➕ Add 1000 Coupon"],
        ["💰 Set Price 500", "💰 Set Price 1000"],
        ["📦 Stock", "👥 Users"],
        ["📢 Broadcast", "🖼 Set QR"]
    ]
    await update.message.reply_text("Admin Panel",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))

# -------- ADD COUPON --------

async def add_coupon(update: Update, context):
    if "500" in update.message.text:
        context.user_data["add"] = "500"
    else:
        context.user_data["add"] = "1000"
    await update.message.reply_text("Send coupons (one per line)")

async def save_coupon(update: Update, context):
    if not context.user_data.get("add"):
        return

    table = f"coupons{context.user_data['add']}"
    lines = update.message.text.splitlines()

    for code in lines:
        try:
            cur.execute(f"INSERT INTO {table} VALUES (?)", (code.strip(),))
        except:
            pass

    conn.commit()
    context.user_data["add"] = None
    await update.message.reply_text("Coupons Added")

# -------- SET PRICE --------

async def set_price(update: Update, context):
    if "500" in update.message.text:
        context.user_data["price"] = "price500"
    else:
        context.user_data["price"] = "price1000"
    await update.message.reply_text("Send new price")

async def save_price(update: Update, context):
    key = context.user_data.get("price")
    if key:
        set_setting(key, update.message.text)
        context.user_data["price"] = None
        await update.message.reply_text("Price Updated")

# -------- SET QR --------

async def set_qr(update: Update, context):
    context.user_data["qr"] = True
    await update.message.reply_text("Send new QR photo")

async def save_qr(update: Update, context):
    if context.user_data.get("qr") and update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        await file.download_to_drive(QR_FILE)
        context.user_data["qr"] = None
        await update.message.reply_text("QR Updated")

# -------- STOCK --------

async def stock(update: Update, context):
    s500 = cur.execute("SELECT COUNT(*) FROM coupons500").fetchone()[0]
    s1000 = cur.execute("SELECT COUNT(*) FROM coupons1000").fetchone()[0]
    await update.message.reply_text(f"500: {s500}\n1000: {s1000}")

# -------- USERS --------

async def users(update: Update, context):
    total = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    await update.message.reply_text(f"Total Users: {total}")

# -------- BROADCAST --------

async def broadcast(update: Update, context):
    context.user_data["broadcast"] = True
    await update.message.reply_text("Send message to broadcast")

async def send_broadcast(update: Update, context):
    if context.user_data.get("broadcast"):
        ids = cur.execute("SELECT id FROM users").fetchall()
        for u in ids:
            try:
                await context.bot.send_message(u[0], update.message.text)
            except:
                pass
        context.user_data["broadcast"] = False
        await update.message.reply_text("Broadcast Sent")

# ---------------- MAIN ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Buy Coupon"), buy))
app.add_handler(CallbackQueryHandler(select_type, pattern="type_"))
app.add_handler(CallbackQueryHandler(select_qty, pattern="qty_"))
app.add_handler(CallbackQueryHandler(ask_utr, pattern="sendutr"))
app.add_handler(CallbackQueryHandler(confirm, pattern="ok_"))
app.add_handler(CallbackQueryHandler(wrong, pattern="bad_"))

app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Admin Panel"), admin_panel))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Add"), add_coupon))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Set Price"), set_price))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Stock"), stock))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Users"), users))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Broadcast"), broadcast))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("Set QR"), set_qr))

app.add_handler(MessageHandler(filters.TEXT, save_coupon))
app.add_handler(MessageHandler(filters.TEXT, save_price))
app.add_handler(MessageHandler(filters.PHOTO, save_qr))
app.add_handler(MessageHandler(filters.TEXT, receive_utr))
app.add_handler(MessageHandler(filters.TEXT, custom_qty))
app.add_handler(MessageHandler(filters.TEXT, send_broadcast))

app.run_polling()
