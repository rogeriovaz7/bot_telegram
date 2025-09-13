import json
import sqlite3
import os
import qrcode
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
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
DB_FILE = "pedidos.db"
os.makedirs("qrcodes", exist_ok=True)

# =========================
# BANCO DE DADOS
# =========================
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Tabela de pedidos
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    produto TEXT,
    preco REAL,
    status TEXT,
    link TEXT
)
"""
)

# Tabela de usuários (para intro)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS usuarios (
    user_id INTEGER PRIMARY KEY
)
"""
)

conn.commit()
conn.close()

with open("produtos.json", "r", encoding="utf-8") as f:
    produtos = json.load(f)


# =========================
# FUNÇÕES DE PAGAMENTO E REGISTRO
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


def criar_link_paypal(preco):
    return f"https://www.paypal.com/paypalme/{PAYPAL_USER}/{preco}"


def gerar_qrcode_mbway(user_id, produto_id, preco):
    texto = f"Pagar {preco}€ para MB WAY: {MBWAY_NUMERO}"
    qr_file = f"qrcodes/{user_id}_{produto_id}.png"
    img = qrcode.make(texto)
    img.save(qr_file)
    return qr_file


def criar_instrucao_skrill(preco, produto):
    return (
        f"💳 Para pagar com *Skrill*:\n\n"
        f"➡️ Envie {preco}€ para o email: *{SKRILL_EMAIL}*\n"
        f"📝 Referência: *Compra IPTV - {produto}*\n\n"
        f"⚠️ Após o pagamento, envie o comprovativo ao suporte."
    )


async def avisar_admin(produto, preco, user_name, user_id):
    msg = (
        f"📦 Novo pedido recebido!\n"
        f"👤 Usuário: {user_name} ({user_id})\n"
        f"📺 Produto: {produto}\n"
        f"💰 Preço: {preco}€\n"
        f"⏳ Aguardando confirmação de pagamento."
    )
    await application.bot.send_message(chat_id=ADMIN_ID, text=msg)


# =========================
# HANDLERS DO BOT
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM usuarios WHERE user_id = ?", (user_id,))
    visto = cursor.fetchone()

    if not visto:
        # Enviar intro só na primeira vez
        intro_path = "intro.mp4"  # Coloque o vídeo na raiz do projeto
        if os.path.exists(intro_path):
            await update.message.reply_video(open(intro_path, "rb"), caption="🚀 Bem-vindo à Loja IPTV Futurista!")
        # Registra que já viu
        cursor.execute("INSERT INTO usuarios (user_id) VALUES (?)", (user_id,))
        conn.commit()

    conn.close()

    keyboard = [[InlineKeyboardButton("🚀 Iniciar", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Bem-vindo à *Loja IPTV Futurista*!\n\nClique em *Iniciar* para ver os planos disponíveis.",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [
            InlineKeyboardButton(
                f"📺 {produto['nome']} - {produto['preco']}€",
                callback_data=f"produto_{key}",
            )
        ]
        for key, produto in produtos.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(
        "🚀 Escolha um dos planos IPTV futuristas abaixo:", reply_markup=reply_markup
    )


async def mostrar_produto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_id = query.data.replace("produto_", "")
    produto = produtos[item_id]
    caption = f"📺 *{produto['nome']}*\n💰 {produto['preco']}€\n\nℹ️ {produto['descricao']}"
    keyboard = [
        [InlineKeyboardButton("🛒 Comprar Agora", callback_data=f"comprar_{item_id}")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu", callback_data="menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_photo(
        open(produto["imagem"], "rb"), caption=caption, parse_mode="Markdown", reply_markup=reply_markup
    )


async def comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_id = query.data.replace("comprar_", "")
    produto = produtos[item_id]
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    registrar_pedido(user_id, produto["nome"], produto["preco"], produto["link"])
    await avisar_admin(produto["nome"], produto["preco"], user_name, user_id)
    qr_file = gerar_qrcode_mbway(user_id, item_id, produto["preco"])
    paypal_link = criar_link_paypal(produto["preco"])
    skrill_instrucao = criar_instrucao_skrill(produto["preco"], produto["nome"])
    mensagem = (
        f"✅ Você escolheu: *{produto['nome']}* - {produto['preco']}€\n\n"
        f"📺 {produto['descricao']}\n\n"
        f"💳 Métodos de Pagamento:\n"
        f"👉 PayPal: {paypal_link}\n"
        f"👉 MB WAY: *{MBWAY_NUMERO}* (QR code abaixo)\n"
        f"👉 Skrill: veja instruções abaixo 👇\n\n"
        f"{skrill_instrucao}\n\n"
        "Após o pagamento, aguarde liberação do acesso."
    )
    await query.message.reply_photo(open(qr_file, "rb"), caption=mensagem, parse_mode="Markdown")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "menu":
        await mostrar_menu(update, context)
    elif query.data.startswith("produto_"):
        await mostrar_produto(update, context)
    elif query.data.startswith("comprar_"):
        await comprar(update, context)


# =========================
# FASTAPI + WEBHOOK
# =========================
app = FastAPI()
application = Application.builder().token(TOKEN).updater(None).build()

# Registrar handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(callback_router))


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)

    await application.update_queue.put(update)
    return {"status": "ok"}


@app.get("/")
def home():
    return {"status": "🤖 Bot IPTV Futurista ativo!"}


async def start_webhook():
    webhook_url = f"https://{RENDER_URL}/webhook"
    await application.bot.set_webhook(webhook_url)
    print(f"🌐 Webhook configurado: {webhook_url}")


@app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.start()
    asyncio.create_task(start_webhook())


@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()


