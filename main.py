# main.py
import os
from fastapi import FastAPI, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= CONFIGURAÇÃO =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PAYPAL_USER = os.getenv("PAYPAL_USER")
TELEGRAM_USER = os.getenv("MEU_TELEGRAM")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # ex: https://seu-dominio.com

if not all([BOT_TOKEN, ADMIN_ID, PAYPAL_USER, TELEGRAM_USER, WEBHOOK_URL]):
    raise RuntimeError("Configure BOT_TOKEN, ADMIN_ID, PAYPAL_USER, MEU_TELEGRAM e WEBHOOK_URL")

# ================= DADOS =================
pendentes = {}  # user_id : plano

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Plano Básico - 5€", callback_data="plano_basico")],
        [InlineKeyboardButton("Plano Premium - 10€", callback_data="plano_premium")],
        [InlineKeyboardButton("Contato", url=f"https://t.me/{TELEGRAM_USER}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🎰 Bem-vindo ao Bot Futurista!\n\n"
        f"💳 Pague via PayPal: <b>{PAYPAL_USER}</b>\n"
        f"📤 Depois, envie o comprovativo clicando no meu usuário: @{TELEGRAM_USER}",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    plano = query.data
    pendentes[user_id] = plano
    await query.message.reply_text(
        f"✅ Você escolheu <b>{plano.replace('_',' ').title()}</b>.\n"
        f"💳 Pague via PayPal: <b>{PAYPAL_USER}</b>\n"
        f"📤 Depois, envie o comprovativo clicando no meu usuário: @{TELEGRAM_USER}",
        parse_mode=ParseMode.HTML
    )

async def pendentes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not pendentes:
        await update.message.reply_text("Nenhum pagamento pendente.")
        return
    text = "💼 Pagamentos Pendentes:\n"
    for uid, plano in pendentes.items():
        text += f"- {uid}: {plano}\n"
    await update.message.reply_text(text)

async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Use: /confirmar <user_id>")
        return
    uid = int(context.args[0])
    if uid in pendentes:
        plano = pendentes.pop(uid)
        await update.message.reply_text(f"✅ Pagamento de {plano} confirmado para {uid}.")
    else:
        await update.message.reply_text("Usuário não encontrado nos pendentes.")

async def negar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Use: /negar <user_id>")
        return
    uid = int(context.args[0])
    if uid in pendentes:
        plano = pendentes.pop(uid)
        await update.message.reply_text(f"❌ Pagamento de {plano} negado para {uid}.")
    else:
        await update.message.reply_text("Usuário não encontrado nos pendentes.")

# ================= FASTAPI =================
app = FastAPI()
bot_app = Application.builder().token(BOT_TOKEN).build()

# Registra handlers
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(button))
bot_app.add_handler(CommandHandler("pendentes", pendentes_cmd))
bot_app.add_handler(CommandHandler("confirmar", confirmar))
bot_app.add_handler(CommandHandler("negar", negar))

@app.post(f"/{BOT_TOKEN}")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.update_queue.put(update)
    return {"ok": True}

@app.on_event("startup")
async def startup():
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")

@app.on_event("shutdown")
async def shutdown():
    await bot_app.stop()
