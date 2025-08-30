import os
import aiohttp
import asyncio
import json
import functools
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
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Rate Limiting ---
user_timestamps = {}  # username -> list of временные метки
RATE_LIMIT_COUNT = 5  # сколько сообщений можно отправлять за интервал
RATE_LIMIT_INTERVAL = 10  # интервал в секундах

def can_proceed(username: str) -> bool:
    """Проверяет, можно ли пользователю отправить новое сообщение"""
    now = time.time()
    timestamps = user_timestamps.get(username, [])
    
    # оставляем только последние сообщения в интервале
    timestamps = [t for t in timestamps if now - t < RATE_LIMIT_INTERVAL]
    
    if len(timestamps) >= RATE_LIMIT_COUNT:
        # превышен лимит
        user_timestamps[username] = timestamps  # обновляем очищенный список
        return False
    
    # добавляем новую отметку времени
    timestamps.append(now)
    user_timestamps[username] = timestamps
    return True


# --- Настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CSV_URL = "https://raw.githubusercontent.com/TheBugurtov/Figma-components-to-Google-Sheets/main/components.csv"

# Настройки Google Sheets
GOOGLE_SHEET_KEY = "1xNtFTHDf2HzzPqO4sckikDtFc8LLjArPoH0t9YLw2po"
GOOGLE_SHEET_TAB_NAME = "Logs"
GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Middleware для rate limiting ---
from aiogram import BaseMiddleware
from aiogram.types import Update
from typing import Callable, Any

HandlerType = Callable[[Update, dict], Any]

class RateLimitMiddleware(BaseMiddleware):
    async def __call__(self, handler: HandlerType, event: Update, data: dict):
        user = None

        if event.message:
            user = event.message.from_user
        elif event.callback_query:
            user = event.callback_query.from_user
        elif event.inline_query:
            user = event.inline_query.from_user
        elif event.chosen_inline_result:
            user = event.chosen_inline_result.from_user
        elif event.poll_answer:
            user = event.poll_answer.user

        if user:
            username_or_id = user.username or str(user.id)
            if not can_proceed(username_or_id):
                if event.message:
                    await event.message.answer("⏳ Слишком много запросов. Подождите немного.")
                elif event.callback_query:
                    await event.callback_query.answer(
                        "⏳ Слишком много запросов. Подождите немного.", show_alert=True
                    )
                elif event.inline_query:
                    await event.inline_query.answer([], switch_pm_text="⏳ Слишком много запросов.", switch_pm_parameter="wait")
                return

        return await handler(event, data)

# Регистрируем middleware в Dispatcher
dp.update.middleware(RateLimitMiddleware())

# --- Инициализация Google Sheets ---
def init_google_sheets():
    try:
        if not GOOGLE_SHEETS_CREDS:
            print("Google Sheets credentials not found in environment variables")
            return None
            
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        creds_dict = json.loads(GOOGLE_SHEETS_CREDS)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
    except Exception as e:
        print(f"Error initializing Google Sheets: {e}")
    return None

# --- Логирование через буфер ---
log_buffer = []
LOG_INTERVAL = 300  # 5 минут
MAX_BUFFER_SIZE = 20  # Максимальный размер буфера перед принудительной отправкой

def add_to_buffer(username: str, action: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_buffer.append([now, username, action])
    print(f"Buffered log: {username} - {action}")
    
    # Если буфер достиг максимального размера, отправляем сразу
    if len(log_buffer) >= MAX_BUFFER_SIZE:
        asyncio.create_task(flush_logs())

async def flush_logs():
    global log_buffer
    if not log_buffer:
        return

    # Создаем копию буфера и очищаем оригинал
    rows_to_write = log_buffer.copy()
    log_buffer.clear()

    loop = asyncio.get_event_loop()
    try:
        client = init_google_sheets()
        if not client:
            print("Google Sheets client not initialized")
            # Возвращаем данные в буфер если не удалось инициализировать клиент
            log_buffer.extend(rows_to_write)
            return

        sheet = await loop.run_in_executor(
            None,
            lambda: client.open_by_key(GOOGLE_SHEET_KEY).worksheet(GOOGLE_SHEET_TAB_NAME)
        )

        # Массовая запись данных
        await loop.run_in_executor(
            None,
            lambda: sheet.append_rows(rows_to_write)
        )
        
        print(f"✅ Flushed {len(rows_to_write)} logs to Google Sheets")

    except Exception as e:
        # При ошибке возвращаем данные обратно в буфер
        log_buffer.extend(rows_to_write)
        print(f"❌ Error flushing logs: {e}")

async def log_worker():
    while True:
        await asyncio.sleep(LOG_INTERVAL)
        await flush_logs()

# --- Главное меню ---
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Найти компонент")],
        [KeyboardButton(text="Изучить гайды"), KeyboardButton(text="Предложить доработку")],
        [KeyboardButton(text="Добавить иконку или логотип"), KeyboardButton(text="Посмотреть последние изменения")],
        [KeyboardButton(text="Поддержка"), KeyboardButton(text="FAQ")]
    ],
    resize_keyboard=True
)

# --- FSM ---
class SearchFlow(StatesGroup):
    choose_type = State()
    input_query = State()
    show_more = State()

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

    query = ' '.join((query or "").lower().strip().split())
    filtered = []

    for r in records:
        tags = [tag.strip() for tag in (r.get("Tags", "") or "").lower().split(",")]

        if query in tags:
            file_name = r["File"].strip()
            if type_ == "mobile" and file_name == "App Components":
                filtered.append(r)
            elif type_ == "icon" and file_name in ("Icons", "Placeholders"):
                filtered.append(r)
            elif type_ == "web" and file_name not in ("App Components", "Icons", "Placeholders"):
                filtered.append(r)

    filtered.sort(key=lambda x: x["Component"].lower())
    return filtered

async def send_large_message(chat_id: int, text: str, delay: float = 0.5):
    max_length = 4000
    parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    
    for part in parts:
        await bot.send_message(chat_id, part)
        if len(parts) > 1:
            await asyncio.sleep(delay)

# --- Обработчик для кнопки "Иконка или заглушка" ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "иконка или заглушка")
async def icon_search_direct(message: types.Message, state: FSMContext):
    username = message.from_user.username or str(message.from_user.id)
    add_to_buffer(username, "Прямой поиск иконок/заглушек")
    
    # Прямой переход к поиску иконок
    await state.update_data(type="icon")
    
    await message.answer(
        "Введите название иконки или заглушки:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(SearchFlow.input_query)

# --- Команды ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    username = message.from_user.username or str(message.from_user.id)
    add_to_buffer(username, "Start command")
    await message.answer(
        'Добрый день!\n'
        'Я помощник <a href="https://www.figma.com/files/855101281008648657/project/7717773/Library?fuid=1338884565519455641">дизайн-системы МТС GRANAT.</a>',
        reply_markup=main_menu,
        parse_mode="HTML"
    )

@dp.message(lambda msg: msg.text and msg.text.lower() == "найти компонент")
async def search_start(message: types.Message, state: FSMContext):
    add_to_buffer(message.from_user.username or str(message.from_user.id), "Начат поиск компонентов")
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мобильный компонент"), KeyboardButton(text="Веб-компонент"), KeyboardButton(text="Иконка или заглушка")],
            [KeyboardButton(text="Отмена")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите тип компонента:", reply_markup=kb)
    await state.set_state(SearchFlow.choose_type)

@dp.message(SearchFlow.choose_type)
async def type_chosen(message: types.Message, state: FSMContext):
    username = message.from_user.username or str(message.from_user.id)
    
    if message.text.lower() == "отмена":
        add_to_buffer(username, "Поиск отменен на выборе типа компонента")
        await state.clear()
        await message.answer("Поиск отменён", reply_markup=main_menu)
        return
        
    if message.text == "Мобильный компонент":
        await state.update_data(type="mobile")
        add_to_buffer(username, "Выбран поиск в мобильных компонентах")
    elif message.text == "Веб-компонент":
        await state.update_data(type="web")
        add_to_buffer(username, "Выбран поиск в веб-компонентах")
    elif message.text == "Иконка или заглушка":
        await state.update_data(type="icon")
        add_to_buffer(username, "Выбран поиск в иконках и заглушках")
    else:
        return
    
    await message.answer(
        "Введите название компонента:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(SearchFlow.input_query)

@dp.message(SearchFlow.input_query)
async def query_input(message: types.Message, state: FSMContext):
    username = message.from_user.username or str(message.from_user.id)
    
    if message.text.lower() == "отмена":
        add_to_buffer(username, "Отмена поиска, возврат в главное меню")
        await state.clear()
        await message.answer("Поиск отменён", reply_markup=main_menu)
        return

    data = await state.get_data()
    query = message.text
    add_to_buffer(username, f"Поисковой запрос: {query} (тип: {data['type']})")
    
    results = await search_components(query, data["type"])
    
    if not results:
        await message.answer(
            f'Компоненты по запросу "{query}" не найдены.',
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Отмена")]],
                resize_keyboard=True
            )
        )
        return
    
    await state.update_data(
        all_results=results,
        shown=0,
        query=query
    )
    await show_results_batch(message, state)

async def show_results_batch(message: types.Message, state: FSMContext):
    data = await state.get_data()
    results = data["all_results"]
    shown = data["shown"]
    batch_size = 10
    
    batch = results[shown:shown+batch_size]

    await message.answer(
        f"Найдено: {len(results)}. Показано {shown+1} из {min(shown+len(batch), len(results))}:"
    )

    for r in batch:
        text = f"<a href='{r['Link']}'>{r['Component']}</a> из {r['File']}"
        image_url = r.get("Image", "").replace('=IMAGE("', "").replace('")', "").strip()
        if image_url:
            try:
                await bot.send_photo(message.chat.id, photo=image_url, caption=text)
            except Exception as e:
                print("Ошибка отправки фото:", e)
                await message.answer(text)
        else:
            await message.answer(text)
    
    new_shown = shown + len(batch)
    await state.update_data(shown=new_shown)
    
    if new_shown < len(results):
        await message.answer(
            "Показать еще?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Да"), KeyboardButton(text="Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(SearchFlow.show_more)
    else:
        await message.answer(
            "Все результаты показаны.\nВведите новый запрос или нажмите 'Отмена'",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Отмена")]],
                resize_keyboard=True
            )
        )
        await state.set_state(SearchFlow.input_query)

@dp.message(SearchFlow.show_more)
async def handle_show_more(message: types.Message, state: FSMContext):
    username = message.from_user.username or str(message.from_user.id)
    
    if message.text.lower() == "да":
        add_to_buffer(username, "Запрошен показ дополнительных результатов")
        await show_results_batch(message, state)
    else:
        add_to_buffer(username, "Отказ от показа дополнительных результатов")
        await message.answer(
            "Введите новый запрос или нажмите 'Отмена'",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Отмена")]],
                resize_keyboard=True
            )
        )
        await state.set_state(SearchFlow.input_query)

# --- Изучить гайды ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "изучить гайды")
async def guides(message: types.Message):
    add_to_buffer(message.from_user.username or str(message.from_user.id), "Просмотр гайдлайнов")
    await send_large_message(message.chat.id, """
Хранилище правил и рекомендаций дизайн-системы в Figma — <a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=181-20673">Granat Guides</a>

Быстрые ссылки на материалы:

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=313-8196">🔠 Гайд по типографике</a>

<a href="https://www.figma.com/design/iqTCxAPRJJm6UlANLlYfva/Variables?node-id=48097-1187">🌓 Иерархия цвета: cветлая и темная тема</a>

✏️ Правила отрисовки <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=547-206394">интерфейсных иконок</a> и <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=23895-7907">продуктовых иконок</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=154-386">🖲️ Кнопки: допустимая темизация, иерахия, расположение и пр.</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=154-385">🦴 Скелетная загрузка</a>

<a href="https://www.figma.com/design/oZGlxnWyOHTAgG6cyLkNJh/Web-Components-Molecules-2.0?node-id=141917-4145">🪪 Карточки в вебе</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=178-386">💬 Модальные окна</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=659-70">🎨 Цветовое кодирование статусов</a>
""")

# --- Предложить доработку ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "предложить доработку")
async def suggest(message: types.Message):
    add_to_buffer(message.from_user.username or str(message.from_user.id), "Просмотр предложения доработки")
    await send_large_message(message.chat.id, """
➡️ Нашли баг в работе компонента Granat в Figma?
Заведите запрос на доработку <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">в GitLab (доступно под корпоративным VPN).</a>

➡️ Есть предложение добавить новый компонент или доработать текущий?
Ознакомьтесь <a href="https://www.figma.com/design/Bew9jPI8yO0fclFUBJ22Nu/DS-Components-Process?node-id=4217-110&t=GlXxEhaJGkfzNspM-4">с блок-схемой принятия решений.</a> Если ваше предложение не носит локальную специфику, заведите запрос на доработку <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">в GitLab (доступно под корпоративным VPN).</a>

❗️ Для работы с gitlab.services.mts.ru нужно включать корпоративный VPN и быть авторизованным под корпоративным логином и паролем.

🔗 Чтобы коммуникация была быстрой и эффективной, просим прикладывать прямые ссылки на все материалы, касающиеся запроса: макет до и после, best practices, исследование, скрины или видео.

⏳ Команда дизайн-системы реагирует на запрос в порядке очереди в течение 3 рабочих дней.
""")

# --- Добавить иконку или логотип ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "добавить иконку или логотип")
async def add_icon(message: types.Message):
    add_to_buffer(message.from_user.username or str(message.from_user.id), "Просмотр добавления иконки или логотипа")
    await send_large_message(message.chat.id, """
➡️ Интерфейсные иконки

Недостающие интерфейсные иконки продукт создает своими силами или нанимает подрядчика. Созданные иконки проходят ревью и согласование у дизайн лида или арт-директора продукта.
Ознакомьтесь <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=547-206394">с требованиями к иконкам.</a>

Иконка нарисована?

Для создания запроса на публикацию используется <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">GitLab (доступно под корпоративным VPN).</a> Прикрепите к запросу ссылку на готовый компонент.

Дизайн-система спланирует ревью компонента в спринт в соответствии с текущими приоритетами. При успешном прохождении ревью дизайнер ДС добавит иконку в библиотеку и опубликует обновление. Если иконка не соответствует гайдам, дизайнер ДС оставит фидбек в виде комментария к запросу продукта в GitLab.

➡️ Продуктовые иконки и логотипы

Продуктовые иконки для мобильных приложений создаются по <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=23895-7907">экосистемному гайду.</a>
Для логотипов веб-сервисов существуют <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=547-206394">компоненты-шаблоны.</a>

Любую новую иконку или логотип необходимо согласовать с Департаментом Маркетинговых Коммуникаций.

Чтобы добавить продуктовую иконку или логотип в ДС, создайте запрос <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">в GitLab (доступно под корпоративным VPN).</a>
""")

# --- Посмотреть последние изменения ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "посмотреть последние изменения")
async def changes(message: types.Message):
    add_to_buffer(message.from_user.username or str(message.from_user.id), "Просмотр последних изменений")
    await message.answer(
        '<a href="https://t.me/c/1397080567/12194">Последние изменения в DS GRANAT</a>\n\n'
        'Если у вас нет доступа, <a href="https://t.me/mts_guard_bot">авторизуйтесь в корпоративном боте</a>\n\n'
        'Если не можете авторизоваться в корпоративном боте, <a href="https://confluence.mts.ru/pages.viewpage.action?pageId=607687434">ознакомьтесь с инструкцией</a>',
        parse_mode="HTML"
    )

# --- Поддержка ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "поддержка")
async def support(message: types.Message):
    add_to_buffer(message.from_user.username or str(message.from_user.id), "Просмотр поддержки")
    await send_large_message(message.chat.id, """
➡️ Закрытая группа DS Community в Telegram

Добавьтесь в коммьюнити дизайн-системы в Telegram. Здесь вы сможете получать всю самую свежую информацию, новости и обновления, задавать вопросы разработчикам и дизайнерам, а также общаться с коллегами, которые используют дизайн-систему.

1. <a href="https://t.me/mts_guard_bot">Авторизуйтесь в корпоративном боте</a>
2. <a href="https://t.me/+90sy0C1fFPwzNTY6">Вступите в группу DS Community</a>

Если не можете авторизоваться в корпоративном боте, <a href="https://confluence.mts.ru/pages.viewpage.action?pageId=607687434">ознакомьтесь с инструкцией.</a>

➡️ По вопросам обращайтесь на почту kuskova@mts.ru
Кускова Юлия — Design Lead МТС GRANAT
""")
    
# --- FAQ ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "faq")
async def support(message: types.Message):
    add_to_buffer(message.from_user.username or str(message.from_user.id), "Просмотр FAQ")
    await send_large_message(message.chat.id, """
📘 Введение
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=33-146">Что такое DS GRANAT и зачем она нужна?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=29-134">Что такое базовая дизайн-система в рамках экосистемы?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2022-537">Где прочитать про дизайн-систему?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2035-1061">Что такое коммьюнити и чем оно полезно?</a>

🔑 Доступ, подключение и поддержка
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2022-528">Доступ к дизайн-системе для нового дизайнера</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2022-585">Как подключить дизайн-систему?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2035-1024">Где следить за обновлениями GRANAT?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=52-403">Как можно влиять на ДС?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2037-1126">Как тесно взаимодействовать с ДС?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2041-1289">Отправлен запрос через GitLab, а ответ не приходит. Что делать, когда ждать ответ?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2041-1344">Как давать обратную связь по библиотекам?</a>

🧩 Компоненты
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2037-1171">Какие компоненты нужно обязательно брать из дизайн-системы, а какие можно разрабатывать локально?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=33-184">Что можно менять в компонентах дизайн-системы?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=71-603">Что делать, если в спецификации компонента нет ответа на ваш вопрос?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2041-1344">Как давать обратную связь по библиотекам?</a>

🎨 Иконки</b>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=42-115">Почему нельзя копировать иконки?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=42-165">Что делать, если нет нужной иконки или нужного размера иконки?</a>

🎛️ Токены и темы
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2041-1322">Как правильно работать с токенами, чтобы корректно переключались тёмная/светлая темы?</a>
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2041-1330">Зачем в ДС токены с прозрачностью?</a>

📌 Версии
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2041-1373">Какой смысл в переходе на G2?</a>

✅ Ревью
• <a href="https://www.figma.com/design/a7UeDnUeJGZPx6AGBYpXTa/DS-GRANAT-FAQ?node-id=2042-1399">Кто проверяет на соответствие ДС?</a>
""")


# --- Тестовая команда для проверки логирования ---
@dp.message(Command("test_log"))
async def test_log(message: types.Message):
    username = message.from_user.username or str(message.from_user.id)
    add_to_buffer(username, "Test log entry")
    await message.answer("Запись добавлена в буфер логов")

# --- Запуск воркера логирования при старте ---
async def on_startup():
    # Запускаем фоновую задачу для периодической отправки логов
    asyncio.create_task(log_worker())
    print("Log worker started")

# --- Запуск ---
from fastapi import FastAPI, Request, Response
import uvicorn
from threading import Thread

app = FastAPI()

@app.middleware("http")
async def handle_head_request(request: Request, call_next):
    if request.method == "HEAD":
        return Response(status_code=200)
    return await call_next(request)

@app.get("/")
def health_check():
    return {"status": "Bot is running"}

def run_fastapi():
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        timeout_keep_alive=60,
        limit_concurrency=100
    )

async def run_bot():
    # Запускаем воркер логирования
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    fastapi_thread = Thread(
        target=run_fastapi,
        daemon=True,
        name="FastAPI Thread"
    )
    fastapi_thread.start()
    
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        # При завершении пытаемся отправить оставшиеся логи
        asyncio.run(flush_logs())
        pass
    finally:
        print("Bot stopped gracefully")