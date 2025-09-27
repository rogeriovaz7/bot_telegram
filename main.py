

import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

# -------------------- CONFIGURAÇÃO --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MEU_TELEGRAM = os.getenv("MEU_TELEGRAM")  # Seu usuário clicável, ex: @meuusuario

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Armazena comprovativos pendentes {user_id: plano}
pendentes = {}

# -------------------- FUNÇÕES --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu futurista estilo cassino com animação via emojis"""
    keyboard = [
        [
            InlineKeyboardButton("💎 Básico - $5", callback_data="plano_5"),
            InlineKeyboardButton("💰 Premium - $10", callback_data="plano_10")
        ],
        [
            InlineKeyboardButton("🚀 VIP - $20", callback_data="plano_20")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = (
        f"🎰 *Cassino Futurista - Menu de Planos*\n\n"
        f"Escolha seu plano e envie o comprovativo para {MEU_TELEGRAM}.\n\n"
        f"💳 Pagamentos via PayPal\n"
        f"⚡ Experiência futurista com botões animados!"
    )
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe escolha do plano e adiciona pendente"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    plano = query.data
    pendentes[user.id] = plano

    msg = (
        f"✨ *Você escolheu:* {plano}\n\n"
        f"📤 Envie seu comprovativo para {MEU_TELEGRAM}\n"
        f"⏳ Aguarde confirmação do pagamento."
    )
    await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def pendentes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos comprovativos pendentes (somente admin)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Acesso negado")
        return

    if not pendentes:
        await update.message.reply_text("📭 Nenhum comprovativo pendente.")
        return

    msg = "📋 *Comprovativos pendentes:*\n"
    for user_id, plano in pendentes.items():
        msg += f"⚡ `{user_id}` : {plano}\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma pagamento (somente admin)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Acesso negado")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Use: /confirmar <user_id>")
        return

    user_id = int(context.args[0])
    if user_id in pendentes:
        plano = pendentes.pop(user_id)
        await update.message.reply_text(
            f"✅ Pagamento CONFIRMADO para `{user_id}` ({plano}) 🎉",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("❌ Usuário não encontrado nos pendentes")

async def negar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nega pagamento (somente admin)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Acesso negado")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Use: /negar <user_id>")
        return

    user_id = int(context.args[0])
    if user_id in pendentes:
        plano = pendentes.pop(user_id)
        await update.message.reply_text(
            f"❌ Pagamento NEGADO para `{user_id}` ({plano}) ⚠️",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("❌ Usuário não encontrado nos pendentes")

# -------------------- MAIN --------------------
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Comandos principais
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("pendentes", pendentes_command))
    application.add_handler(CommandHandler("confirmar", confirmar))
    application.add_handler(CommandHandler("negar", negar))

    # Inicia polling
    application.run_polling()

if __name__ == "__main__":
    main()
