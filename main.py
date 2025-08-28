import os
from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# =========================
# CONFIGURAÇÕES
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # token do BotFather
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "segredo123")  # string forte
PUBLIC_URL = os.getenv("PUBLIC_URL")  # URL do Render (ex: https://forward-bot.onrender.com)

if not BOT_TOKEN:
    raise RuntimeError("⚠️ Defina a variável BOT_TOKEN no ambiente")

# Cria a aplicação do Telegram
telegram_app = Application.builder().token(BOT_TOKEN).build()

# =========================
# HANDLERS DO BOT
# =========================
async def start(update, context):
    await update.message.reply_text("🚀 Bot online via Webhook no Render!")

async def echo(update, context):
    await update.message.reply_text(f"Você disse: {update.message.text}")

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# =========================
# FASTAPI
# =========================
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()
    if PUBLIC_URL:
        # Registra webhook no Telegram
        await telegram_app.bot.set_webhook(
            url=f"{PUBLIC_URL}/webhook",
            secret_token=WEBHOOK_SECRET
        )
        print("✅ Webhook configurado:", f"{PUBLIC_URL}/webhook")

@app.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None)
):
    # Segurança: só aceita requisições com o secret correto
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Token inválido")

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)

    await telegram_app.process_update(update)
    return {"ok": True}
