import os
import aiohttp
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
import csv
import io
import time

# --- Настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CSV_URL = "https://raw.githubusercontent.com/TheBugurtov/Figma-components-to-Google-Sheets/main/components.csv"

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Главное меню ---
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Найти компонент")],
        [KeyboardButton(text="Изучить гайды"), KeyboardButton(text="Предложить доработку")],
        [KeyboardButton(text="Добавить иконку или логотип"), KeyboardButton(text="Посмотреть последние изменения")],
        [KeyboardButton(text="Поддержка")]
    ],
    resize_keyboard=True
)

# --- FSM ---
class SearchFlow(StatesGroup):
    input_query = State()

# --- Кэш CSV ---
component_cache = None
last_fetch_time = 0
CACHE_TTL = 5 * 60  # 5 минут

async def get_component_data():
    global component_cache, last_fetch_time
    now = time.time()

    if component_cache and now - last_fetch_time < CACHE_TTL:
        return component_cache

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CSV_URL) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP error: {resp.status}")
                csv_text = await resp.text()
                reader = csv.DictReader(io.StringIO(csv_text))
                component_cache = list(reader)
                last_fetch_time = now
                print("CSV обновлен")
                return component_cache
    except Exception as e:
        print("Ошибка загрузки CSV:", e)
        return component_cache or []

async def search_components(query, type_):
    records = await get_component_data()
    if not records:
        return []

    q = (query or "").lower().strip()
    filtered = []

    for r in records:
        tags = (r.get("Tags", "") or "").lower().replace(" ", "").split(",")
        if any(q in tag for tag in tags):
            if type_ == "mobile" and r["File"].strip() == "App Components":
                filtered.append(r)
            elif type_ == "web" and r["File"].strip() != "App Components":
                filtered.append(r)

    return filtered

async def send_large_message(chat_id: int, text: str, delay: float = 0.5):
    """Отправляет большое сообщение частями с задержкой"""
    max_length = 4000
    parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    
    for part in parts:
        await bot.send_message(chat_id, part)
        if len(parts) > 1:
            await asyncio.sleep(delay)

# --- Команды ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Добрый день!\nЯ помощник Дизайн-системы.", reply_markup=main_menu)

@dp.message(lambda msg: msg.text and msg.text.lower() == "найти компонент")
async def search_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите название компонента:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(SearchFlow.input_query)

@dp.message(SearchFlow.input_query)
async def process_search(message: types.Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await state.clear()
        await message.answer("Поиск отменён", reply_markup=main_menu)
        return

    # Ищем в веб-компонентах
    results = await search_components(message.text, "web")
    
    if not results:
        await message.answer(
            f'Компоненты по запросу "{message.text}" не найдены.\nПопробуйте другой запрос или нажмите "Отмена"',
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Отмена")]],
                resize_keyboard=True
            )
        )
        # Остаемся в состоянии поиска
        return
    
    # Форматируем результаты
    formatted = [
        f"▪️ <b>{r['Component']}</b> ({r['File']})\n🔗 {r['Link']}"
        for r in results
    ]
    
    await send_large_message(
        message.chat.id,
        f"Найдено {len(results)} компонентов:\n\n" + "\n\n".join(formatted)
    )
    
    # После успешного поиска остаемся в режиме поиска
    await message.answer(
        "Введите следующий запрос или нажмите 'Отмена'",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
    )

# --- Информационные команды (без изменения состояния) ---
async def send_info_message(message: types.Message, text: str):
    """Отправляет информационное сообщение без изменения клавиатуры"""
    await send_large_message(message.chat.id, text)

@dp.message(lambda msg: msg.text and msg.text.lower() == "изучить гайды")
async def guides(message: types.Message):
    await send_info_message(message, """
<b>Хранилище правил дизайн-системы:</b>
<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=181-20673">Granat Guides</a>

<b>Быстрые ссылки:</b>
• <a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=313-8196">Типографика</a>
• <a href="https://www.figma.com/design/iqTCxAPRJJm6UlANLlYfva/Variables?node-id=48097-1187">Цветовые темы</a>
• <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=547-206394">Иконки</a>
""")

@dp.message(lambda msg: msg.text and msg.text.lower() == "предложить доработку")
async def suggest(message: types.Message):
    await send_info_message(message, """
<b>Предложить доработку:</b>
Оформляйте запросы в <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">GitLab</a>

<b>Требования:</b>
1. Укажите детальное описание
2. Приложите примеры и ссылки
3. Ожидайте ответ в течение 3 рабочих дней
""")

@dp.message(lambda msg: msg.text and msg.text.lower() == "добавить иконку или логотип")
async def add_icon(message: types.Message):
    await send_info_message(message, """
<b>Добавление иконок:</b>
1. Для интерфейсных иконок - <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">оформите запрос</a>
2. Для продуктовых иконок - согласуйте с маркетингом
3. Логотипы - используйте <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=29711-16375">шаблоны</a>
""")

@dp.message(lambda msg: msg.text and msg.text.lower() == "посмотреть последние изменения")
async def changes(message: types.Message):
    await send_info_message(message, """
<b>Последние изменения:</b>
• Обновление компонентов - 15.08.2023
• Новые иконки - 10.08.2023
• Исправления багов - 05.08.2023

Подробнее: https://t.me/c/1397080567/12194
""")

@dp.message(lambda msg: msg.text and msg.text.lower() == "поддержка")
async def support(message: types.Message):
    await send_info_message(message, """
<b>Поддержка дизайн-системы:</b>
1. <a href="https://t.me/+90sy0C1fFPwzNTY6">Telegram-чат</a>
2. Email: kuskova@mts.ru
3. Внутренняя документация

Перед обращением проверьте, нет ли ответа в <a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=181-20673">гайдах</a>
""")

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())