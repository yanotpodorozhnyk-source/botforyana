import logging
import hashlib
import gspread

from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)

TOKEN = "ТУТ_ТВІЙ_ТОКЕН"

# ---------------- GOOGLE SHEETS ----------------
scopes = ["https://www.googleapis.com/auth/spreadsheets"]

creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=scopes
)

gc = gspread.authorize(creds)

sheet = gc.open("База знань").sheet1
data = sheet.get_all_records()

print(f"📚 Завантажено записів: {len(data)}")

# ---------------- TREE ----------------
tree = {}
answers = {}

for row in data:
    cat = row["Категорія"]
    sub = row["Підтема"]
    q = row["Питання"]
    ans = row["Відповідь"]

    if cat not in tree:
        tree[cat] = {}

    if sub not in tree[cat]:
        tree[cat][sub] = []

    tree[cat][sub].append(q)
    answers[f"{cat}|{sub}|{q}"] = ans


# ---------------- CALLBACK SAFE ----------------
callback_map = {}

def safe_callback(text):
    key = hashlib.md5(text.encode()).hexdigest()[:10]
    callback_map[key] = text
    return key


# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = []

    for cat in tree:
        keyboard.append(
            [InlineKeyboardButton(cat, callback_data=safe_callback(cat))]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Оберіть категорію:",
        reply_markup=reply_markup
    )


# ---------------- SEARCH START ----------------
async def check_apteka_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    context.user_data["search_apteka"] = True

    await query.edit_message_text(
        "Введіть номер аптеки:"
    )


# ---------------- MESSAGE SEARCH ----------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.user_data.get("search_apteka"):
        return

    apteka = update.message.text

    context.user_data["search_apteka"] = False

    keyboard = [
        [InlineKeyboardButton("Головне меню", callback_data="main_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🔎 Пошук аптеки: {apteka}\n\n(тут буде перевірка підключення)",
        reply_markup=reply_markup
    )


# ---------------- MENU HANDLER ----------------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data_cb = query.data

    if data_cb == "main_menu":

        keyboard = []

        for cat in tree:
            keyboard.append(
                [InlineKeyboardButton(cat, callback_data=safe_callback(cat))]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "Оберіть категорію:",
            reply_markup=reply_markup
        )
        return

    if data_cb not in callback_map:
        return

    data = callback_map[data_cb]

    parts = data.split("|")

    # ---------------- CATEGORY ----------------
    if len(parts) == 1:

        cat = parts[0]

        keyboard = [
            [InlineKeyboardButton(sub, callback_data=safe_callback(f"{cat}|{sub}"))]
            for sub in tree[cat]
        ]

        keyboard.append(
            [InlineKeyboardButton("Головне меню", callback_data="main_menu")]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"Категорія: {cat}",
            reply_markup=reply_markup
        )
        return


    # ---------------- SUBCATEGORY ----------------
    if len(parts) == 2:

        cat, sub = parts

        # ⭐ СПЕЦІАЛЬНА КНОПКА ПОШУКУ
        if "підключена аптека" in sub.lower():

            await check_apteka_start(update, context)
            return

        keyboard = [
            [InlineKeyboardButton(q, callback_data=safe_callback(f"{cat}|{sub}|{q}"))]
            for q in tree[cat][sub]
        ]

        keyboard.append(
            [InlineKeyboardButton("Назад", callback_data=safe_callback(cat))]
        )

        keyboard.append(
            [InlineKeyboardButton("Головне меню", callback_data="main_menu")]
        )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"Підтема: {sub}\nОберіть питання:",
            reply_markup=reply_markup
        )
        return


    # ---------------- ANSWER ----------------
    if len(parts) == 3:

        cat, sub, q = parts

        ans = answers.get(data, "Інформація відсутня")

        keyboard = [
            [InlineKeyboardButton("Назад", callback_data=safe_callback(f"{cat}|{sub}"))],
            [InlineKeyboardButton("Головне меню", callback_data="main_menu")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            ans if ans else "Інформація відсутня",
            reply_markup=reply_markup
        )


# ---------------- MAIN ----------------
def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(button))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🚀 Bot started")

    app.run_polling()


if __name__ == "__main__":
    main()
