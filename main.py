import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application, CommandHandler
import asyncio
from dotenv import load_dotenv

# =========================
# Carregar variáveis do .env
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

if not BOT_TOKEN:
    raise RuntimeError("⚠️ Defina a variável BOT_TOKEN no ambiente ou no arquivo .env")

# =========================
# Inicializar o bot
# =========================
app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()

# Comando /start
async def start(update: Update, context):
    await update.message.reply_text("🚀 Bot online via Webhook!")

application.add_handler(CommandHandler("start", start))

# =========================
# Webhook endpoint
# =========================
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
    return {"ok": True}

# =========================
# Startup: configurar webhook
# =========================
@app.on_event("startup")
async def on_startup():
    webhook_url = f"{PUBLIC_URL}/webhook"
    await application.bot.set_webhook(url=webhook_url, secret_token=WEBHOOK_SECRET)
    asyncio.create_task(application.initialize())
    asyncio.create_task(application.start())
    print(f"✅ Webhook configurado em {webhook_url}")

# =========================
# Shutdown: parar bot
# =========================
@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()
