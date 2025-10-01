import json
import sqlite3
import os
import qrcode
import asyncio
from fastapi import FastAPI, Request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Bot,
)
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

# =========================
# NOTIFICAÇÃO PARA ADMIN
# =========================
async def avisar_admin(pedido_id, produto, preco, user_name, user_id):
    msg = (
        f"📦 Novo pedido recebido!\n"
        f"👤 Usuário: {user_name} ({user_id})\n"
        f"📺 Produto: {produto}\n"
        f"💰 Preço: {preco}€\n"
        f"⏳ Aguardando confirmação de pagamento."
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Aprovar", callback_data=f"aprovar_{pedido_id}_{user_id}"),
            InlineKeyboardButton("❌ Negar", callback_data=f"negar_{pedido_id}_{user_id}"),
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await application.bot.send_message(chat_id=ADMIN_ID, text=msg, reply_markup=reply_markup)

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
        intro_path = os.path.join("banners", "intro.mp4")
        if os.path.exists(intro_path):
            await update.message.reply_video(open(intro_path, "rb"), caption="🚀 Bem-vindo à Loja IPTV Futurista!")
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

    # registra no banco
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pedidos (user_id, produto, preco, status, link) VALUES (?, ?, ?, ?, ?)",
        (user_id, produto["nome"], produto["preco"], "pendente", produto["link"]),
    )
    pedido_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # avisa admin
    await avisar_admin(pedido_id, produto["nome"], produto["preco"], user_name, user_id)

    # Métodos de pagamento
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


# =========================
# CALLBACK DE ADMIN (APROVAR / NEGAR)
# =========================
async def admin_decisao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dados = query.data.split("_")
    acao, pedido_id, user_id = dados[0], int(dados[1]), int(dados[2])

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if acao == "aprovar":
        cursor.execute("UPDATE pedidos SET status = ? WHERE id = ?", ("aprovado", pedido_id))
        await application.bot.send_message(chat_id=user_id, text="✅ O seu pagamento foi confirmado! O serviço já está ativo.")
        await query.edit_message_text("✔️ Pagamento aprovado e cliente notificado.")
    elif acao == "negar":
        cursor.execute("UPDATE pedidos SET status = ? WHERE id = ?", ("negado", pedido_id))
        await application.bot.send_message(chat_id=user_id, text="❌ O seu pagamento não foi aprovado. Verifique os dados e tente novamente.")
        await query.edit_message_text("🚫 Pagamento negado e cliente notificado.")

    conn.commit()
    conn.close()


# =========================
# IA - RESPOSTAS AUTOMÁTICAS
# =========================
async def responder_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pergunta = update.message.text

    try:
        resposta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Tu és um assistente simpático da Loja IPTV Futurista."},
                      {"role": "user", "content": pergunta}],
            max_tokens=200
        )
        texto = resposta.choices[0].message.content
    except Exception as e:
        texto = f"⚠️ Erro ao consultar IA: {e}"

    await update.message.reply_text(texto)

# =========================
# FASTAPI + WEBHOOK
# =========================
app = FastAPI()
application = Application.builder().token(TOKEN).updater(None).build()

# Registrar handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(callback=callback_router))
application.add_handler(CallbackQueryHandler(callback=admin_decisao, pattern="^(aprovar|negar)_"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_ia))


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

