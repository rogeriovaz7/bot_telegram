import os
import sqlite3
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from openai import OpenAI

# =========================
# CONFIGURAÇÃO VIA VARIÁVEIS DE AMBIENTE
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAYPAL_USER = os.getenv("PAYPAL_USER")
MBWAY_NUMERO = os.getenv("MBWAY_NUMERO")
SKRILL_EMAIL = os.getenv("SKRILL_EMAIL")
RENDER_URL = os.getenv("RENDER_URL")

if not TOKEN or not OPENAI_API_KEY or not ADMIN_ID or not RENDER_URL:
    raise RuntimeError(
        "⚠️ Configure todas as variáveis de ambiente: BOT_TOKEN, ADMIN_ID, OPENAI_API_KEY, RENDER_URL"
    )

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# BANCO DE DADOS
# =========================
DB_FILE = "database.db"
if not os.path.exists(DB_FILE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, first_time INTEGER)")
    c.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, produto TEXT, status TEXT)")
    conn.commit()
    conn.close()

# =========================
# BOT TELEGRAM
# =========================
application = Application.builder().token(TOKEN).build()

# IA integrada
async def responder_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        resposta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": user_text}],
        )
        reply = resposta.choices[0].message.content
    except Exception as e:
        reply = f"⚠️ Erro na IA: {e}"
    await update.message.reply_text(reply)

# Menu principal
async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Produto 1", callback_data="produto_1")],
        [InlineKeyboardButton("Produto 2", callback_data="produto_2")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text("📦 Escolhe um produto:", reply_markup=reply_markup)

# Produto
async def mostrar_produto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    produto_id = query.data.split("_")[1]
    keyboard = [[InlineKeyboardButton("Comprar ✅", callback_data=f"comprar_{produto_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(f"🛒 Produto {produto_id}\nPreço: 10€", reply_markup=reply_markup)

# Comprar
async def comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    produto_id = query.data.split("_")[1]

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO orders (user_id, produto, status) VALUES (?, ?, ?)",
              (query.from_user.id, f"Produto {produto_id}", "pendente"))
    order_id = c.lastrowid
    conn.commit()
    conn.close()

    # Notificar cliente
    await query.message.reply_text(
        f"💳 Envia o pagamento para PayPal: {PAYPAL_USER}\n"
        f"ou MBWAY: {MBWAY_NUMERO}\n"
        f"ou Skrill: {SKRILL_EMAIL}\n\n"
        "Depois envia o comprovativo para o admin."
    )

    # Notificar admin
    keyboard = [
        [InlineKeyboardButton("✅ Aprovar", callback_data=f"aprovar_{order_id}")],
        [InlineKeyboardButton("❌ Negar", callback_data=f"negar_{order_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if ADMIN_ID != 0:
        await application.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📢 Novo pagamento pendente!\n\nPedido #{order_id}\nCliente: @{query.from_user.username}\nProduto: {produto_id}",
            reply_markup=reply_markup
        )

# Admin decisão
async def admin_decisao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, order_id = query.data.split("_")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    row = c.fetchone()
    if not row:
        await query.message.reply_text("⚠️ Pedido não encontrado.")
        return

    user_id = row[0]

    if action == "aprovar":
        c.execute("UPDATE orders SET status=? WHERE id=?", ("aprovado", order_id))
        await application.bot.send_message(chat_id=user_id, text="✅ O teu pagamento foi aprovado! O serviço está ativo.")
    elif action == "negar":
        c.execute("UPDATE orders SET status=? WHERE id=?", ("negado", order_id))
        await application.bot.send_message(chat_id=user_id, text="❌ O teu pagamento foi negado. Revê o comprovativo.")
    conn.commit()
    conn.close()

    await query.message.reply_text(f"Admin decidiu: {action.upper()} para pedido #{order_id}")

# Callback router
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "menu":
        await mostrar_menu(update, context)
    elif query.data.startswith("produto_"):
        await mostrar_produto(update, context)
    elif query.data.startswith("comprar_"):
        await comprar(update, context)

# Start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT first_time FROM users WHERE id=?", (update.effective_user.id,))
    row = c.fetchone()

    if row is None:
        c.execute("INSERT INTO users (id, username, first_time) VALUES (?, ?, ?)",
                  (update.effective_user.id, update.effective_user.username, 1))
        conn.commit()
        conn.close()

        # Primeira vez → vídeo
        video_path = "intro.mp4"
        if os.path.exists(video_path):
            await update.message.reply_video(video=open(video_path, "rb"))
        await update.message.reply_text("👋 Bem-vindo ao Bot! Usa o menu abaixo:")
    else:
        conn.close()
        await update.message.reply_text("👋 Bem-vindo de volta! Usa o menu abaixo:")

    keyboard = [[InlineKeyboardButton("📦 Menu", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Escolhe uma opção:", reply_markup=reply_markup)

# =========================
# HANDLERS
# =========================
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(callback_router, pattern="^(menu|produto_|comprar_)"))
application.add_handler(CallbackQueryHandler(admin_decisao, pattern="^(aprovar|negar)_"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_ia))

# =========================
# FASTAPI WEBHOOK
# =========================
app = FastAPI()

@app.post(f"/{TOKEN}")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.on_event("startup")
async def startup_event():
    await application.initialize()
    await application.start()
    if RENDER_URL:
        await application.bot.set_webhook(f"{RENDER_URL}/{TOKEN}")

@app.on_event("shutdown")
async def shutdown_event():
    await application.stop()

# =========================
# EXECUÇÃO LOCAL OU RENDER
# =========================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))  # Render define $PORT, local usa 10000
    uvicorn.run("main:app", host="0.0.0.0", port=port)
