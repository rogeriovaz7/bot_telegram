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
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # opcional
HF_TOKEN = os.getenv("HF_TOKEN")  # token grátis HuggingFace
MEU_TELEGRAM = os.getenv("MEU_TELEGRAM")  # ex: https://t.me/seuusername
RENDER_URL = os.getenv("RENDER_URL")

if not BOT_TOKEN or not ADMIN_ID or not MEU_TELEGRAM or not RENDER_URL:
    raise RuntimeError("⚠️ Configure BOT_TOKEN, ADMIN_ID, MEU_TELEGRAM e RENDER_URL")

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


async def avisar_admin(produto, preco, user_name, user_id):
    msg = (
        f"📦 Novo pedido recebido!\n"
        f"👤 Usuário: {user_name} ({user_id})\n"
        f"📺 Produto: {produto}\n"
        f"💰 Preço: {preco}€\n"
        f"⏳ Aguardando envio do comprovativo."
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

    mensagem = (
        f"✅ Você escolheu: *{produto['nome']}* - {produto['preco']}€\n\n"
        f"📺 {produto['descricao']}\n\n"
        f"📩 Para enviar o comprovativo do pagamento, envie para: [Meu Telegram]({MEU_TELEGRAM})\n"
        f"⏳ Seu pedido será validado em breve pelo administrador."
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
    prompt = f"Você é um assistente da Loja IPTV Futurista.\nProdutos disponíveis:\n{lista_produtos}\nResponda dúvidas de forma clara e curta."

    resposta = None
    if client:  # OpenAI
        try:
            resposta = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt + "\n" + pergunta}],
            ).choices[0].message.content
        except Exception:
            resposta = "🤖 Ocorreu um erro ao contactar a IA."
    elif HF_TOKEN:  # HuggingFace
        try:
            url = "https://api-inference.huggingface.co/models/declare-lab/flan-alpaca-large"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            payload = {"inputs": prompt + "\nUser: " + pergunta}
            resp = requests.post(url, headers=headers, json=payload)
            data = resp.json()
            resposta = data[0]["generated_text"] if isinstance(data, list) else "🤖 Não consegui responder."
        except Exception:
            resposta = "🤖 Ocorreu um erro ao contactar a IA."

    await update.message.reply_text(resposta)


# =========================
# HANDLER DE COMPROVATIVO
# =========================
async def receber_comprovativo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Envie apenas fotos ou documentos como comprovativo.")
        return

    file = await context.bot.get_file(file_id)
    os.makedirs("comprovativos", exist_ok=True)
    file_path = f"comprovativos/{file_id}"
    await file.download_to_drive(file_path)
    await update.message.reply_text("✅ Comprovativo recebido! O administrador verificará em breve.")


# =========================
# COMANDOS ADMIN
# =========================
async def cmd_pendentes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, produto, preco, status FROM pedidos WHERE status='pendente'")
    pedidos = cursor.fetchall()
    conn.close()

    if not pedidos:
        await update.message.reply_text("✅ Não há pedidos pendentes.")
        return

    msg = "📋 Pedidos pendentes:\n" + "\n".join(
        [f"ID: {p[0]} | Usuário: {p[1]} | Produto: {p[2]} | Preço: {p[3]}€" for p in pedidos]
    )
    await update.message.reply_text(msg)


async def cmd_confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("❌ Use: /confirmar <ID>")
        return

    pedido_id = int(context.args[0])
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE pedidos SET status='confirmado' WHERE id=?", (pedido_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Pedido {pedido_id} confirmado!")


async def cmd_negar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("❌ Use: /negar <ID>")
        return

    pedido_id = int(context.args[0])
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE pedidos SET status='negado' WHERE id=?", (pedido_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"❌ Pedido {pedido_id} negado!")


# =========================
# FASTAPI + TELEGRAM
# =========================
app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()

# Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(callback_router))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_ia))
application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receber_comprovativo))
application.add_handler(CommandHandler("pendentes", cmd_pendentes))
application.add_handler(CommandHandler("confirmar", cmd_confirmar))
application.add_handler(CommandHandler("negar", cmd_negar))

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


