import json
import sqlite3
import os
import asyncio
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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAYPAL_USER = os.getenv("PAYPAL_USER")
RENDER_URL = os.getenv("RENDER_URL")
MEU_TELEGRAM = os.getenv("MEU_TELEGRAM")  # seu usuário Telegram sem @

if not TOKEN or not ADMIN_ID or not OPENAI_API_KEY or not PAYPAL_USER or not RENDER_URL or not MEU_TELEGRAM:
    raise RuntimeError("⚠️ Configure BOT_TOKEN, ADMIN_ID, OPENAI_API_KEY, PAYPAL_USER, RENDER_URL e MEU_TELEGRAM")

DB_FILE = "pedidos.db"

client = OpenAI(api_key=OPENAI_API_KEY)

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS historico (
    user_id INTEGER,
    role TEXT,
    mensagem TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

with open("produtos.json", "r", encoding="utf-8") as f:
    produtos = json.load(f)

# =========================
# HISTÓRICO E IA CHATGPT
# =========================
def salvar_historico(user_id, role, mensagem):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO historico (user_id, role, mensagem) VALUES (?, ?, ?)",
        (user_id, role, mensagem),
    )
    conn.commit()
    conn.close()

def resumir_historico(user_id, max_msgs=10):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, mensagem FROM historico WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, max_msgs)
    )
    rows = cursor.fetchall()
    conn.close()
    rows = rows[::-1]
    return [{"role": r, "content": m} for r, m in rows]

def obter_resposta_chatgpt(pergunta: str, user_id: int) -> str:
    """
    Responde usando ChatGPT GPT-3.5
    """
    lista_produtos = "\n".join(
        [f"- {k}: {p['nome']} ({p['preco']}€) → {p['descricao']}" for k, p in produtos.items()]
    )
    historico = resumir_historico(user_id)
    
    messages = [{"role": "system", "content": f"Você é um assistente simpático da Loja IPTV Futurista. Produtos:\n{lista_produtos}"}]
    for h in historico:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": pergunta})

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        resposta = resp.choices[0].message.content
    except Exception as e:
        resposta = f"🤖 Ocorreu um erro ao contactar a IA: {e}"

    salvar_historico(user_id, "user", pergunta)
    salvar_historico(user_id, "assistant", resposta)
    return resposta

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
# HANDLERS TELEGRAM
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
        [InlineKeyboardButton(f"📺 {p['nome']} - {p['preco']}€", callback_data=f"produto_{k}")]
        for k, p in produtos.items()
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
        f"📩 Após realizar o pagamento, envie o comprovativo clicando aqui: "
        f"[@{MEU_TELEGRAM}](https://t.me/{MEU_TELEGRAM})\n"
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

async def responder_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    pergunta = update.message.text
    resposta = obter_resposta_chatgpt(pergunta, user_id)
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
    return {"status": "🤖 Bot IPTV Futurista com ChatGPT ativo!"}

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
