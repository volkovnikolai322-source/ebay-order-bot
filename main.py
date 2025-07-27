import os
import logging
import aiohttp
import gspread
import openai
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

# Настройка Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GSERVICE_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
client = gspread.authorize(creds)
sheet = client.open_by_key(GOOGLE_SHEETS_KEY).worksheet("Ebay 2")

openai.api_key = OPENAI_API_KEY

async def ocr_space_file(file_path):
    url = 'https://api.ocr.space/parse/image'
    data = {'apikey': OCR_API_KEY, 'language': 'eng'}
    with open(file_path, 'rb') as f:
        files = {'file': f}
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field('apikey', OCR_API_KEY)
            form.add_field('language', 'eng')
            form.add_field('file', f, filename=file_path, content_type='image/jpeg')
            async with session.post(url, data=form) as resp:
                return await resp.json()

def gpt_structured_fields(text):
    prompt = (
        "Ты — умный помощник. Разбери распознанный с чека eBay текст на такие поля и верни как JSON: "
        "Имя, Почта, Адрес, Телефон, Товар. "
        "Пример ответа: {\"Имя\": \"...\", \"Почта\": \"...\", \"Адрес\": \"...\", \"Телефон\": \"...\", \"Товар\": \"...\"}\n\n"
        f"Вот текст для разбора:\n{text}"
    )
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0
    )
    try:
        content = response['choices'][0]['message']['content']
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

    # 3. Запись только в нужные столбцы (D, E, G, H, I)
    row = [
        "",  # A: Дата заказа
        "",  # B: Продавец
        "",  # C: № п/п
        structured.get("Имя", ""),     # D
        structured.get("Почта", ""),   # E
        "",  # F: пустой
        structured.get("Адрес", ""),   # G
        structured.get("Телефон", ""), # H
        structured.get("Товар", ""),   # I
    ]
    sheet.append_row(row)
    await message.reply("Заказ структурирован и добавлен в таблицу.")
    os.remove(file_on_disk)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
