import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

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
last_msg_id = {}
edit_mode = {} # Для отслеживания, какой цвет сейчас редактируем вручную

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
    
    try:
        m_id = last_msg_id.get(user_id)
        if m_id:
            await context.bot.edit_message_text(text, update.effective_chat.id, m_id, reply_markup=markup, parse_mode="Markdown")
        else:
            sent = await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup, parse_mode="Markdown")
            last_msg_id[user_id] = sent.message_id
    except:
        sent = await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup, parse_mode="Markdown")
        last_msg_id[user_id] = sent.message_id

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    try: await update.message.delete()
    except: pass

    # 1. Если ввели число (ручной ввод количества)
    if text.isdigit() and user_id in edit_mode:
        art, color = edit_mode[user_id]
        if art in inventory and color in inventory[art]:
            inventory[art][color] = int(text)
            save_data()
            del edit_mode[user_id] # Выходим из режима редактирования
            await show_colors(update, context)
            return

    # 2. Если ввели артикул (содержит цифры, но не только они, или просто новый артикул)
    if any(char.isdigit() for char in text) and len(text) > 3: # Пример: 715-44
        current_article[user_id] = text
        if text not in inventory:
            inventory[text] = {}
        await show_colors(update, context)
    
    # 3. Если ввели текст (название цвета)
    else:
        art = current_article.get(user_id)
        if art:
            if text not in inventory[art]:
                inventory[art][text] = 0 # Создаем с нулем
                save_data()
            await show_colors(update, context)

async def show_colors(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_text=None):
    user_id = update.effective_user.id
    art = current_article.get(user_id)
    if not art: return

    text_lines = [f"📦 **Артикул: {art}**", "---"]
    if custom_text: text_lines.append(f"💡 {custom_text}\n---")

    keyboard = []
    for idx, (color, count) in enumerate(inventory.get(art, {}).items()):
        status = "⚠️" if count <= 6 else "🔹"
        text_lines.append(f"{status} {color}: `{count}` пар")
        keyboard.append([
            InlineKeyboardButton(f"{color} +6", callback_data=f"a_{idx}"),
            InlineKeyboardButton(f"✏️", callback_data=f"edit_{idx}"),
            InlineKeyboardButton(f"🗑", callback_data=f"delcolor_{idx}")
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Удалить артикул", callback_data="delete_article")])
    keyboard.append([InlineKeyboardButton("⬅️ Меню", callback_data="back_menu")])
    
    msg_text = "\n".join(text_lines)
    markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.edit_message_text(msg_text, update.effective_chat.id, last_msg_id[user_id], reply_markup=markup, parse_mode="Markdown")
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
        inventory[art][colors[idx]] += 6
        save_data()
        await show_colors(update, context)

    elif data.startswith("edit_") and art:
        idx = int(data.split("_")[1])
        color = list(inventory[art].keys())[idx]
        edit_mode[user_id] = (art, color)
        await show_colors(update, context, custom_text=f"Введите число для цвета: {color}")

    elif data == "need_order":
        order = [f"• `{a}`-{c}: **{q}**" for a, colors in inventory.items() for c, q in colors.items() if q <= 6]
        await query.message.reply_text("🛒 **ДОЗАКАЗ:**\n" + "\n".join(order) if order else "✅ Ок")
        await main_menu(update, context)

    elif data == "report":
        rep = [f"🆔 *{a}*:\n" + "\n".join([f"  - {c}: {q}" for c, q in colors.items()]) for a, colors in inventory.items() if colors]
        await query.message.reply_text("📋 **СВОДКА:**\n\n" + "\n".join(rep) if rep else "Пусто")
        await main_menu(update, context)

    elif data == "delete_article" and art:
        if art in inventory: del inventory[art]
        save_data()
        await main_menu(update, context)

    elif data.startswith("delcolor_") and art:
        idx = int(data.split("_")[1])
        del inventory[art][list(inventory[art].keys())[idx]]
        save_data()
        await show_colors(update, context)

    elif data in ["back_menu", "start_bot"]:
        await main_menu(update, context)

if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
    
