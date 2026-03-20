import logging
import os
import re
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


# ---------------- LOGGING ----------------

logging.basicConfig(level=logging.INFO)


# ---------------- GOOGLE AUTH ----------------

credentials_b64 = os.getenv("GOOGLE_CREDENTIALS")

credentials_json = base64.b64decode(credentials_b64).decode("utf-8")

creds_dict = json.loads(credentials_json)

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)

client = gspread.authorize(creds)


# ---------------- FILES ----------------

knowledge_sheet = client.open("База знань").sheet1

social_sheet = client.open("Соц. Проєкти")

pharmacy_sheet = social_sheet.worksheet("Аптеки учасники оновлено 18.11")

program_sheet = social_sheet.worksheet("Умови соц.проограм")


# ---------------- STATES ----------------

WAIT_DRUG = set()
WAIT_PROGRAM = set()
WAIT_PHARMACY = set()
WAIT_ADDRESS = set()


# ---------------- UTIL ----------------

def normalize(text):

    if not text:
        return ""

    return text.lower().strip()


def pharmacy_connected(value):

    if not value:
        return False

    if "відключено" in value.lower():
        return False

    return True


# ---------------- LOAD DATA ----------------

def load_pharmacies():

    rows = pharmacy_sheet.get_all_records()

    pharmacies = []

    for r in rows:

        pharmacy = {
            "number": str(r.get("Короткий номер", "")),
            "city": r.get("Місто", ""),
            "street": r.get("Вулиця", ""),
            "region": r.get("Область", ""),
            "phone": r.get("Телефон", ""),
            "programs": {}
        }

        for key, val in r.items():

            if key not in ["Короткий номер", "Місто", "Вулиця", "Область", "Телефон"]:

                if pharmacy_connected(str(val)):
                    pharmacy["programs"][key] = True

        pharmacies.append(pharmacy)

    return pharmacies


def load_programs():

    rows = program_sheet.get_all_values()

    programs = {}

    current_program = None

    for r in rows:

        if "Програма" in r[0]:

            current_program = r[1]

            programs[current_program] = []

            continue

        if current_program and len(r) > 2:

            drug = r[2]

            if not drug:
                continue

            if "виключ" in drug.lower():
                continue

            programs[current_program].append({
                "drug": drug,
                "limit": r[1],
                "discount": r[3]
            })

    return programs


PHARMACIES = load_pharmacies()

PROGRAMS = load_programs()


# ---------------- SEARCH ----------------

def search_drug(name):

    name = normalize(name)

    result = []

    for program, drugs in PROGRAMS.items():

        for d in drugs:

            if name in normalize(d["drug"]):

                result.append(
                    f"💳 {program}\n"
                    f"{d['drug']}\n"
                    f"Знижка: {d['discount']}\n"
                    f"Ліміт: {d['limit']}"
                )

    return result


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


def pharmacy_by_number(num):

    result = []

    for p in PHARMACIES:

        if p["number"].startswith(num):

            result.append(
                f"{p['number']} {p['city']} {p['street']}"
            )

    return result


def pharmacy_by_address(addr):

    addr = normalize(addr)

    result = []

    for p in PHARMACIES:

        text = normalize(p["city"] + " " + p["street"])

        if addr in text:

            result.append(
                f"{p['number']} {p['city']} {p['street']}"
            )

    return result


# ---------------- BOT ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [InlineKeyboardButton("📚 База знань", callback_data="knowledge")],
        [InlineKeyboardButton("💳 Соціальні програми", callback_data="social")]
    ]

    await update.message.reply_text(
        "Оберіть розділ",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    data = query.data


    if data == "social":

        keyboard = [
            [InlineKeyboardButton("🔎 Пошук препарату", callback_data="drug")],
            [InlineKeyboardButton("💳 Пошук програми", callback_data="program")],
            [InlineKeyboardButton("🏥 Пошук аптеки по номеру", callback_data="pharmacy")],
            [InlineKeyboardButton("📍 Пошук аптеки по адресі", callback_data="address")]
        ]

        await query.message.reply_text(
            "Оберіть варіант пошуку",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


    elif data == "drug":

        WAIT_DRUG.add(query.from_user.id)

        await query.message.reply_text("Введіть назву препарату")


    elif data == "program":

        WAIT_PROGRAM.add(query.from_user.id)

        await query.message.reply_text("Введіть назву програми")


    elif data == "pharmacy":

        WAIT_PHARMACY.add(query.from_user.id)

        await query.message.reply_text("Введіть номер аптеки")


    elif data == "address":

        WAIT_ADDRESS.add(query.from_user.id)

        await query.message.reply_text("Введіть адресу або місто")


async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.message.from_user.id

    msg = update.message.text


    if uid in WAIT_DRUG:

        WAIT_DRUG.remove(uid)

        res = search_drug(msg)

        await update.message.reply_text("\n\n".join(res[:10]) or "Нічого не знайдено")


    elif uid in WAIT_PROGRAM:

        WAIT_PROGRAM.remove(uid)

        res = pharmacies_by_program(msg)

        await update.message.reply_text("\n\n".join(res[:20]) or "Нічого не знайдено")


    elif uid in WAIT_PHARMACY:

        WAIT_PHARMACY.remove(uid)

        res = pharmacy_by_number(msg)

        await update.message.reply_text("\n".join(res) or "Нічого не знайдено")


    elif uid in WAIT_ADDRESS:

        WAIT_ADDRESS.remove(uid)

        res = pharmacy_by_address(msg)

        await update.message.reply_text("\n".join(res) or "Нічого не знайдено")


# ---------------- RUN ----------------

TOKEN = os.getenv("TELEGRAM_TOKEN")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

app.add_handler(CallbackQueryHandler(button))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))

print("Bot started")

app.run_polling()
