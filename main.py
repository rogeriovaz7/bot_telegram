



import json
import sqlite3
import os
import qrcode
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler,
)
from telegram.constants import ParseMode

# =========================
# CONFIGURAÇÃO VIA VARIÁVEIS DE AMBIENTE
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PAYPAL_USER = os.getenv("PAYPAL_USER")
MBWAY_NUMERO = os.getenv("MBWAY_NUMERO")
SKRILL_EMAIL = os.getenv("SKRILL_EMAIL")
RENDER_URL = os.getenv("RENDER_URL")

if not TOKEN or not ADMIN_ID or not RENDER_URL:
    raise RuntimeError(
        "⚠️ Configure todas as variáveis de ambiente: BOT_TOKEN, ADMIN_ID, RENDER_URL"
    )

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
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pedidos (user_id, produto, preco, status, link) VALUES (?, ?, ?, ?, ?)",
            (user_id, produto, preco, "pendente", link),
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Erro no BD ao registrar pedido: {e}")
        raise
    finally:
        if 'conn' in locals():
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


async def avisar_admin(application, produto, preco, user_name, user_id):
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
    conn.close()

    is_first_time = not visto
    if is_first_time:
        # Registra que já viu
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO usuarios (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()

        # Enviar intro só na primeira vez
        intro_path = os.path.join("banners", "intro.mp4")
        if os.path.exists(intro_path):
            try:
                with open(intro_path, "rb") as video_file:
                    await update.message.reply_video(video_file, caption="🚀 Bem-vindo à Loja IPTV Futurista!")
            except Exception as e:
                print(f"Erro ao enviar vídeo de intro: {e}")
                await update.message.reply_text("🚀 Bem-vindo à Loja IPTV Futurista! (Vídeo indisponível)")

    welcome_text = "👋 Bem-vindo de volta à *Loja IPTV Futurista*!" if not is_first_time else "👋 Bem-vindo à *Loja IPTV Futurista*!"
    keyboard = [[InlineKeyboardButton("🚀 Iniciar", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"{welcome_text}\n\nClique em *Iniciar* para ver os planos disponíveis.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Acesso negado.")
        return

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pedidos WHERE status='pendente'")
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM pedidos")
        total = cursor.fetchone()[0]
        conn.close()
        await update.message.reply_text(f"📊 Pedidos pendentes: {pending} / Total: {total}")
    except sqlite3.Error as e:
        await update.message.reply_text(f"❌ Erro ao consultar BD: {e}")


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
    if item_id not in produtos:
        await query.message.reply_text("❌ Produto não encontrado.")
        return
    produto = produtos[item_id]
    caption = f"📺 *{produto['nome']}*\n💰 {produto['preco']}€\n\nℹ️ {produto['descricao']}"
    keyboard = [
        [InlineKeyboardButton("🛒 Comprar Agora", callback_data=f"comprar_{item_id}")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu", callback_data="menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    imagem_path = produto.get("imagem")
    if imagem_path and os.path.exists(imagem_path):
        try:
            with open(imagem_path, "rb") as photo_file:
                await query.message.reply_photo(photo_file, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
            return
        except Exception as e:
            print(f"Erro ao enviar imagem do produto {produto['nome']}: {e}")
    await query.message.reply_text(caption + "\n\n(Imagem indisponível)", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_id = query.data.replace("comprar_", "")
    if item_id not in produtos:
        await query.message.reply_text("❌ Produto não encontrado.")
        return
    produto = produtos[item_id]
    user_id = query.from_user.id
    user_name = query.from_user.full_name or "Usuário Anônimo"  # Sanitize se necessário
    try:
        registrar_pedido(user_id, produto["nome"], produto["preco"], produto["link"])
        await avisar_admin(context.application, produto["nome"], produto["preco"], user_name, user_id)
    except Exception as e:
        await query.message.reply_text("❌ Erro ao registrar pedido. Tente novamente.")
        print(f"Erro ao registrar pedido: {e}")
        return

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
    if os.path.exists(qr_file):
        try:
            with open(qr_file, "rb") as qr_photo:
                await query.message.reply_photo(qr_photo, caption=mensagem, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            print(f"Erro ao enviar QR code: {e}")
            await query.message.reply_text(mensagem, parse_mode=ParseMode.MARKDOWN)
    else:
        await query.message.reply_text(mensagem, parse_mode=ParseMode.MARKDOWN)


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
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await application.initialize()
    await application.start()
    asyncio.create_task(start_webhook())
    yield
    # Shutdown
    await application.stop()

app = FastAPI(lifespan=lifespan)
application = Application.builder().token(TOKEN).updater(None).build()

# Registrar handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("status", status))
application.add_handler(CallbackQueryHandler(callback_router))


async def start_webhook():
    webhook_url = f"https://{RENDER_URL}/webhook"
    await application.bot.set_webhook(webhook_url)
    print(f"🌐 Webhook configurado: {webhook_url}")


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    if update:
        await application.update_queue.put(update)
    return {"status": "ok"}


@app.get("/")
def home():
    return {"status": "🤖 Bot IPTV Futurista ativo!"}
