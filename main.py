import os
import json
import sqlite3
import qrcode
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

# =========================
# CONFIGURAÇÃO VIA VARIÁVEIS DE AMBIENTE
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RENDER_URL = os.getenv("RENDER_URL")

if not TOKEN or not OPENAI_API_KEY or not ADMIN_ID or not RENDER_URL:
    raise RuntimeError("⚠️ Configure BOT_TOKEN, ADMIN_ID, OPENAI_API_KEY e RENDER_URL")

client = OpenAI(api_key=OPENAI_API_KEY)
DB_FILE = "pedidos.db"
os.makedirs("qrcodes", exist_ok=True)

# =========================
# BANCO DE DADOS
# =========================
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    produto TEXT,
    preco REAL,
    status TEXT,
    link TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    user_id INTEGER PRIMARY KEY
)
""")
conn.commit()
conn.close()

with open("produtos.json", "r", encoding="utf-8") as f:
    produtos = json.load(f)

# =========================
# FUNÇÕES AUXILIARES
# =========================
def registrar_pedido(user_id, produto, preco, link):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pedidos (user_id, produto, preco, status, link) VALUES (?, ?, ?, ?, ?)",
        (user_id, produto, preco, "pendente", link),
    )
    conn.commit()
    conn.close()


def gerar_qrcode_mbway(user_id, produto_id, preco):
    texto = f"Pagar {preco}€ para MB WAY"
    qr_file = f"qrcodes/{user_id}_{produto_id}.png"
    img = qrcode.make(texto)
    img.save(qr_file)
    return qr_file


# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO usuarios (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    keyboard = [[InlineKeyboardButton("🚀 Iniciar", callback_data="menu")]]
    await update.message.reply_text(
        "👋 Bem-vindo! Clique em Iniciar para ver os planos.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(f"{p['nome']} - {p['preco']}€", callback_data=f"produto_{key}")]
        for key, p in produtos.items()
    ]
    await query.message.reply_text("Escolha seu plano:", reply_markup=InlineKeyboardMarkup(keyboard))


async def mostrar_produto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    produto_id = query.data.split("_")[1]
    produto = produtos[produto_id]
    caption = f"{produto['nome']} - {produto['preco']}€\n{produto['descricao']}"
    keyboard = [[InlineKeyboardButton("🛒 Comprar", callback_data=f"comprar_{produto_id}")]]
    await query.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))


async def comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    produto_id = query.data.split("_")[1]
    produto = produtos[produto_id]
    user_id = query.from_user.id
    registrar_pedido(user_id, produto["nome"], produto["preco"], "")
    qr_file = gerar_qrcode_mbway(user_id, produto_id, produto["preco"])
    await query.message.reply_photo(open(qr_file, "rb"), caption=f"Pedido registrado: {produto['nome']} - {produto['preco']}€")


async def responder_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    prompt = f"Usuário perguntou: '{user_msg}'\nSugira o melhor produto disponível: {json.dumps(produtos, ensure_ascii=False)}"
    resposta = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    reply_text = resposta.choices[0].message.content
    await update.message.reply_text(reply_text)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "menu":
        await mostrar_menu(update, context)
    elif data.startswith("produto_"):
        await mostrar_produto(update, context)
    elif data.startswith("comprar_"):
        await comprar(update, context)


# =========================
# FASTAPI + WEBHOOK
# =========================
app = FastAPI()
application: Application = None  # Será inicializado no startup


@app.on_event("startup")
async def startup():
    global application
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_ia))
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(f"https://{RENDER_URL}/webhook")


@app.on_event("shutdown")
async def shutdown():
    if application:
        await application.stop()


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}


@app.get("/")
def home():
    return {"status": "Bot ativo!"}


