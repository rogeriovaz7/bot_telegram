# main.py
import os
import asyncio
from fastapi import FastAPI, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===================== CONFIGURAÇÃO =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PAYPAL_USER = os.getenv("PAYPAL_USER")
TELEGRAM_USER = os.getenv("MEU_TELEGRAM")

if not all([BOT_TOKEN, ADMIN_ID, PAYPAL_USER, TELEGRAM_USER]):
    raise RuntimeError("⚠️ Configure BOT_TOKEN, ADMIN_ID, PAYPAL_USER e MEU_TELEGRAM")

# ===================== DADOS =====================
pendentes = {}  # user_id : plano

# ===================== BOT HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Menu futurista com emojis e cores via HTML
    keyboard = [
        [InlineKeyboardButton("💠 Plano Básico - 5€", callback_data="plano_basico")],
        [InlineKeyboardButton("💎 Plano Premium - 10€", callback_data="plano_premium")],
        [InlineKeyboardButton("⚡ Suporte / Contato", url=f"https://t.me/{TELEGRAM_USER}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = (
        "<b>🎰 Bem-vindo ao Bot Futurista!</b>\n"
        "Escolha seu plano e siga o pagamento via PayPal.\n\n"
        f"💳 Pague via PayPal: <b>{PAYPAL_USER}</b>\n"
        f"📤 Depois, envie o comprovativo clicando no meu usuário: @{TELEGRAM_USER}\n\n"
        "🛸 Menu futurista ativado!"
    )

    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    plano = query.data
    pendentes[user_id] = plano

    message = (
        f"✅ Você escolheu <b>{plano.replace('_',' ').title()}</b>.\n"
        f"💳 Pague via PayPal: <b>{PAYPAL_USER}</b>\n"
        f"📤 Depois, envie o comprovativo clicando no meu usuário: @{TELEGRAM_USER}\n\n"
        "🚀 Pagamento futurista iniciado!"
    )

    await query.message.reply_text(message, parse_mode=ParseMode.HTML)

async def pendentes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not pendentes:
        await update.message.reply_text("💤 Nenhum pagamento pendente.")
        return
    text = "💼 <b>Pagamentos Pendentes:</b>\n"
    for uid, plano in pendentes.items():
        text += f"🧾 {uid}: {plano.replace('_',' ').title()}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

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
        await update.message.reply_text(f"✅ Pagamento de {plano.replace('_',' ').title()} confirmado para {uid}.")
    else:
        await update.message.reply_text("❌ Usuário não encontrado nos pendentes.")

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
        await update.message.reply_text(f"❌ Pagamento de {plano.replace('_',' ').title()} negado para {uid}.")
    else:
        await update.message.reply_text("❌ Usuário não encontrado nos pendentes.")

# ===================== FASTAPI =====================
app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()

# Handlers do bot
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button))
application.add_handler(CommandHandler("pendentes", pendentes_cmd))
application.add_handler(CommandHandler("confirmar", confirmar))
application.add_handler(CommandHandler("negar", negar))

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

# ===================== EXECUÇÃO =====================
async def start_bot():
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await application.updater.idle()

if __name__ == "__main__":
    asyncio.run(start_bot())

