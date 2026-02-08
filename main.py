import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логов
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Путь для сохранения данных (совместимо с Railway Volume)
DATA_DIR = "/app/data" if os.path.exists("/app/data") else "."
DATA_FILE = os.path.join(DATA_DIR, "inventory.json")

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Ошибка загрузки: {e}")
            return {}
    return {}

def save_data():
    if not os.path.exists(DATA_DIR) and DATA_DIR != ".":
        os.makedirs(DATA_DIR)
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(inventory, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Ошибка сохранения: {e}")

inventory = load_data()
current_article = {}

async def main_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("🔄 Обнулить склад", callback_data="restart_confirm")],
        [InlineKeyboardButton("📋 Получить сводку", callback_data="report")],
        [InlineKeyboardButton("▶️ Начать работу", callback_data="start_bot")]
    ]
    text = "📦 **Система учета склада**\nВведите номер артикула или выберите действие:"
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

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
        else:
            await update.message.reply_text("❌ Сначала введите номер артикула.")

async def show_colors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    art = current_article.get(user_id)
    if not art: return

    text_lines = [f"📦 **Артикул: {art}**", "---", "Введите название цвета или жмите кнопки:"]
    keyboard = []
    
    if art in inventory:
        for idx, (color, count) in enumerate(inventory[art].items()):
            text_lines.append(f"🔹 {color}: `{count}` пар")
            keyboard.append([
                InlineKeyboardButton(f"{color} +6", callback_data=f"a_{idx}"),
                InlineKeyboardButton(f"🗑 {color}", callback_data=f"delcolor_{idx}")
            ])
    
    keyboard.append([InlineKeyboardButton("❌ Удалить весь артикул", callback_data="delete_article")])
    keyboard.append([InlineKeyboardButton("⬅️ В меню", callback_data="back_menu")])
    
    msg_text = "\n".join(text_lines)
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global inventory
    query = update.callback_query
    user_id = update.effective_user.id
    art = current_article.get(user_id)
    await query.answer()
    
    data = query.data

    # 1. Добавление +6
    if data.startswith("a_") and art:
        idx = int(data.split("_")[1])
        colors = list(inventory[art].keys())
        if idx < len(colors):
            inventory[art][colors[idx]] += 6
            save_data()
            await show_colors(update, context)

    # 2. УДАЛЕНИЕ ЦВЕТА (Исправлено)
    elif data.startswith("delcolor_") and art:
        idx = int(data.split("_")[1])
        colors = list(inventory[art].keys())
        if idx < len(colors):
            color_to_del = colors[idx]
            del inventory[art][color_to_del]
            save_data()
            await show_colors(update, context)

    # 3. УДАЛЕНИЕ АРТИКУЛА (Исправлено)
    elif data == "delete_article" and art:
        if art in inventory:
            del inventory[art]
            save_data()
        current_article[user_id] = None
        await query.edit_message_text(f"✅ Артикул `{art}` полностью удален.", parse_mode="Markdown")
        await main_menu(update)

    # 4. Сводка
    elif data == "report":
        if not inventory:
            await query.message.reply_text("📭 Склад пуст.")
        else:
            report = ["📋 **ПОЛНАЯ СВОДКА**\n"]
            total = 0
            for art_name, colors in inventory.items():
                if colors:
                    report.append(f"🆔 *Артикул {art_name}*:")
                    for c, q in colors.items():
                        report.append(f"  - {c}: {q} пар")
                        total += q
                    report.append("")
            report.append(f"📈 **Итого: {total} пар**")
            await query.message.reply_text("\n".join(report), parse_mode="Markdown")
        await main_menu(update)

    # 5. Остальное
    elif data == "restart_confirm":
        keyboard = [[InlineKeyboardButton("✅ Да, обнулить", callback_data="restart_yes")],
                    [InlineKeyboardButton("❌ Отмена", callback_data="back_menu")]]
        await query.edit_message_text("⚠️ Обнулить ВЕСЬ склад?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "restart_yes":
        inventory = {}
        save_data()
        await query.edit_message_text("✅ Все данные удалены.")
        await main_menu(update)
    
    elif data in ["back_menu", "start_bot"]:
        await main_menu(update)

if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        exit(1)
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
    
