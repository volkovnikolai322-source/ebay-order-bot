import os
import logging
import aiohttp
import gspread
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ContentType
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
import json

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OCR_API_KEY = os.getenv('OCR_API_KEY')
GOOGLE_SHEETS_KEY = os.getenv('GOOGLE_SHEETS_KEY')  # ID Google Таблицы
GSERVICE_JSON = os.getenv('GSERVICE_JSON')  # содержимое JSON сервисного аккаунта

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Настройка Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GSERVICE_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
client = gspread.authorize(creds)
sheet = client.open_by_key(GOOGLE_SHEETS_KEY).sheet1

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

@dp.message()
async def handle_photo(message: types.Message):
    if not message.photo:
        return
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = file.file_path
    file_on_disk = f"{photo.file_id}.jpg"
    await bot.download_file(file_path, file_on_disk)

    # Распознаём текст через OCR Space
    ocr_result = await ocr_space_file(file_on_disk)
    parsed_text = ocr_result['ParsedResults'][0]['ParsedText']
    
    # Добавляем строку в Google Таблицу (можно улучшить парсинг под свои поля)
    sheet.append_row([parsed_text])

    await message.reply("Заказ распознан и добавлен в таблицу.")
    os.remove(file_on_disk)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
