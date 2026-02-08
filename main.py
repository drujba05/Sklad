import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логов
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Настройка пути к данным
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

async def main_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("📋 Сводка", callback_data="report"),
         InlineKeyboardButton("📦 Дозаказ", callback_data="need_order")],
        [InlineKeyboardButton("🔄 Обнулить склад", callback_data="restart_confirm")],
        [InlineKeyboardButton("▶️ Начать работу", callback_data="start_bot")]
    ]
    text = "📦 **Учет склада**\nВведите артикул или выберите действие:"
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
    if not art or art not in inventory: return

    text_lines = [f"📦 **Артикул: {art}**", "---"]
    keyboard = []
    
    for idx, (color, count) in enumerate(inventory[art].items()):
        status = "⚠️" if count <= 6 else "🔹"
        text_lines.append(f"{status} {color}: `{count}` пар")
        keyboard.append([
            InlineKeyboardButton(f"{color} +6", callback_data=f"a_{idx}"),
            InlineKeyboardButton(f"🗑 {color}", callback_data=f"delcolor_{idx}")
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Удалить весь артикул", callback_data="delete_article")])
    keyboard.append([InlineKeyboardButton("⬅️ В меню", callback_data="back_menu")])
    
    await update.callback_query.message.reply_text("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown") if update.callback_query else await update.message.reply_text("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

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
            # Для обновления просто вызываем сообщение заново
            await show_colors(update, context)

    elif data == "need_order":
        order_list = ["🛒 **СПИСОК НА ДОЗАКАЗ (6 пар и меньше)**\n"]
        found = False
        for a, colors in inventory.items():
            for c, q in colors.items():
                if q <= 6:
                    order_list.append(f"• `{a}` - {c}: **{q}** пар")
                    found = True
        if not found:
            await query.message.reply_text("✅ Всех позиций достаточно!")
        else:
            await query.message.reply_text("\n".join(order_list), parse_mode="Markdown")
        await main_menu(update)

    elif data == "report":
        if not inventory:
            await query.edit_message_text("📭 Склад пуст.")
        else:
            report = ["📋 **СВОДКА СКЛАДА**\n"]
            for a, colors in inventory.items():
                if colors:
                    report.append(f"🆔 *{a}*:")
                    for c, q in colors.items():
                        mark = "⚠️" if q <= 6 else ""
                        report.append(f"  - {c}: {q} {mark}")
            await query.message.reply_text("\n".join(report), parse_mode="Markdown")
        await main_menu(update)

    elif data == "delete_article" and art:
        if art in inventory: del inventory[art]
        save_data()
        await query.message.reply_text(f"✅ Артикул {art} удален.")
        await main_menu(update)

    elif data.startswith("delcolor_") and art:
        idx = int(data.split("_")[1])
        colors = list(inventory[art].keys())
        if idx < len(colors):
            del inventory[art][colors[idx]]
            save_data()
            await show_colors(update, context)

    elif data == "restart_confirm":
        await query.edit_message_text("⚠️ Удалить всё?", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да", callback_data="restart_yes"), InlineKeyboardButton("❌ Нет", callback_data="back_menu")]
        ]))

    elif data == "restart_yes":
        inventory = {}
        save_data()
        await query.edit_message_text("✅ Данные очищены.")
        await main_menu(update)
    
    elif data in ["back_menu", "start_bot"]:
        await main_menu(update)

if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
        
