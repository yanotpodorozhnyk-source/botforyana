import logging
import os
import base64
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import gspread
from google.oauth2.service_account import Credentials


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")


# ---------------- GOOGLE AUTH ----------------

credentials_b64 = os.getenv("GOOGLE_CREDENTIALS")

credentials_json = base64.b64decode(credentials_b64).decode("utf-8")

creds_dict = json.loads(credentials_json)

creds = Credentials.from_service_account_info(
    creds_dict,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

gc = gspread.authorize(creds)


# ---------------- GOOGLE SHEETS ----------------

SOCIAL_SHEET_ID = "197_It5B9M2d5pX2m3igzrQGF3snHs9mzOzPuAQ_SUjU"

social_sheet = gc.open_by_key(SOCIAL_SHEET_ID)

pharmacies_sheet = social_sheet.worksheet("Аптеки учасники оновлено 18.11")
program_sheet = social_sheet.worksheet("Умови соц.програм")


# ---------------- LOAD PHARMACIES ----------------

def load_pharmacies():

    rows = pharmacies_sheet.get_all_values()

    headers = rows[0]

    pharmacies = []

    for row in rows[1:]:

        pharmacy = {
            "number": row[0],
            "region": row[1],
            "city": row[2],
            "street": row[3],
            "phone": row[4],
            "programs": []
        }

        for i in range(5, len(headers)):

            value = row[i].lower()

            if value and "відключено" not in value:
                pharmacy["programs"].append(headers[i])

        pharmacies.append(pharmacy)

    return pharmacies


PHARMACIES = load_pharmacies()

print("✅ Pharmacies loaded:", len(PHARMACIES))


# ---------------- LOAD PROGRAMS ----------------

def load_programs():

    rows = program_sheet.get_all_values()

    programs = {}
    current_program = None

    for row in rows:

        cell = row[0].strip()

        if cell and cell.isupper():

            current_program = cell
            programs[current_program] = []

        elif current_program and cell:

            programs[current_program].append(cell)

    return programs


PROGRAMS = load_programs()

print("✅ Programs loaded:", len(PROGRAMS))


# ---------------- SEARCH ----------------

def pharmacies_by_program(program):

    program = program.lower()

    result = []

    for p in PHARMACIES:

        for prog in p["programs"]:

            if program in prog.lower():

                result.append(
                    f"🏥 Аптека {p['number']}\n"
                    f"{p['region']} {p['city']}\n"
                    f"{p['street']}\n"
                    f"{p['phone']}"
                )

                break

    return result


# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [InlineKeyboardButton("Соціальні програми", callback_data="social_programs")]
    ]

    await update.message.reply_text(
        "Оберіть розділ:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------- CALLBACK ----------------

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data


    if data == "social_programs":

        keyboard = [
            [InlineKeyboardButton("Карткові соц програми", callback_data="card_programs")]
        ]

        await query.edit_message_text(
            "Оберіть тип:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


    elif data == "card_programs":

        keyboard = []

        for program in PROGRAMS.keys():

            keyboard.append([
                InlineKeyboardButton(program, callback_data=f"program_{program}")
            ])

        keyboard.append([
            InlineKeyboardButton("🔎 Пошук вручну", callback_data="search_program")
        ])

        await query.edit_message_text(
            "Оберіть програму або скористайтесь пошуком:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


    elif data.startswith("program_"):

        program = data.replace("program_", "")

        pharmacies = pharmacies_by_program(program)

        if not pharmacies:

            await query.edit_message_text("Аптеки не знайдено")
            return

        text = "\n\n".join(pharmacies[:20])

        await query.edit_message_text(text)


    elif data == "search_program":

        context.user_data["mode"] = "search_program"

        await query.edit_message_text(
            "Введіть назву програми:"
        )


# ---------------- MESSAGE SEARCH ----------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    mode = context.user_data.get("mode")


    if mode == "search_program":

        pharmacies = pharmacies_by_program(text)

        if not pharmacies:

            await update.message.reply_text("Нічого не знайдено")
            return

        result = "\n\n".join(pharmacies[:20])

        await update.message.reply_text(result)


# ---------------- MAIN ----------------

def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(button))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot started")

    app.run_polling()


if __name__ == "__main__":
    main()
