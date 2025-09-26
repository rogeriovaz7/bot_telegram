import json
import sqlite3
import os
import asyncio
import requests
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from openai import OpenAI

# =========================
# CONFIGURAÇÃO
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # opcional
HF_TOKEN = os.getenv("HF_TOKEN")  # token grátis do HuggingFace
PAYPAL_USER = os.getenv("PAYPAL_USER")
RENDER_URL = os.getenv("RENDER_URL")

if not TOKEN or not ADMIN_ID or not RENDER_URL:
    raise RuntimeError("⚠️ Configure BOT_TOKEN, ADMIN_ID, PAYPAL_USER, RENDER_URL")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
DB_FILE = "pedidos.db"

# =========================
# BANCO DE DADOS
# =========================
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

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
# FUNÇÕES DE LOJA
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
# HANDLERS DA LOJA
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🚀 Iniciar Loja", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Bem-vindo à *Loja IPTV Futurista*!\n\nClique em *Iniciar Loja* para ver os planos disponíveis.\n\n"
        "💡 Também pode conversar comigo — sou uma IA que responde dúvidas e ajuda a escolher o plano certo.",
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
    await query.message.reply_text("🚀 Escolha um dos planos IPTV futuristas abaixo:", reply_markup=reply_markup)


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
        open(produto["imagem"], "rb"),
        caption=caption,
        parse_mode="Markdown",
        reply_markup=reply_markup,
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

    paypal_link = criar_link_paypal(produto["preco"])

    mensagem = (
        f"✅ Você escolheu: *{produto['nome']}* - {produto['preco']}€\n\n"
        f"📺 {produto['descricao']}\n\n"
        f"💳 Pague com PayPal: {paypal_link}\n\n"
        f"📩 Após realizar o pagamento, envie o comprovativo aqui no Telegram.\n"
        f"⏳ Seu pedido será validado e liberado em breve."
    )

    await query.message.reply_photo(
        open(produto["imagem"], "rb"),
        caption=mensagem,
        parse_mode="Markdown",
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "menu":
        await mostrar_menu(update, context)
    elif query.data.startswith("produto_"):
        await mostrar_produto(update, context)
    elif query.data.startswith("comprar_"):
        await comprar(update, context)


# =========================
# HANDLER DE IA
# =========================
async def responder_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pergunta = update.message.text

    lista_produtos = "\n".join(
        [f"- {k}: {p['nome']} ({p['preco']}€) → {p['descricao']}" for k, p in produtos.items()]
    )

    prompt = f"""
Você é um assistente da Loja IPTV Futurista.

Produtos disponíveis:
{lista_produtos}

Tarefas:
- Responda dúvidas normais do utilizador.
- Se mencionar preço, tempo ou plano, recomende o mais adequado.
- Responda de forma simpática, curta e clara.
"""

    resposta = None
    if client:  # usa OpenAI se disponível
        resposta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": pergunta},
            ],
        ).choices[0].message.content
    elif HF_TOKEN:  # fallback HuggingFace grátis
        url = "https://api-inference.huggingface.co/models/meta-llama/Meta-Llama-3-8B-Instruct"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": prompt + "\nUser: " + pergunta}
        resp = requests.post(url, headers=headers, json=payload)
        data = resp.json()
        resposta = data[0]["generated_text"] if isinstance(data, list) else "Desculpe, não consegui responder."

    if not resposta:
        resposta = "🤖 Desculpe, não consegui responder agora."

    # Se a resposta indicar um produto, mostramos os botões
    keyboard = []
    for key, p in produtos.items():
        if str(p["preco"]) in resposta or p["nome"].lower() in resposta.lower():
            keyboard.append([InlineKeyboardButton(f"🛒 Comprar {p['nome']}", callback_data=f"comprar_{key}")])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(resposta, reply_markup=reply_markup)


# =========================
# FASTAPI + WEBHOOK
# =========================
app = FastAPI()
application = Application.builder().token(TOKEN).updater(None).build()

# Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(callback_router))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_ia))


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"status": "ok"}


@app.get("/")
def home():
    return {"status": "🤖 Bot IPTV Futurista com IA ativo!"}


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



