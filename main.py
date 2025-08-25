import asyncio
from typing import List, Union
import logging
import json
import re

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher.handler import CancelHandler
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.middlewares import BaseMiddleware
from config import API_TOKEN, CHANNEL_ID, TEMPLATE_FILE, ADMIN_ID

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)
dp.middleware.setup(LoggingMiddleware())

# Загрузка шаблонов из файла
try:
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as file:  # Используем unicode-escape для корректного чтения кириллических символов
        TEMPLATE = json.load(file)
except FileNotFoundError:
    TEMPLATE = '{}'

class AlbumMiddleware(BaseMiddleware):

    album_data: dict = {}

    def __init__(self, latency: Union[int, float] = 0.01):
        self.latency = latency
        super().__init__()

    async def on_process_message(self, message: types.Message, data: dict):
        if not message.media_group_id:
            return

        try:
            self.album_data[message.media_group_id].append(message)
            raise CancelHandler()
        except KeyError:
            self.album_data[message.media_group_id] = [message]
            await asyncio.sleep(self.latency)

            message.conf["is_last"] = True
            data["album"] = self.album_data[message.media_group_id]

    async def on_post_process_message(self, message: types.Message, result: dict, data: dict):
        if message.media_group_id and message.conf.get("is_last"):
            del self.album_data[message.media_group_id]


# Обработчик команды /pattern
@dp.message_handler(commands=['pattern'])
async def handle_broadcast_command(message: types.Message):
    global TEMPLATE
    # Проверка, что пользователь, отправивший команду, является администратором
    if not message.from_user.id == ADMIN_ID:
        return

    # Получаем текст для рассылки из сообщения пользователя
    pattern_text = message.get_args()

    # Проверяем, что текст для рассылки не пустой
    if not pattern_text:
        TEMPLATE = '{}'
    else:
        TEMPLATE = pattern_text.replace("\\n", "\n")  # Заменяем \\n на \n для новой строки

    # Сохраняем список отвеченных пользователей в файл
    with open(TEMPLATE_FILE, 'w') as file:
        json.dump(TEMPLATE, file)

    pattern = TEMPLATE.format('Пример текста поста')

    # Отправляем подтверждение о выполнении рассылки
    await message.answer(f"Вы обновили шаблон текста:\n\n <code>{pattern}</code>", parse_mode=types.ParseMode.HTML)

@dp.message_handler(content_types=['photo'])
async def handle_photos(message: types.Message, album: List[types.Message] = None):
    if not album:
        photo_id = message.photo[-1].file_id
        caption_with_template = TEMPLATE.format(message.caption if message.caption else '')
        await bot.send_photo(CHANNEL_ID, photo_id, caption=caption_with_template)
    else:
        await handle_albums(message, album)


@dp.message_handler(content_types=['video'])
async def handle_videos(message: types.Message, album: List[types.Message] = None):
    if not album:
        video_id = message.video[-1].file_id
        caption_with_template = TEMPLATE.format(message.caption if message.caption else '')
        await bot.send_photo(CHANNEL_ID, video_id, caption=caption_with_template)
    else:
        await handle_albums(message, album)


@dp.message_handler(content_types=['photo', 'video'])
async def handle_albums(message: types.Message, album: List[types.Message] = None):
    # Создать медиа группу
    media = types.MediaGroup()
    group = []
    if album:
        for index, obj in enumerate(album):
            if obj.photo:
                file_id = obj.photo[-1].file_id
                if index == 0:
                    caption_with_template = TEMPLATE.format(obj.caption if obj.caption else '')
                    media.attach_photo(file_id, caption=caption_with_template)
                else:
                    media.attach_photo(file_id)
            elif obj.video:
                file_id = obj.video.file_id
                if index == 0:
                    caption_with_template = TEMPLATE.format(obj.caption if obj.caption else '')
                    media.attach_video(file_id, caption=caption_with_template)
                else:
                    media.attach_video(file_id)
            else:
                continue

        await bot.send_media_group(chat_id=CHANNEL_ID, media=media)


@dp.message_handler(content_types=['text'])
async def process_message(message: types.Message):
    text = message.text
    text_with_template = TEMPLATE.format(text)
    await bot.send_message(CHANNEL_ID, text_with_template)

if __name__ == "__main__":
    dp.middleware.setup(AlbumMiddleware())
    executor.start_polling(dp, skip_updates=True)
