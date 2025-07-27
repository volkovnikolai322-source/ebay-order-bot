import os
import logging
import aiohttp
import gspread
from aiogram import Bot, Dispatcher, types
from aiogram.types import ContentType
from aiogram.utils import executor
from oauth2client.service_account import ServiceAccountCredentials
import json

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OCR_API_KEY = os.getenv('OCR_API_KEY')
GOOGLE_SHEETS_KEY = os.getenv('GOOGLE_SHEETS_KEY')  # название таблицы
GSERVICE_JSON = os.getenv('GSERVICE_JSON')  # json credentials (строкой)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# Настройка Google Sheets через сервисный аккаунт
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GSERVICE_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEETS_KEY).sheet1

async def ocr_space_file(file_path):
    url = 'https://api.ocr.space/parse/image'
    with open(file_path, 'rb') as f:
        files = {'file': f}
        data = {'apikey': OCR_API_KEY, 'language': 'eng'}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, files=files) as resp:
                return await resp.json()

@dp.message_handler(content_types=ContentType.PHOTO)
async def handle_photo(message: types.Message):
    # Получаем фото (максимальное качество)
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file_path = file_info.file_path
    file_on_disk = f"{photo.file_id}.jpg"
    await bot.download_file(file_path, file_on_disk)

    # Распознаём текст
    ocr_result = await ocr_space_file(file_on_disk)
    parsed_text = ocr_result['ParsedResults'][0]['ParsedText']
    
    # Здесь можно обработать parsed_text → разбить на поля (или через AI)
    # Для примера просто пишем в таблицу всё в одну ячейку
    sheet.append_row([parsed_text])

    await message.reply("Заказ распознан и добавлен в таблицу.")
    os.remove(file_on_disk)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

