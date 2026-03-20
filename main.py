import logging
import re
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

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Google credentials ---
credentials_b64 = os.getenv("GOOGLE_CREDENTIALS")
credentials_json = base64.b64decode(credentials_b64).decode("utf-8")
creds_dict = json.loads(credentials_json)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = "197_It5B9M2d5pX2m3igzrQGF3snHs9mzOzPuAQ_SUjU"

sheet = client.open_by_key(SPREADSHEET_ID)

pharmacy_sheet = sheet.worksheet("Аптеки учасники оновлено 18.11")
program_sheet = sheet.worksheet("Умови соц.проограм")

# --- STATES ---
WAIT_DRUG = {}
WAIT_PROGRAM = {}
WAIT_PHARMACY_NUMBER = {}
WAIT_PHARMACY_ADDRESS = {}

# --- UTIL FUNCTIONS ---

def normalize(text):
    if not text:
        return ""
    return text.lower().strip()


def is_pharmacy_connected(value):
    if not value:
        return False

    value = value.lower()

    if "відключено" in value:
        return False

    return True


# --- LOAD PHARMACIES ---

def load_pharmacies():

    rows = pharmacy_sheet.get_all_records()

    pharmacies = []

    for r in rows:

        pharmacy = {
            "number": r.get("Короткий номер", ""),
            "city": r.get("Місто", ""),
            "street": r.get("Вулиця", ""),
            "region": r.get("Область", ""),
            "phone": r.get("Телефон", ""),
            "programs": {}
        }

        for key in r:
            if key not in [
                "Короткий номер",
                "Місто",
                "Вулиця",
                "Область",
                "Телефон"
            ]:

                if is_pharmacy_connected(r[key]):
                    pharmacy["programs"][key] = True

        pharmacies.append(pharmacy)

    return pharmacies


# --- LOAD PROGRAMS ---

def load_programs():

    rows = program_sheet.get_all_values()

    programs = {}
    current_program = None

    for r in rows:

        if "Програма" in r[0]:

            current_program = r[1].strip()
            programs[current_program] = []

            continue

        if current_program and r[2]:

            drug = r[2]

            if "виключ" in drug.lower():
                continue

            programs[current_program].append({
                "limit": r[1],
                "drug": drug,
                "discount": r[3]
            })

    return programs


PHARMACIES = load_pharmacies()
PROGRAMS = load_programs()

# --- SEARCH DRUG ---

def search_drug(name):

    results = []

    name = normalize(name)

    for program in PROGRAMS:

        for drug in PROGRAMS[program]:

            if name in normalize(drug["drug"]):

                results.append(
                    f"💳 {program}\n"
                    f"{drug['drug']}\n"
                    f"Знижка: {drug['discount']}\n"
                    f"Ліміт: {drug['limit']}\n"
                )

    return results


# --- SEARCH PROGRAM PHARMACIES ---

def pharmacies_by_program(program):

    result = []

    for p in PHARMACIES:

        if program in p["programs"]:

            result.append(
                f"🏥 {p['number']}\n"
                f"{p['region']} {p['city']}\n"
                f"{p['street']}\n"
                f"{p['phone']}"
            )

    return result


# --- SEARCH BY NUMBER ---

def pharmacy_by_number(num):

    result = []

    for p in PHARMACIES:

        if str(p["number"]).startswith(num):

            result.append(
                f"🏥 {p['number']}\n"
                f"{p['region']} {p['city']}\n"
                f"{p['street']}\n"
                f"{p['phone']}"
            )

    return result


# --- SEARCH BY ADDRESS ---

def pharmacy_by_address(text):

    text = normalize(text)

    result = []

    for p in PHARMACIES:

        addr = f"{p['city']} {p['street']}"

        if text in normalize(addr):

            result.append(
                f"🏥 {p['number']}\n"
                f"{p['region']} {p['city']}\n"
                f"{p['street']}\n"
                f"{p['phone']}"
            )

    return result


# --- START ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [InlineKeyboardButton("💳 Карткові соц програми", callback_data="social_programs")]
    ]

    await update.message.reply_text(
        "Оберіть розділ:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# --- BUTTON HANDLER ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "social_programs":

        keyboard = [
            [InlineKeyboardButton("🔎 Пошук препарату", callback_data="drug")],
            [InlineKeyboardButton("💳 Пошук програми", callback_data="program")],
            [InlineKeyboardButton("🏥 Аптека по номеру", callback_data="number")],
            [InlineKeyboardButton("📍 Аптека по адресі", callback_data="address")]
        ]

        await query.edit_message_text(
            "Оберіть варіант:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "drug":

        WAIT_DRUG[query.from_user.id] = True
        await query.message.reply_text("Введіть назву препарату")

    elif data == "program":

        WAIT_PROGRAM[query.from_user.id] = True
        await query.message.reply_text("Введіть назву програми")

    elif data == "number":

        WAIT_PHARMACY_NUMBER[query.from_user.id] = True
        await query.message.reply_text("Введіть номер аптеки")

    elif data == "address":

        WAIT_PHARMACY_ADDRESS[query.from_user.id] = True
        await query.message.reply_text("Введіть місто або вулицю")


# --- TEXT HANDLER ---

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.message.from_user.id
    text = update.message.text

    if uid in WAIT_DRUG:

        WAIT_DRUG.pop(uid)

        res = search_drug(text)

        if res:
            await update.message.reply_text("\n\n".join(res[:10]))
        else:
            await update.message.reply_text("Нічого не знайдено")

    elif uid in WAIT_PROGRAM:

        WAIT_PROGRAM.pop(uid)

        res = pharmacies_by_program(text)

        if res:
            await update.message.reply_text("\n\n".join(res[:20]))
        else:
            await update.message.reply_text("Аптек не знайдено")

    elif uid in WAIT_PHARMACY_NUMBER:

        WAIT_PHARMACY_NUMBER.pop(uid)

        res = pharmacy_by_number(text)

        if res:
            await update.message.reply_text("\n\n".join(res))
        else:
            await update.message.reply_text("Аптеку не знайдено")

    elif uid in WAIT_PHARMACY_ADDRESS:

        WAIT_PHARMACY_ADDRESS.pop(uid)

        res = pharmacy_by_address(text)

        if res:
            await update.message.reply_text("\n\n".join(res))
        else:
            await update.message.reply_text("Аптеку не знайдено")


# --- MAIN ---

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

app.run_polling()
