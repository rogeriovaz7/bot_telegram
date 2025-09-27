import os
import logging
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import openai

# -------------------- Config -------------------- #
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MEU_TELEGRAM = os.environ.get("MEU_TELEGRAM")  # ex: @usuario
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{os.environ.get('RENDER_EXTERNAL_URL', '')}{WEBHOOK_PATH}"

openai.api_key = OPENAI_API_KEY

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

pendentes = {}  # user_id -> comprovativo

# -------------------- Handlers -------------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Plano 1", callback_data="plano1")],
                [InlineKeyboardButton("Plano 2", callback_data="plano2")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Escolha um plano e envie o comprovativo depois para {MEU_TELEGRAM}",
        reply_markup=reply_markup,
    )

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await query.message.reply_text(f"Olá {user.first_name}, envie o comprovativo para {MEU_TELEGRAM}")

async def receber_comprovativo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if update.message.photo:
        pendentes[user_id] = update.message.photo[-1].file_id
    elif update.message.document:
        pendentes[user_id] = update.message.document.file_id
    else:
        pendentes[user_id] = update.message.text
    await update.message.reply_text(f"Comprovativo recebido! O administrador ({MEU_TELEGRAM}) irá confirmar.")

# -------------------- Admin -------------------- #
async def cmd_pendentes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not pendentes:
        await update.message.reply_text("Não há comprovativos pendentes.")
        return
    msg = "Pendentes:\n" + "\n".join([str(uid) for uid in pendentes])
    await update.message.reply_text(msg)

async def cmd_confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    args = update.message.text.split()
    if len(args) < 2:
        await update.message.reply_text("Use /confirmar <user_id>")
        return
    user_id = int(args[1])
    if user_id in pendentes:
        del pendentes[user_id]
        await update.message.reply_text(f"Comprovativo de {user_id} confirmado!")
    else:
        await update.message.reply_text("User ID não encontrado.")

async def cmd_negar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    args = update.message.text.split()
    if len(args) < 2:
        await update.message.reply_text("Use /negar <user_id>")
        return
    user_id = int(args[1])
    if user_id in pendentes:
        del pendentes[user_id]
        await update.message.reply_text(f"Comprovativo de {user_id} negado!")
    else:
        await update.message.reply_text("User ID não encontrado.")

# -------------------- ChatGPT -------------------- #
async def responder_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"Erro ao contactar IA: {e}")

# -------------------- FastAPI + Webhook -------------------- #
app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Adicionar handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(callback_router))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_ia))
telegram_app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receber_comprovativo))
telegram_app.add_handler(CommandHandler("pendentes", cmd_pendentes))
telegram_app.add_handler(CommandHandler("confirmar", cmd_confirmar))
telegram_app.add_handler(CommandHandler("negar", cmd_negar))

@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_webhook(WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.stop()
    await telegram_app.shutdown()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.update_queue.put(update)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


