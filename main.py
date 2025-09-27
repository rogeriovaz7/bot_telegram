
# main.py
import os
import sqlite3
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters
)
import openai

# ---------------------------
# CONFIGURAÇÃO
# ---------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
MEU_TELEGRAM = os.environ.get("MEU_TELEGRAM")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PAYPAL_LINK = os.environ.get("PAYPAL_LINK", "https://paypal.me/seu_usuario/valor")

if not all([BOT_TOKEN, ADMIN_ID, MEU_TELEGRAM, WEBHOOK_URL, OPENAI_API_KEY]):
    raise RuntimeError("Configure BOT_TOKEN, ADMIN_ID, MEU_TELEGRAM, WEBHOOK_URL e OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

# ---------------------------
# Inicializa FastAPI
# ---------------------------
app = FastAPI()

# ---------------------------
# Banco de dados SQLite
# ---------------------------
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    last_command TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    status TEXT,
    link TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS ia_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message TEXT,
    response TEXT
)
""")
conn.commit()

# ---------------------------
# Funções auxiliares
# ---------------------------
async def log_to_admin(message: str):
    """Envia logs para o ADMIN"""
    try:
        await bot_app.bot.send_message(chat_id=int(ADMIN_ID), text=message)
    except Exception as e:
        print("Falha ao enviar log:", e)

def save_user(user_id, username):
    cursor.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()

# ---------------------------
# Handlers do Bot
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    save_user(user_id, username)
    await update.message.reply_text(
        "Olá! Bot ativo ✅\nUse /help para ver os comandos disponíveis."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandos disponíveis:\n"
        "/start - iniciar bot\n"
        "/help - ajuda\n"
        "/comprovativo - enviar comprovativo\n"
        "/pagamento - gerar link PayPal\n"
        "/ia <mensagem> - conversar com IA\n"
        "/history - ver histórico de IA"
    )

async def enviar_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Envie o comprovativo para: {MEU_TELEGRAM}"
    )

async def pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("INSERT INTO payments(user_id, status, link) VALUES (?, ?, ?)",
                   (user_id, "pending", PAYPAL_LINK))
    conn.commit()
    await update.message.reply_text(f"Faça o pagamento usando este link: {PAYPAL_LINK}")
    await log_to_admin(f"Novo pagamento pendente do usuário {user_id} ({update.effective_user.username})")

async def chat_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_msg = " ".join(context.args)
    if not user_msg:
        await update.message.reply_text("Escreva algo após /ia para conversar com a IA.")
        return
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=300
        )
        reply_text = response['choices'][0]['message']['content']
        await update.message.reply_text(reply_text)

        # Salva histórico no SQLite
        cursor.execute("INSERT INTO ia_history(user_id, message, response) VALUES (?, ?, ?)",
                       (user_id, user_msg, reply_text))
        conn.commit()
    except Exception as e:
        await update.message.reply_text(f"Erro na IA: {e}")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT message, response FROM ia_history WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("Nenhum histórico encontrado.")
        return
    history_text = "\n\n".join([f"Q: {msg}\nA: {resp}" for msg, resp in rows])
    await update.message.reply_text(f"Últimas 10 interações:\n\n{history_text}")

# ---------------------------
# Cria aplicação do Telegram
# ---------------------------
bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", help_command))
bot_app.add_handler(CommandHandler("comprovativo", enviar_telegram))
bot_app.add_handler(CommandHandler("pagamento", pagamento))
bot_app.add_handler(CommandHandler("ia", chat_ia))
bot_app.add_handler(CommandHandler("history", history))

# ---------------------------
# FastAPI endpoint para webhook
# ---------------------------
@app.post(f"/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.update_queue.put(update)
    return {"ok": True}

# ---------------------------
# Configura webhook
# ---------------------------
async def set_webhook():
    await bot_app.bot.set_webhook(WEBHOOK_URL)
    print("Webhook configurado:", WEBHOOK_URL)
    await log_to_admin(f"Webhook configurado: {WEBHOOK_URL}")

# ---------------------------
# Startup e shutdown
# ---------------------------
@app.on_event("startup")
async def startup_event():
    await set_webhook()
    asyncio.create_task(bot_app.run_polling())
    await log_to_admin("Bot iniciado com sucesso ✅")

@app.on_event("shutdown")
async def shutdown_event():
    await bot_app.bot.delete_webhook()
    await log_to_admin("Bot desligado ⚠️")
