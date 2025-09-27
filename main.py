
import os
import asyncio
from fastapi import FastAPI, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PAYPAL_USER = os.getenv("PAYPAL_USER")
TELEGRAM_USER = os.getenv("MEU_TELEGRAM")

if not all([BOT_TOKEN, ADMIN_ID, PAYPAL_USER, TELEGRAM_USER]):
    raise RuntimeError("⚠️ Configure BOT_TOKEN, ADMIN_ID, PAYPAL_USER e MEU_TELEGRAM")

pendentes = {}

# ===================== FUNÇÕES =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Plano Básico - 5€", callback_data="plano_basico")],
        [InlineKeyboardButton("Plano Premium - 10€", callback_data="plano_premium")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎰 Bem-vindo ao Bot Futurista! Escolha seu plano e siga o pagamento via PayPal.\n\n"
        f"Após pagar, envie o comprovativo clicando no meu usuário: @{TELEGRAM_USER}",
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
        f"✅ Você escolheu <b>{plano.replace('_', ' ').title()}</b>.\n"
        f"💳 Pague via PayPal para: <b>{PAYPAL_USER}</b>\n"
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
    args = context.args
    if not args:
        await update.message.reply_text("Use: /confirmar <user_id>")
        return
    uid = int(args[0])
    if uid in pendentes:
        plano = pendentes.pop(uid)
        await update.message.reply_text(f"✅ Pagamento de {plano} confirmado para {uid}.")
    else:
        await update.message.reply_text("Usuário não encontrado nos pendentes.")

async def negar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Use: /negar <user_id>")
        return
    uid = int(args[0])
    if uid in pendentes:
        plano = pendentes.pop(uid)
        await update.message.reply_text(f"❌ Pagamento de {plano} negado para {uid}.")
    else:
        await update.message.reply_text("Usuário não encontrado nos pendentes.")

# ===================== FASTAPI =====================
app = FastAPI()
application = None  # será inicializado depois

@app.on_event("startup")
async def startup():
    global application
    application = Application.builder().token(BOT_TOKEN).build()

    # Adiciona handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("pendentes", pendentes_cmd))
    application.add_handler(CommandHandler("confirmar", confirmar))
    application.add_handler(CommandHandler("negar", negar))

    # roda bot em background
    asyncio.create_task(application.initialize())
    asyncio.create_task(application.start())
    asyncio.create_task(application.updater.start_polling())  # necessário para queue

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}
