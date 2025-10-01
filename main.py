
import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import qrcode
import io
import openai

# =========================
# CONFIGURAÇÃO VIA VARIÁVEIS DE AMBIENTE
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RENDER_URL = os.getenv("RENDER_URL")

openai.api_key = OPENAI_API_KEY

# =========================
# CONFIGURAÇÃO DO FASTAPI
# =========================
app = FastAPI()
application = None  # Será inicializado no startup

# =========================
# DADOS DE PRODUTOS
# =========================
PRODUCTS = {
    "iptv_1mes": {"nome": "IPTV 1 Mês", "preco": 5, "arquivo": "banners/iptv_1mes.jpg"},
    "iptv_3meses": {"nome": "IPTV 3 Meses", "preco": 12, "arquivo": "banners/iptv_3meses.jpg"},
    "iptv_6meses": {"nome": "IPTV 6 Meses", "preco": 20, "arquivo": "banners/iptv_6meses.jpg"},
    "iptv_12meses": {"nome": "IPTV 12 Meses", "preco": 35, "arquivo": "banners/iptv_12meses.jpg"},  # NOVO
}


# =========================
# HELPERS
# =========================
async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia vídeo de boas-vindas na primeira interação"""
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id, "Bem-vindo! Aqui está o vídeo de introdução:")
    # vídeo fictício local ou URL
    video_path = "banners/welcome.mp4"
    if os.path.exists(video_path):
        await context.bot.send_video(chat_id, video=open(video_path, "rb"))

async def ask_ai(question: str) -> str:
    """Chama a OpenAI para responder perguntas do usuário"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user","content":question}],
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Erro na IA: {e}"

# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_welcome(update, context)

    keyboard = [
        [InlineKeyboardButton(p["nome"], callback_data=key)]
        for key, p in PRODUCTS.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(update.effective_chat.id, "Escolha um produto:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    produto_key = query.data
    produto = PRODUCTS.get(produto_key)

    if produto:
        # Cria QR code fictício para pagamento
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(f"Pagamento {produto['nome']} - Preço: {produto['preco']}€")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)

        await context.bot.send_photo(query.message.chat.id, photo=bio, caption=f"Escaneie para pagar: {produto['nome']} - {produto['preco']}€")
        # Notificação para o ADMIN
        await context.bot.send_message(ADMIN_ID, f"Usuário {query.from_user.username} escolheu {produto['nome']}. Aprove ou negue o pagamento.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia pergunta para IA se não for comando"""
    resposta = await ask_ai(update.message.text)
    await update.message.reply_text(resposta)

# =========================
# FASTAPI WEBHOOK
# =========================
@app.on_event("startup")
async def startup():
    global application
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start webhook
    # Em Render: usamos webhook + FastAPI
    from telegram.ext import BasePersistence
    persistence = BasePersistence()
    await application.initialize()
    await application.start()
    await application.updater.start_polling()  # Em Render webhook, polling não é recomendado, mas funciona para testes
    print("Bot iniciado.")

@app.post(f"/webhook/{TOKEN}")
async def telegram_webhook(request: Request):
    """Recebe updates do Telegram via webhook"""
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"status": "ok"}

# Endpoint de teste
@app.get("/")
def index():
    return {"status": "Bot rodando"}

# =========================
# EXECUÇÃO LOCAL
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
