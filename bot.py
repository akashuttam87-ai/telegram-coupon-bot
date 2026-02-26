import sqlite3
import os
import re
from telegram import *
from telegram.ext import *

BOT_TOKEN = os.getenv("8271855633:AAEOQ0ymg-NFiXHhIu2QtNC3dL_cWtmTwxQ")
ADMIN_ID = int(os.getenv("7662708655"))
SUPPORT = "https://t.me/Ark456781"

# DATABASE
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS coupons(id INTEGER PRIMARY KEY, code TEXT UNIQUE, value TEXT, used INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS utrs(utr TEXT UNIQUE)")
cursor.execute("CREATE TABLE IF NOT EXISTS config(key TEXT UNIQUE, value TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS attempts(user INTEGER UNIQUE, count INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS users(user INTEGER UNIQUE)")
conn.commit()

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users VALUES(?)",(user,))
    conn.commit()

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Coupon", callback_data="buy")],
        [InlineKeyboardButton("📞 Support", url=SUPPORT)]
    ]

    await update.message.reply_text(
        "Welcome to Coupon Bot",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- BUY ----------
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("500", callback_data="value_500")],
        [InlineKeyboardButton("1000", callback_data="value_1000")],
        [InlineKeyboardButton("2000", callback_data="value_2000")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    await query.message.reply_text(
        "Select Coupon Value",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- QUANTITY ----------
async def quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    value = query.data.split("_")[1]
    context.user_data["value"] = value

    keyboard = [
        [InlineKeyboardButton("1", callback_data="qty_1"),
         InlineKeyboardButton("2", callback_data="qty_2")],
        [InlineKeyboardButton("5", callback_data="qty_5"),
         InlineKeyboardButton("Custom", callback_data="custom")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    await query.message.reply_text(
        "Select Quantity",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- SEND QR ----------
async def send_qr(update, context, qty):

    value = context.user_data["value"]

    cursor.execute("SELECT value FROM config WHERE key='qr'")
    qr = cursor.fetchone()

    cursor.execute("SELECT value FROM config WHERE key=?", (value,))
    price = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM coupons WHERE value=? AND used=0",(value,))
    stock = cursor.fetchone()[0]

    total = int(price[0]) * qty if price else 0

    context.user_data["qty"] = qty

    await update.callback_query.message.reply_photo(
        photo=open(qr[0],"rb"),
        caption=f"""
Coupon: {value}
Price: ₹{price[0]}
Qty: {qty}
Total: ₹{total}
Stock: {stock}

Send 12 digit UTR
"""
    )

# ---------- UTR ----------
async def receive_utr(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.id
    utr = update.message.text.strip()

    if not re.fullmatch(r"\d{12}", utr):
        return

    cursor.execute("SELECT * FROM utrs WHERE utr=?",(utr,))
    if cursor.fetchone():
        await update.message.reply_text("UTR already used")
        return

    cursor.execute("SELECT count FROM attempts WHERE user=?",(user,))
    data = cursor.fetchone()

    if data and data[0]>=5:
        await update.message.reply_text("Max attempts reached")
        return

    cursor.execute("INSERT OR IGNORE INTO attempts VALUES(?,0)",(user,))
    cursor.execute("UPDATE attempts SET count=count+1 WHERE user=?",(user,))
    conn.commit()

    value=context.user_data["value"]
    qty=context.user_data["qty"]

    keyboard=[
        [InlineKeyboardButton("Approve",callback_data=f"approve_{user}_{utr}_{value}_{qty}")]
    ]

    await context.bot.send_message(
        ADMIN_ID,
        f"User:{user}\nUTR:{utr}\nValue:{value}\nQty:{qty}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text("Sent for admin approval")

# ---------- APPROVE ----------
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query=update.callback_query
    await query.answer()

    _,user,utr,value,qty=query.data.split("_")
    user=int(user)
    qty=int(qty)

    cursor.execute("INSERT INTO utrs VALUES(?)",(utr,))

    cursor.execute("SELECT code FROM coupons WHERE value=? AND used=0 LIMIT ?",(value,qty))
    coupons=cursor.fetchall()

    codes=[]

    for c in coupons:
        codes.append(c[0])
        cursor.execute("UPDATE coupons SET used=1 WHERE code=?",(c[0],))

    conn.commit()

    await context.bot.send_message(user,"\n".join(codes))
    await query.message.reply_text("Approved")

# ---------- ADMIN ----------
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.from_user.id!=ADMIN_ID:
        return

    keyboard=[
        [InlineKeyboardButton("Set QR",callback_data="setqr")],
        [InlineKeyboardButton("Set Price",callback_data="setprice")],
        [InlineKeyboardButton("Add Coupon",callback_data="addcoupon")],
        [InlineKeyboardButton("Stock",callback_data="stock")],
        [InlineKeyboardButton("Broadcast",callback_data="broadcast")]
    ]

    await update.message.reply_text("Admin Panel",reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- BUTTON ----------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data=update.callback_query.data

    if data=="buy":
        await buy(update,context)

    elif data.startswith("value_"):
        await quantity(update,context)

    elif data.startswith("qty_"):
        await send_qr(update,context,int(data.split("_")[1]))

    elif data=="cancel":
        await update.callback_query.message.reply_text("Cancelled")

    elif data.startswith("approve_"):
        await approve(update,context)

# ---------- MAIN ----------
app=ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start",start))
app.add_handler(CommandHandler("admin",admin))

app.add_handler(CallbackQueryHandler(button))

app.add_handler(MessageHandler(filters.TEXT,receive_utr))

print("Bot Running")
app.run_polling()
