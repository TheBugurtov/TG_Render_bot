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

# Инициализация бота с обработкой конфликтов
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML"),
    session_timeout=60  # Увеличиваем таймаут сессии
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
    choose_type = State()
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

    return [f"<b>{r['Component']}</b> из <b>{r['File']}</b>\n{r['Link']}" for r in filtered]

# --- Команды ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Добрый день!\nЯ помощник Дизайн-системы.", reply_markup=main_menu)

@dp.message(lambda msg: msg.text and msg.text.lower() == "назад")
async def go_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы в главном меню:", reply_markup=main_menu)

# --- Найти компонент ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "найти компонент")
async def ask_type(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мобильный компонент"), KeyboardButton(text="Веб-компонент")],
            [KeyboardButton(text="Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите тип компонента:", reply_markup=kb)
    await state.set_state(SearchFlow.choose_type)

@dp.message(SearchFlow.choose_type)
async def type_chosen(message: types.Message, state: FSMContext):
    if message.text == "Мобильный компонент":
        await state.update_data(type="mobile")
    elif message.text == "Веб-компонент":
        await state.update_data(type="web")
    else:
        return
    await message.answer(
        "Введите название компонента:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )
    await state.set_state(SearchFlow.input_query)

@dp.message(SearchFlow.input_query)
async def query_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    results = await search_components(message.text, data["type"])
    
    if results:
        # Разбиваем длинные сообщения на части
        message_parts = []
        current_part = f"Найдено: {len(results)}\n\n"
        
        for result in results:
            if len(current_part) + len(result) > 4000:  # Лимит Telegram
                message_parts.append(current_part)
                current_part = ""
            current_part += result + "\n\n"
        
        message_parts.append(current_part)
        
        for part in message_parts:
            await message.answer(part)
    else:
        await message.answer(f'Компоненты по запросу "{message.text}" не найдены.')
    
    await state.clear()
    await message.answer("Вы в главном меню:", reply_markup=main_menu)

# --- Остальные пункты меню ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "изучить гайды")
async def guides(message: types.Message):
    await message.answer(
        """Хранилище правил и рекомендаций дизайн-системы в Figma — <a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=181-20673">Granat Guides</a>""",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )

@dp.message(lambda msg: msg.text and msg.text.lower() == "предложить доработку")
async def suggest(message: types.Message):
    await message.answer(
        "➡️ Нашли баг? Заводите задачу в GitLab.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )

@dp.message(lambda msg: msg.text and msg.text.lower() == "добавить иконку или логотип")
async def add_icon(message: types.Message):
    await message.answer(
        "➡️ Ознакомьтесь с требованиями к иконкам в GitLab.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )

@dp.message(lambda msg: msg.text and msg.text.lower() == "посмотреть последние изменения")
async def changes(message: types.Message):
    await message.answer("Последние изменения в DS GRANAT: https://t.me/c/1397080567/12194")

@dp.message(lambda msg: msg.text and msg.text.lower() == "поддержка")
async def support(message: types.Message):
    await message.answer(
        "➡️ Закрытая группа DS Community в Telegram\n\n1. Авторизуйтесь в корпоративном боте\n2. Вступите в группу",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )

# --- Запуск с обработкой конфликтов ---
async def main():
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    # Убедимся, что нет других запущенных экземпляров
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        pass