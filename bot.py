from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from fpdf import FPDF
from io import BytesIO
import json
import os

# --- Словарь для хранения данных: {артикул: {цвет: количество_пар}} ---
inventory = {}

# --- Сессия текущего артикула ---
current_article = None

# --- Загрузка стартового инвентаря из JSON ---
try:
    with open("initial_inventory.json", "r", encoding="utf-8") as f:
        initial_data = json.load(f)
        for art, colors in initial_data.items():
            inventory[art] = {color: 0 for color in colors}
except FileNotFoundError:
    pass  # если файла нет, работаем пустым inventory

# --- Главное меню ---
async def main_menu(update):
    keyboard = [
        [InlineKeyboardButton("Рестарт всего", callback_data="restart_confirm")],
        [InlineKeyboardButton("Итог / PDF", callback_data="pdf")]
    ]
    await update.message.reply_text(
        "Введите артикул или выберите команду ниже:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Старт бота ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update)

# --- Обработка сообщений (артикул или новый цвет) ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_article
    text = update.message.text.strip()
    
    if text.isdigit():  # новый артикул
        current_article = text
        if current_article not in inventory:
            inventory[current_article] = {}  # пока без цветов, можно добавить потом
        await show_colors(update)
    else:  # новый цвет для текущего артикула
        if current_article:
            color = text
            if color not in inventory[current_article]:
                inventory[current_article][color] = 0
            await show_colors(update)

# --- Показ цветов с кнопками +6 ---
async def show_colors(update_or_query):
    global current_article
    article = inventory[current_article]
    keyboard = []
    for color in article:
        keyboard.append([InlineKeyboardButton(f"{color} [+6] ({article[color]} пар)", callback_data=f"add6|{color}")])
    keyboard.append([InlineKeyboardButton("➕ Добавить цвет", callback_data="add_color")])
    keyboard.append([InlineKeyboardButton("🔄 Сброс артикула", callback_data="reset_article_confirm")])
    keyboard.append([InlineKeyboardButton("⬅ Назад к меню", callback_data="back")])
    keyboard.append([InlineKeyboardButton("🔄 Рестарт всего", callback_data="restart_confirm")])
    keyboard.append([InlineKeyboardButton("➡ Итог / PDF", callback_data="pdf")])

    text = f"Артикул: {current_article}"
    if hasattr(update_or_query, "message"):
        await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update_or_query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- Обработка нажатий кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_article
    query = update.callback_query
    await query.answer()
    data = query.data

    # --- +6 пар ---
    if data.startswith("add6"):
        _, color = data.split("|")
        inventory[current_article][color] += 6
        await show_colors(query)

    # --- Добавление цвета ---
    elif data == "add_color":
        await query.message.reply_text("Введите название нового цвета:")

    # --- Подтверждение сброса артикула ---
    elif data == "reset_article_confirm":
        keyboard = [
            [InlineKeyboardButton("Да", callback_data="reset_article")],
            [InlineKeyboardButton("Нет", callback_data="cancel")]
        ]
        await query.message.reply_text(f"Вы уверены, что хотите обнулить артикул {current_article}?", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "reset_article":
        if current_article in inventory:
            for color in inventory[current_article]:
                inventory[current_article][color] = 0
            await query.message.reply_text(f"Артикул {current_article} сброшен.")
            await show_colors(query)

    # --- Подтверждение Рестарт всего ---
    elif data == "restart_confirm":
        keyboard = [
            [InlineKeyboardButton("Да", callback_data="restart")],
            [InlineKeyboardButton("Нет", callback_data="cancel")]
        ]
        await query.message.reply_text("Вы уверены, что хотите полностью сбросить все данные?", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "restart":
        inventory.clear()
        current_article = None
        await query.message.reply_text("Сессия сброшена. Начинаем с чистого листа.")
        await main_menu(query)

    # --- Отмена действия ---
    elif data == "cancel":
        await query.message.reply_text("Действие отменено.")
        if current_article:
            await show_colors(query)
        else:
            await main_menu(query)

    # --- Итог / PDF ---
    elif data == "pdf":
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt="Отчёт по складу", ln=True, align='C')
        pdf.ln(5)
        for article, colors in inventory.items():
            pdf.cell(200, 10, txt=f"Артикул {article}:", ln=True)
            for color, qty in colors.items():
                pdf.cell(200, 10, txt=f"  {color}: {qty} пар", ln=True)
            pdf.ln(3)
        
        pdf_buffer = BytesIO()
        pdf.output(pdf_buffer)
        pdf_buffer.seek(0)
        await query.message.reply_document(document=pdf_buffer, filename="inventory_report.pdf")

    # --- Назад к меню ---
    elif data == "back":
        current_article = None
        await main_menu(query)

# --- Команда для массового добавления артикулов и цветов ---
async def massadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lines = text.split("\n")
    count = 0
    for line in lines:
        if ":" in line:
            art, colors_str = line.split(":", 1)
            art = art.strip()
            colors = [c.strip() for c in colors_str.split(",") if c.strip()]
            if art not in inventory:
                inventory[art] = {}
            for color in colors:
                if color not in inventory[art]:
                    inventory[art][color] = 0
            count += 1
    await update.message.reply_text(f"Добавлено/обновлено {count} артикулов с цветами.")

# --- Запуск бота ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # токен из переменной окружения
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("massadd", massadd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
app.add_handler(CallbackQueryHandler(button_handler))
app.run_polling()
