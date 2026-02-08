import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логов
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

DATA_DIR = "/app/data" if os.path.exists("/app/data") else "."
DATA_FILE = os.path.join(DATA_DIR, "inventory.json")

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {}
    return {}

def save_data():
    if not os.path.exists(DATA_DIR) and DATA_DIR != ".":
        os.makedirs(DATA_DIR)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=4)

inventory = load_data()
current_article = {}
last_msg_id = {} # Словарь для хранения ID последнего сообщения бота

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📋 Сводка", callback_data="report"),
         InlineKeyboardButton("📦 Дозаказ", callback_data="need_order")],
        [InlineKeyboardButton("🔄 Обнулить склад", callback_data="restart_confirm")],
        [InlineKeyboardButton("▶️ Начать работу", callback_data="start_bot")]
    ]
    text = "📦 **Система склада**\nВведите артикул или выберите действие:"
    markup = InlineKeyboardMarkup(keyboard)
    
    # Пытаемся редактировать старое, если нет - шлем новое
    try:
        if user_id in last_msg_id:
            await context.bot.edit_message_text(text, update.effective_chat.id, last_msg_id[user_id], reply_markup=markup, parse_mode="Markdown")
        else:
            sent = await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup, parse_mode="Markdown")
            last_msg_id[user_id] = sent.message_id
    except:
        sent = await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup, parse_mode="Markdown")
        last_msg_id[user_id] = sent.message_id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update, context)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # УДАЛЯЕМ сообщение пользователя, чтобы чат был чистым
    try:
        await update.message.delete()
    except:
        pass

    if any(char.isdigit() for char in text):
        current_article[user_id] = text
        if text not in inventory:
            inventory[text] = {}
        await show_colors(update, context)
    else:
        art = current_article.get(user_id)
        if art:
            if text not in inventory[art]:
                inventory[art][text] = 6
                save_data()
            await show_colors(update, context)

async def show_colors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    art = current_article.get(user_id)
    if not art: return

    text_lines = [f"📦 **Артикул: {art}**", "---"]
    keyboard = []
    for idx, (color, count) in enumerate(inventory.get(art, {}).items()):
        status = "⚠️" if count <= 6 else "🔹"
        text_lines.append(f"{status} {color}: `{count}` пар")
        keyboard.append([
            InlineKeyboardButton(f"{color} +6", callback_data=f"a_{idx}"),
            InlineKeyboardButton(f"🗑 {color}", callback_data=f"delcolor_{idx}")
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Удалить весь артикул", callback_data="delete_article")])
    keyboard.append([InlineKeyboardButton("⬅️ В меню", callback_data="back_menu")])
    
    msg_text = "\n".join(text_lines)
    markup = InlineKeyboardMarkup(keyboard)

    try:
        m_id = last_msg_id.get(user_id)
        await context.bot.edit_message_text(msg_text, update.effective_chat.id, m_id, reply_markup=markup, parse_mode="Markdown")
    except:
        sent = await context.bot.send_message(update.effective_chat.id, msg_text, reply_markup=markup, parse_mode="Markdown")
        last_msg_id[user_id] = sent.message_id

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global inventory
    query = update.callback_query
    user_id = update.effective_user.id
    art = current_article.get(user_id)
    await query.answer()
    
    data = query.data

    if data.startswith("a_") and art:
        idx = int(data.split("_")[1])
        colors = list(inventory[art].keys())
        if idx < len(colors):
            inventory[art][colors[idx]] += 6
            save_data()
            await show_colors(update, context)

    elif data == "need_order":
        order_list = ["🛒 **ДОЗАКАЗ (<= 6 пар)**\n"]
        found = False
        for a, colors in inventory.items():
            for c, q in colors.items():
                if q <= 6:
                    order_list.append(f"• `{a}` - {c}: **{q}**")
                    found = True
        await query.message.reply_text("\n".join(order_list) if found else "✅ Все в наличии!", parse_mode="Markdown")
        await main_menu(update, context)

    elif data == "report":
        report = ["📋 **СВОДКА**\n"]
        for a, colors in inventory.items():
            if colors:
                report.append(f"🆔 *{a}*:")
                for c, q in colors.items():
                    report.append(f"  - {c}: {q}")
        await query.message.reply_text("\n".join(report) if inventory else "📭 Пусто", parse_mode="Markdown")
        await main_menu(update, context)

    elif data == "delete_article" and art:
        if art in inventory: del inventory[art]
        save_data()
        await show_colors(update, context) # Обновит интерфейс

    elif data.startswith("delcolor_") and art:
        idx = int(data.split("_")[1])
        colors = list(inventory[art].keys())
        if idx < len(colors):
            del inventory[art][colors[idx]]
            save_data()
            await show_colors(update, context)

    elif data in ["back_menu", "start_bot"]:
        await main_menu(update, context)

    elif data == "restart_confirm":
        await query.edit_message_text("⚠️ Очистить всё?", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да", callback_data="restart_yes"), InlineKeyboardButton("❌ Нет", callback_data="back_menu")]
        ]))

    elif data == "restart_yes":
        inventory = {}
        save_data()
        await main_menu(update, context)

if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
                                                                                             
