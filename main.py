# main.py
import os
import asyncio
import sqlite3
from fastapi import FastAPI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import openai

# ================================
# Configurações
# ================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAYPAL_LINK = os.getenv("PAYPAL_LINK")  # Link para pagamento
PORT = int(os.getenv("PORT", 10000))

openai.api_key = OPENAI_API_KEY

# ================================
# Banco de dados SQLite
# ================================
DB_FILE = "comprovativos.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT,
        link TEXT NOT NULL,
        status TEXT DEFAULT 'pendente'
    )
    """)
    conn.commit()
    conn.close()

def add_comprovativo(user_id, username, link):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO pagamentos (user_id, username, link)
    VALUES (?, ?, ?)
    """, (user_id, username, link))
    conn.commit()
    conn.close()

def check_comprovativo(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pagamentos WHERE user_id=? AND status='pendente'", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

# ================================
# FastAPI
# ================================
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "Bot com IA e pagamentos está online!"}

# ================================
# Telegram Handlers
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Olá! Eu sou um bot com IA.\n"
        "Envie-me uma mensagem para responder.\n\n"
        f"Para carregar saldo via PayPal, use: {PAYPAL_LINK}\n"
        "Depois de enviar o comprovativo, envie-me o link para validar o pagamento."
    )
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Comandos:\n"
        "/start - iniciar bot\n"
        "/help - ajuda\n\n"
        "Envie qualquer mensagem e eu responderei com IA.\n"
        f"Para pagamento PayPal: {PAYPAL_LINK}"
    )
    await update.message.reply_text(text)

async def chatgpt_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_message}],
            temperature=0.7,
            max_tokens=500
        )
        answer = response['choices'][0]['message']['content'].strip()
    except Exception as e:
        answer = "Erro ao processar a mensagem. Tente novamente."
        print("OpenAI Error:", e)
    
    await update.message.reply_text(answer)

async def comprovativo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""
    user_message = update.message.text

    if "http" in user_message:  # Se for um link
        existing = check_comprovativo(user_id)
        if existing:
            await update.message.reply_text(
                "Você já enviou um comprovativo pendente. Aguarde validação."
            )
        else:
            add_comprovativo(user_id, username, user_message)
            await update.message.reply_text(
                "Recebi seu comprovativo! Vamos validar e creditar o saldo em breve."
            )
    else:
        await chatgpt_response(update, context)

# ================================
# Criação do Bot Telegram
# ================================
async def start_bot():
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, comprovativo_handler))

    # Inicia polling
    await application.run_polling()

# ================================
# FastAPI startup
# ================================
@app.on_event("startup")
async def startup_event():
    init_db()
    asyncio.create_task(start_bot())

