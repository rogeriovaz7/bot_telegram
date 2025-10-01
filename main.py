import json
import sqlite3
import os
import qrcode
import asyncio
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


async def avisar_admin(produto, preco, user_name, user_id):
    msg = (
        f"📦 Novo pedido recebido!\n"
        f"👤 Usuário: {user_name} ({user_id})\n"
        f"📺 Produto: {produto}\n"
        f"💰 Preço: {preco}€\n"
        f"⏳ Aguardando confirmação de pagamento.\n\n"
        f"Para aprovar ou negar, responda com /aprovar {user_id} ou /negar {user_id}"
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
        [InlineKeyboardButton(f"📺 {p['nome']} - {p['preco']}€", callback_data=f"produto_{key}")]
        for key, p in produtos.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(
        "🌌 *✨ Planos IPTV Futuristas Disponíveis ✨*\n\nEscolha seu plano abaixo:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def mostrar_produto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    produto_id = query.data.split("_")[1]
    produto = produtos[produto_id]

    imagem_map = {
        "1mes": "iptv_1mes.jpg",
        "3meses": "iptv_3meses.jpg",
        "6meses": "iptv_6meses.jpg",
    }
    image_file = imagem_map.get(produto_id, "default.jpg")
    image_path = os.path.join("banners", image_file)

    caption = (
        f"🌠 *{produto['nome']}*\n"
        f"💰 *Preço:* {produto['preco']}€\n\n"
        f"ℹ️ {produto['descricao']}\n\n"
        f"Escolha uma opção abaixo para continuar:"
    )
    keyboard = [
        [InlineKeyboardButton("🛒 Comprar Agora", callback_data=f"comprar_{produto_id}")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu", callback_data="menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_photo(open(image_path, "rb"), caption=caption, parse_mode="Markdown", reply_markup=reply_markup)


async def comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    produto_id = query.data.split("_")[1]
    produto = produtos[produto_id]
    user_id = query.from_user.id
    user_name = query.from_user.full_name

    registrar_pedido(user_id, produto["nome"], produto["preco"], produto["link"])
    await avisar_admin(produto["nome"], produto["preco"], user_name, user_id)

    qr_file = gerar_qrcode_mbway(user_id, produto_id, produto["preco"])
    paypal_link = criar_link_paypal(produto["preco"])
    skrill_instrucao = criar_instrucao_skrill(produto["preco"], produto["nome"])

    mensagem = (
        f"✅ Você escolheu: *{produto['nome']}* - {produto['preco']}€\n\n"
        f"💳 *Métodos de Pagamento*:\n"
        f"👉 PayPal: {paypal_link}\n"
        f"👉 MB WAY: *{MBWAY_NUMERO}* (QR code abaixo)\n"
        f"👉 Skrill: veja instruções 👇\n\n"
        f"{skrill_instrucao}\n\n"
        "⏳ Após o pagamento, aguarde aprovação do administrador."
    )
    await query.message.reply_photo(open(qr_file, "rb"), caption=mensagem, parse_mode="Markdown")


# =========================
# IA INTEGRADA
# =========================
async def responder_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text

    prompt = f"""
Você é um assistente de vendas futurista para IPTV. 
O usuário perguntou: "{user_msg}"
Sugira o melhor produto IPTV disponível na loja, com base na pergunta.
Se for uma pergunta geral, responda normalmente.
Os produtos disponíveis são:
{json.dumps(produtos, ensure_ascii=False)}
Responda em português.
"""
    resposta = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8
    )
    reply_text = resposta.choices[0].message.content
    await update.message.reply_text(reply_text)


# =========================
# ROUTER E COMANDOS ADMIN
# =========================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "menu":
        await mostrar_menu(update, context)
    elif query.data.startswith("produto_"):
        await mostrar_produto(update, context)
    elif query.data.startswith("comprar_"):
        await comprar(update, context)


async def aprovar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    user_id = int(context.args[0])
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE pedidos SET status = 'aprovado' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Pedido do usuário {user_id} aprovado.")


async def negar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    user_id = int(context.args[0])
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE pedidos SET status = 'negado' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"❌ Pedido do usuário {user_id} negado.")


# =========================
# FASTAPI + WEBHOOK
# =========================
app = FastAPI()
application = Application.builder().token(TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("aprovar", aprovar))
application.add_handler(CommandHandler("negar", negar))
application.add_handler(CallbackQueryHandler(callback_router))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_ia))


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"status": "ok"}


@app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.start()
    webhook_url = f"https://{RENDER_URL}/webhook"
    await application.bot.set_webhook(webhook_url)
    print(f"🌐 Webhook configurado: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()


@app.get("/")
def home():
    return {"status": "🤖 Bot IPTV Futurista ativo!"}

