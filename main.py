
import os
import sqlite3
import logging
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
import asyncio

# =========================
# CONFIGURAÇÕES
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PAYPAL_USER = os.getenv("PAYPAL_USER")
RENDER_URL = os.getenv("RENDER_URL")
MEU_TELEGRAM = os.getenv("MEU_TELEGRAM")  # teu username sem @

if not all([BOT_TOKEN, ADMIN_ID, PAYPAL_USER, RENDER_URL, MEU_TELEGRAM]):
    raise RuntimeError("⚠️ Configure BOT_TOKEN, ADMIN_ID, PAYPAL_USER, RENDER_URL e MEU_TELEGRAM")

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)

# =========================
# FASTAPI
# =========================
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "Bot ativo com webhook 🚀"}

# =========================
# BANCO DE DADOS
# =========================
DB_FILE = "pedidos.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            produto TEXT,
            preco REAL,
            link TEXT,
            status TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

def registrar_pedido(user_id, produto, preco, link):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO pedidos (user_id, produto, preco, link, status) VALUES (?, ?, ?, ?, ?)",
              (user_id, produto, preco, link, "pendente"))
    conn.commit()
    conn.close()

def atualizar_status(user_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE pedidos SET status=? WHERE user_id=? ORDER BY id DESC LIMIT 1", (status, user_id))
    conn.commit()
    conn.close()

def listar_pendentes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, user_id, produto, preco FROM pedidos WHERE status='pendente'")
    rows = c.fetchall()
    conn.close()
    return rows

def ja_viu_intro(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM usuarios WHERE user_id=?", (user_id,))
    visto = c.fetchone() is not None
    conn.close()
    return visto

def marcar_intro_vista(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO usuarios (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

# =========================
# PRODUTOS
# =========================
produtos = {
    "1": {"nome": "Plano Mensal", "preco": 10, "descricao": "Acesso IPTV 30 dias", "imagem": "banners/intro.png"},
    "2": {"nome": "Plano Trimestral", "preco": 25, "descricao": "Acesso IPTV 90 dias", "imagem": "banners/intro.png"},
    "3": {"nome": "Plano Anual", "preco": 80, "descricao": "Acesso IPTV 365 dias", "imagem": "banners/intro.png"},
}

# =========================
# INICIALIZAÇÃO DO BOT
# =========================
application = Application.builder().token(BOT_TOKEN).build()

# =========================
# FUNÇÕES BOT
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not ja_viu_intro(user_id):
        video_path = "banners/intro.mp4"
        await update.message.reply_video(open(video_path, "rb"), caption="🎬 Bem-vindo à Loja IPTV Futurista!")
        marcar_intro_vista(user_id)

    # Mostra os planos
    keyboard = [
        [InlineKeyboardButton(f"{p['nome']} - {p['preco']}€", callback_data=f"comprar_{id}")]
        for id, p in produtos.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Escolha um plano IPTV abaixo:",
        reply_markup=reply_markup,
    )

async def comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_id = query.data.replace("comprar_", "")
    produto = produtos[item_id]
    user_id = query.from_user.id
    registrar_pedido(user_id, produto["nome"], produto["preco"], produto["imagem"])

    paypal_link = f"https://paypal.me/{PAYPAL_USER}/{produto['preco']}"

    mensagem = (
        f"✅ Você escolheu: *{produto['nome']}* - {produto['preco']}€\n\n"
        f"📺 {produto['descricao']}\n\n"
        f"💳 Pague com PayPal: {paypal_link}\n\n"
        f"📩 Após realizar o pagamento, envie o comprovativo clicando no botão abaixo."
    )

    keyboard = [
        [InlineKeyboardButton("📩 Enviar comprovativo no privado", url=f"https://t.me/{MEU_TELEGRAM}")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_photo(
        open(produto["imagem"], "rb"),
        caption=mensagem,
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

async def receber_comprovativo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if update.message.photo or update.message.document:
        await update.message.reply_text("✅ Comprovativo recebido! Aguarde confirmação.")

        caption = f"📩 Comprovativo de {user.full_name} (@{user.username}, ID: {user.id})"

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data=f"confirmar_{user.id}"),
                InlineKeyboardButton("❌ Negar", callback_data=f"negar_{user.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.message.photo:
            await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id,
                                         caption=caption, reply_markup=reply_markup)
        elif update.message.document:
            await context.bot.send_document(ADMIN_ID, update.message.document.file_id,
                                           caption=caption, reply_markup=reply_markup)
    else:
        await update.message.reply_text("⚠️ Envie o comprovativo como foto ou documento.")

async def callback_comprovativo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, user_id_str = data.split("_")
    user_id = int(user_id_str)

    if query.from_user.id != ADMIN_ID:
        await query.message.reply_text("❌ Apenas o ADMIN pode usar este botão.")
        return

    if action == "confirmar":
        atualizar_status(user_id, "confirmado")
        await context.bot.send_message(user_id, "🎉 Pagamento confirmado! Seu plano foi ativado. Aproveite o IPTV 🚀")
        await query.message.edit_caption(query.message.caption + "\n\n✅ Pagamento confirmado pelo ADMIN")
    elif action == "negar":
        atualizar_status(user_id, "negado")
        await context.bot.send_message(user_id,
            "⚠️ Seu comprovativo não foi aprovado. Envie novamente um comprovativo válido."
        )
        await query.message.edit_caption(query.message.caption + "\n\n❌ Pagamento negado pelo ADMIN")

# =========================
# COMANDOS ADMIN
# =========================
async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Não autorizado.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Use: /confirmar <id_do_usuario>")
        return
    try:
        user_id = int(context.args[0])
        atualizar_status(user_id, "confirmado")
        await context.bot.send_message(user_id, "🎉 Pagamento confirmado! Seu plano foi ativado. Aproveite o IPTV 🚀")
        await update.message.reply_text(f"✅ Pagamento confirmado para usuário {user_id}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro ao confirmar: {e}")

async def negar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Não autorizado.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Use: /negar <id_do_usuario>")
        return
    try:
        user_id = int(context.args[0])
        atualizar_status(user_id, "negado")
        await context.bot.send_message(user_id,
            "⚠️ Seu comprovativo não foi aprovado. Envie novamente um comprovativo válido."
        )
        await update.message.reply_text(f"❌ Pagamento negado para usuário {user_id}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro ao negar: {e}")

async def pendentes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Não autorizado.")
        return
    pedidos = listar_pendentes()
    if not pedidos:
        await update.message.reply_text("✅ Não há pedidos pendentes.")
        return
    resposta = "📋 *Pedidos pendentes:*\n\n"
    for pid, user_id, produto, preco in pedidos:
        resposta += f"🆔 Pedido {pid} | 👤 User {user_id}\n📦 {produto} - {preco}€\n\n"
    await update.message.reply_text(resposta, parse_mode="Markdown")

# =========================
# HANDLERS
# =========================
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(comprar, pattern="^comprar_"))
application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receber_comprovativo))
application.add_handler(CallbackQueryHandler(callback_comprovativo, pattern="^(confirmar|negar)_"))
application.add_handler(CommandHandler("confirmar", confirmar))
application.add_handler(CommandHandler("negar", negar))
application.add_handler(CommandHandler("pendentes", pendentes))

# =========================
# WEBHOOK FASTAPI
# =========================
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    init_db()
    await application.initialize()
    await application.start()
    webhook_url = f"https://{RENDER_URL}/webhook"
    await application.bot.set_webhook(webhook_url)
    print(f"🌐 Webhook configurado: {webhook_url}")

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
