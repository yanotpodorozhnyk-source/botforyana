import logging
import hashlib
import gspread

from google.oauth2.service_account import Credentials

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ---------------- LOGGING ----------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ---------------- TOKEN ----------------

TOKEN = "ТУТ_ТВІЙ_ТОКЕН"

# ---------------- GOOGLE SHEETS ----------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=SCOPES
)

client = gspread.authorize(creds)

sheet = client.open("База знань").sheet1

data = sheet.get_all_records()

# ---------------- CALLBACK SAFE ----------------

def safe_callback(text):
    return hashlib.md5(text.encode()).hexdigest()[:32]

# ---------------- BUILD TREE ----------------

tree = {}
answers = {}
callback_map = {}

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

    cb = safe_callback(f"{cat}|{sub}|{q}")

    answers[cb] = ans
    callback_map[cb] = (cat, sub, q)

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = []

    for cat in tree:
        keyboard.append([
            InlineKeyboardButton(cat, callback_data=safe_callback(cat))
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Оберіть категорію:",
        reply_markup=reply_markup
    )

# ---------------- SEARCH START ----------------

async def check_apteka_start(update, context):

    query = update.callback_query

    context.user_data["search_apteka"] = True

    await query.message.reply_text(
        "Введіть номер аптеки:"
    )

# ---------------- BUTTON HANDLER ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data_cb = query.data

    # ---------------- CATEGORY ----------------

    for cat in tree:

        if safe_callback(cat) == data_cb:

            keyboard = []

            for sub in tree[cat]:
                keyboard.append([
                    InlineKeyboardButton(
                        sub,
                        callback_data=safe_callback(f"{cat}|{sub}")
                    )
                ])

            keyboard.append([
                InlineKeyboardButton("Головне меню", callback_data="main_menu")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"Категорія: {cat}",
                reply_markup=reply_markup
            )

            return

    # ---------------- SUBCATEGORY ----------------

    for cat in tree:
        for sub in tree[cat]:

            if safe_callback(f"{cat}|{sub}") == data_cb:

                # спец функція пошуку аптек
                if "підключена аптека" in sub.lower():

                    await check_apteka_start(update, context)
                    return

                keyboard = []

                for q in tree[cat][sub]:

                    keyboard.append([
                        InlineKeyboardButton(
                            q,
                            callback_data=safe_callback(f"{cat}|{sub}|{q}")
                        )
                    ])

                keyboard.append([
                    InlineKeyboardButton(
                        "Назад",
                        callback_data=safe_callback(cat)
                    )
                ])

                keyboard.append([
                    InlineKeyboardButton(
                        "Головне меню",
                        callback_data="main_menu"
                    )
                ])

                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    f"Підтема: {sub}",
                    reply_markup=reply_markup
                )

                return

    # ---------------- QUESTION ----------------

    if data_cb in answers:

        ans = answers[data_cb]

        if not ans:
            ans = "Інформація поки не додана."

        keyboard = [[
            InlineKeyboardButton("Головне меню", callback_data="main_menu")
        ]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            ans,
            reply_markup=reply_markup
        )

        return

    # ---------------- MAIN MENU ----------------

    if data_cb == "main_menu":

        keyboard = []

        for cat in tree:
            keyboard.append([
                InlineKeyboardButton(
                    cat,
                    callback_data=safe_callback(cat)
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "Головне меню:",
            reply_markup=reply_markup
        )

# ---------------- MESSAGE HANDLER ----------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if context.user_data.get("search_apteka"):

        apteka = update.message.text

        await update.message.reply_text(
            f"Пошук аптеки: {apteka}\n\n(тут буде перевірка підключення)"
        )

        context.user_data["search_apteka"] = False

# ---------------- MAIN ----------------

def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Bot started 🚀")

    app.run_polling()

if __name__ == "__main__":
    main()
