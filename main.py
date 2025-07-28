import os
import logging
import aiohttp
import gspread
import openai
import random
import re
from aiogram import Bot, Dispatcher, types
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
import json

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OCR_API_KEY = os.getenv('OCR_API_KEY')
GOOGLE_SHEETS_KEY = os.getenv('GOOGLE_SHEETS_KEY')
GSERVICE_JSON = os.getenv('GSERVICE_JSON')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GSERVICE_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
client_gsheets = gspread.authorize(creds)
sheet = client_gsheets.open_by_key(GOOGLE_SHEETS_KEY).worksheet("Ebay 2")

SYSTEM_PROMPT = """
Ты ассистент по обработке заказов eBay. Извлеки из текста только следующие поля:

1. Адрес — только улица, дом, город, штат, zip (только первые 5 цифр), страна не нужна, не указывай суффикс zip-4.
2. Название наушников — выбери из:
- Openrun Pro 2 Black
- Openrun Pro 2 Orange
- Openrun Pro 2 Silver
- Openswim Pro Gray
- Openswim Pro Red
- 2025 Opencomm 2 UC USB-C

Формат ответа:
{
    "Адрес": "",
    "Товар": ""
}
Если данные не удалось найти, оставь поле пустым. Не добавляй пояснений, только валидный JSON.
"""

MODEL_CODES = {
    "Openrun Pro 2 Black": "S820",
    "Openrun Pro 2 Orange": "S820",
    "Openrun Pro 2 Silver": "S820",
    "Openswim Pro Gray": "S710",
    "Openswim Pro Red": "S710",
    "2025 Opencomm 2 UC USB-C": "C120"
}

def random_digits(n):
    while True:
        digits = ''.join(random.choices('0123456789', k=n))
        if not re.match(r'(123456|654321|000000|111111|222222|333333|444444|555555|666666|777777|888888|999999)', digits):
            return digits

def parse_zip_and_city(address):
    zip_match = re.search(r'(\b\d{5}\b)', address)
    zip_code = zip_match.group(1) if zip_match else "00000"
    city_match = re.search(r'([A-Za-z ]+),\s?[A-Z]{2}\s?' + zip_code, address)
    city = city_match.group(1).strip() if city_match else ""
    return zip_code, city

def fake_phone(zip_code):
    area = zip_code[:3] if zip_code and zip_code[0] != "0" else str(random.randint(201, 999))
    rest = random_digits(7)
    return f"{area}{rest}"

def fake_sn(model):
    code = MODEL_CODES.get(model, "S000")
    return code + random_digits(10)

def ensure_row_490(sheet):
    existing_rows = len(sheet.get_all_values())
    needed = 489 - existing_rows
    for _ in range(max(0, needed)):
        sheet.append_row([""] * 13)

logging.info(f"Попытка добавить строку: {row} (len={len(row)})")
try:
    sheet.append_row(row)
    logging.info("Добавление прошло успешно!")
except Exception as e:
    logging.error(f"Ошибка при добавлении строки: {e}")

def gpt_structured_fields(text):
    client = openai.Client(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Распознанный текст:\n{text}"}
        ],
        max_tokens=400,
        temperature=0.7
    )
    try:
        content = response.choices[0].message.content
        data = json.loads(content)
        return data
    except Exception as e:
        print("Ошибка парсинга JSON:", e)
        return {}

@dp.message()
async def handle_photo(message: types.Message):
    if not message.photo:
        return
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = file.file_path
    file_on_disk = f"{photo.file_id}.jpg"
    await bot.download_file(file_path, file_on_disk)

    # 1. OCR
    ocr_result = await ocr_space_file(file_on_disk)
    parsed_text = ocr_result['ParsedResults'][0]['ParsedText']

    # 2. AI-парсинг через GPT
    structured = await asyncio.to_thread(gpt_structured_fields, parsed_text)
    address = structured.get("Адрес", "")
    product = structured.get("Товар", "")

    # 3. Генерируем телефон и серийник
    zip_code, city = parse_zip_and_city(address)
    phone = fake_phone(zip_code)
    sn = fake_sn(product)

    # 4. Запись только в нужные столбцы (D, G, H, I, J)
    row = [
        "",                   # A
        "",                   # B
        "",                   # C
        "",                   # D: Имя не требуется
        "",                   # E: Почта не требуется
        "",                   # F
        address,              # G: Адрес
        phone,                # H: Телефон
        product,              # I: Товар
        sn,                   # J: S/N
        "", "", ""            # K, L, M
    ]
    ensure_row_490(sheet)
    sheet.append_row(row)
    await message.reply("Заказ структурирован и добавлен в таблицу.")
    os.remove(file_on_disk)

async def ocr_space_file(file_path):
    url = 'https://api.ocr.space/parse/image'
    data = {'apikey': OCR_API_KEY, 'language': 'eng'}
    with open(file_path, 'rb') as f:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field('apikey', OCR_API_KEY)
            form.add_field('language', 'eng')
            form.add_field('file', f, filename=file_path, content_type='image/jpeg')
            async with session.post(url, data=form) as resp:
                return await resp.json()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
