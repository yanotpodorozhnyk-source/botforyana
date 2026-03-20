import logging
import re
import hashlib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import gspread
import os
import base64
import json

# --- Decode Google Sheets credentials ---
credentials_b64 = os.getenv('GOOGLE_CREDENTIALS')
if credentials_b64:
    credentials_json = base64.b64decode(credentials_b64).decode('utf-8')
    credentials_dict = json.loads(credentials_json)
    with open('credentials.json', 'w') as f:
        json.dump(credentials_dict, f)

# --- Логування ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Google Sheets ---
gc = gspread.service_account(filename='credentials.json')

knowledge_sheet = gc.open('База знань').sheet1
knowledge_data = knowledge_sheet.get_all_records()

pharmacy_sheet = gc.open('Соц програми').worksheet('Аптеки')
pharmacies = pharmacy_sheet.get_all_records()

program_sheet = gc.open('Соц програми').worksheet('Препарати')
program_data = program_sheet.get_all_records()

# --- Стани користувачів ---
user_states = {}

# --- Отримати номер аптеки ---
def get_pharmacy_number(text):
    match = re.match(r"\d+", str(text))
    if match:
        return match.group()
    return None

# --- Дерево бази знань ---
tree = {}
for row in knowledge_data:
    cat = row['Категорія'].strip()
    sub = row['Підтема'].strip()
    q = row['Питання'].strip()
    ans = row.get('Відповідь', '').strip()
    if cat not in tree:
        tree[cat] = {}
    if sub not in tree[cat]:
        tree[cat][sub] = {}
    tree[cat][sub][q] = ans

# --- Безпечний callback ---
def safe_callback(text):
    clean = re.sub(r'\s+', '_', text.strip())
    clean = re.sub(r'[^a-zA-Z0-9_]', '', clean)
    h = hashlib.sha1(text.encode('utf-8')).hexdigest()[:20]
    return f"{clean}_{h}"

# --- Старт ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(cat, callback_data=safe_callback(cat))] for cat in tree]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привіт! Обери категорію:", reply_markup=reply_markup)

# --- Пошук препарату ---
def search_drug(name):
    results = []
    for row in program_data:
        if name.lower() in row["Препарат"].lower():
            results.append(row)
    return results

# --- Пошук аптек по програмі ---
def pharmacies_by_program(program):
    result = []
    for row in pharmacies:
        if row.get(program):
            number = get_pharmacy_number(row["Аптека"])
            result.append(f"{number}\n{row['Область']} {row['Місто']}\n{row['Вулиця']}\n☎ {row['Телефон']}")
    return result

# --- Пошук по номеру ---
def search_pharmacy_number(number):
    results = []
    for row in pharmacies:
        n = get_pharmacy_number(row["Аптека"])
        if n == number:
            results.append(f"{n}\n{row['Область']} {row['Місто']}\n{row['Вулиця']}\n☎ {row['Телефон']}")
    return results

# --- Пошук по адресі ---
def search_address(text):
    results = []
    for row in pharmacies:
        addr = f"{row['Місто']} {row['Вулиця']}".lower()
        if text.lower() in addr:
            n = get_pharmacy_number(row["Аптека"])
            results.append(f"{n}\n{row['Область']} {row['Місто']}\n{row['Вулиця']}\n☎ {row['Телефон']}")
    return results

# --- Обробка кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_cb = query.data

    # --- Головне меню ---
    if data_cb == "main_menu":
        keyboard = [[InlineKeyboardButton(cat, callback_data=safe_callback(cat))] for cat in tree]
        await query.edit_message_text("Привіт! Обери категорію:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- Категорія ---
    for cat in tree:
        if safe_callback(cat) == data_cb:
            keyboard = [[InlineKeyboardButton(sub, callback_data=safe_callback(f"{cat}|{sub}"))] for sub in tree[cat]]
            keyboard.append([InlineKeyboardButton("Головне меню", callback_data="main_menu")])
            await query.edit_message_text(f"Категорія: {cat}\nОберіть підтему:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

    # --- Підтема ---
    for cat in tree:
        for sub in tree[cat]:
            if safe_callback(f"{cat}|{sub}") == data_cb:
                if cat == "Соціальні програми" and sub == "Карткові соц програми":
                    keyboard = [
                        [InlineKeyboardButton("🔎 Пошук по препарату", callback_data="drug_search")],
                        [InlineKeyboardButton("💳 Пошук по програмі", callback_data="program_search")],
                        [InlineKeyboardButton("🏥 Пошук аптеки по номеру", callback_data="pharmacy_number")],
                        [InlineKeyboardButton("📍 Пошук аптеки по адресі", callback_data="pharmacy_address")],
                        [InlineKeyboardButton("Головне меню", callback_data="main_menu")]
                    ]
                    await query.edit_message_text("Оберіть варіант пошуку:", reply_markup=InlineKeyboardMarkup(keyboard))
                    return
                # Для інших підтем бази знань
                keyboard = [[InlineKeyboardButton(q, callback_data=safe_callback(f"{cat}|{sub}|{q}"))] for q in tree[cat][sub]]
                keyboard.append([InlineKeyboardButton("Назад", callback_data=safe_callback(cat))])
                keyboard.append([InlineKeyboardButton("Головне меню", callback_data="main_menu")])
                await query.edit_message_text(f"Підтема: {sub}\nОберіть питання:", reply_markup=InlineKeyboardMarkup(keyboard))
                return

    # --- Пошук препарату ---
    if data_cb == "drug_search":
        user_states[query.from_user.id] = "drug"
        await query.edit_message_text("Введіть назву препарату")
        return

    # --- Пошук програми ---
    if data_cb == "program_search":
        programs = [p for p in program_data[0].keys() if p not in ["Препарат", "Ліміт", "Знижка"]]
        keyboard = [[InlineKeyboardButton(p, callback_data=f"program_{p}")] for p in programs]
        keyboard.append([InlineKeyboardButton("Головне меню", callback_data="main_menu")])
        await query.edit_message_text("Оберіть програму:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- Аптеки програми ---
    if data_cb.startswith("program_"):
        program = data_cb.replace("program_", "")
        result = pharmacies_by_program(program)
        text = "\n\n".join(result[:20]) if result else "Немає аптек"
        await query.edit_message_text(text)
        return

    # --- Пошук аптеки по номеру ---
    if data_cb == "pharmacy_number":
        user_states[query.from_user.id] = "pharmacy_number"
        await query.edit_message_text("Введіть номер аптеки")
        return

    # --- Пошук аптеки по адресі ---
    if data_cb == "pharmacy_address":
        user_states[query.from_user.id] = "address"
        await query.edit_message_text("Введіть місто або адресу")
        return

    # --- Питання ---
    for cat in tree:
        for sub in tree[cat]:
            for q, ans in tree[cat][sub].items():
                if safe_callback(f"{cat}|{sub}|{q}") == data_cb:
                    keyboard = [
                        [InlineKeyboardButton("Назад", callback_data=safe_callback(f"{cat}|{sub}"))],
                        [InlineKeyboardButton("Головне меню", callback_data="main_menu")]
                    ]
                    await query.edit_message_text(ans, reply_markup=InlineKeyboardMarkup(keyboard))
                    return

# --- Обробка тексту ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    state = user_states.get(user_id)

    if state == "drug":
        results = search_drug(text)
        if not results:
            await update.message.reply_text("Препарат не знайдено")
            return
        msg = ""
        for r in results:
            msg += f"{r['Програма']}\n{r['Препарат']}\nЗнижка {r['Знижка']}\n\n"
        await update.message.reply_text(msg)
        return

    if state == "pharmacy_number":
        results = search_pharmacy_number(text)
        if not results:
            await update.message.reply_text("Аптеку не знайдено")
            return
        await update.message.reply_text("\n\n".join(results[:20]))
        return

    if state == "address":
        results = search_address(text)
        if not results:
            await update.message.reply_text("Аптеку не знайдено")
            return
        await update.message.reply_text("\n\n".join(results[:20]))
        return

# --- Запуск ---
if __name__ == '__main__':
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("Бот запущений...")
    app.run_polling()
