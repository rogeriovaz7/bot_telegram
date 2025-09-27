import os
import sqlite3
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# -----------------------------
# CONFIGURAÇÃO
# -----------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "SEU_BOT_TOKEN_AQUI")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))
MEU_TELEGRAM = os.environ.get("MEU_TELEGRAM", "@seu_usuario")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://SEU_DOMINIO.onrender.com/webhook")
DB_PATH = "comprovativos.db"

if not BOT_TOKEN or not ADMIN_ID or not MEU_TELEGRAM or not WEBHOOK_URL:
    raise RuntimeError("Configure BOT_TOKEN, ADMIN_ID, MEU_TELEGRAM e WEBHOOK_URL")

# -----------------------------
# FASTAPI
# -----------------------------
app = FastAPI()

# -----------------------------
# BOT TELEGRAM
# -----------------------------
bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

# -----------------------------
# BANCO DE DADOS
# -----------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comprovativos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            fullname TEXT,
            file_id TEXT,
            file_type TEXT,
            status TEXT DEFAULT 'pendente'
        )
    """)
    conn.commit()
    conn.close()

init_db()

# -----------------------------
# HANDLERS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Olá {update.effective_user.first_name}! 👋\n"
        f"Use /enviar_comprovativo para enviar seu comprovativo."
    )

async def enviar_comprovativo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Envie sua foto ou documento de comprovativo.\n"
        f"O admin {MEU_TELEGRAM} será notificado."
    )

async def receber_comprovativo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Detecta tipo
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = "photo"
    elif update.message.document:
        file_id = update.message.document.file_id
        file_type = "document"
    else:
        await update.message.reply_text("⚠️ Envie apenas foto ou documento!")
        return

    # Salva no DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO comprovativos (user_id, username, fullname, file_id, file_type)
        VALUES (?, ?, ?, ?, ?)
    """, (user.id, user.username, user.full_name, file_id, file_type))
    conn.commit()
    comprovativo_id = cursor.lastrowid
    conn.close()

    await update.message.reply_text("✅ Comprovativo enviado! Aguarde aprovação do admin.")

# -----------------------------
# LISTAR PENDENTES (ADMIN)
# -----------------------------
async def listar_pendentes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Apenas o admin pode usar este comando.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fullname, username, file_type, file_id FROM comprovativos WHERE status='pendente'")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("✅ Não há comprovativos pendentes.")
        return

    for row in rows:
        cid, fullname, username, ftype, fid = row
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Aprovar", callback_data=f"aprovar:{cid}"),
             InlineKeyboardButton("❌ Rejeitar", callback_data=f"rejeitar:{cid}")]
        ])
        text = f"📌 {fullname} (@{username})\nTipo: {ftype}"
        if ftype == "photo":
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=fid, caption=text, reply_markup=buttons)
        else:
            await context.bot.send_document(chat_id=ADMIN_ID, document=fid, caption=text, reply_markup=buttons)

# -----------------------------
# APROVAR/REJEITAR
# -----------------------------
async def aprovar_rejeitar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, comprovativo_id = data.split(":")
    comprovativo_id = int(comprovativo_id)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM comprovativos WHERE id=?", (comprovativo_id,))
    row = cursor.fetchone()
    if not row:
        await query.edit_message_caption(caption="❌ Comprovativo não encontrado.")
        conn.close()
        return

    user_id = row[0]
    status_text = "Aprovado ✅" if action == "aprovar" else "Rejeitado ❌"
    cursor.execute("UPDATE comprovativos SET status=? WHERE id=?", (status_text, comprovativo_id))
    conn.commit()
    conn.close()

    await query.edit_message_caption(caption=f"{status_text} por {update.effective_user.full_name}")
    await context.bot.send_message(chat_id=user_id, text=f"Seu comprovativo foi {status_text.lower()}!")

# -----------------------------
# HISTÓRICO (ADMIN)
# -----------------------------
async def historico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Apenas o admin pode usar este comando.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fullname, username, status FROM comprovativos ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("✅ Nenhum comprovativo encontrado.")
        return

    text = "📄 Últimos comprovativos:\n"
    for cid, fullname, username, status in rows:
        text += f"#{cid} {fullname} (@{username}) → {status}\n"
    await update.message.reply_text(text)

# -----------------------------
# ADICIONA HANDLERS
# -----------------------------
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("enviar_comprovativo", enviar_comprovativo))
bot_app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receber_comprovativo))
bot_app.add_handler(CommandHandler("pendentes", listar_pendentes))
bot_app.add_handler(CommandHandler("historico", historico))
bot_app.add_handler(CallbackQueryHandler(aprovar_rejeitar, pattern="^(aprovar|rejeitar):"))

# -----------------------------
# ENDPOINT DO WEBHOOK
# -----------------------------
@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.update_queue.put(update)
    return {"status": "ok"}

# -----------------------------
# STARTUP / SHUTDOWN
# -----------------------------
@app.on_event("startup")
async def startup_event():
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.bot.set_webhook(WEBHOOK_URL)

@app.on_event("shutdown")
async def shutdown_event():
    await bot_app.stop()
    await bot_app.shutdown()

