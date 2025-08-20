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

# --- Инициализация Google Sheets ---
def init_google_sheets():
    try:
        if not GOOGLE_SHEETS_CREDS:
            print("Google Sheets credentials not found in environment variables")
            return None
            
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        # Используем json.loads вместо eval для безопасности
        creds_dict = json.loads(GOOGLE_SHEETS_CREDS)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
    except Exception as e:
        print(f"Error initializing Google Sheets: {e}")
    return None

# --- Логирование в Google Sheets (асинхронное) ---
async def log_action(username: str, action: str):
    loop = asyncio.get_event_loop()
    try:
        client = init_google_sheets()
        if not client:
            print("Google Sheets client not initialized")
            return False
            
        # Выносим синхронные операции в отдельный поток
        sheet = await loop.run_in_executor(
            None,
            lambda: client.open_by_key(GOOGLE_SHEET_KEY).worksheet(GOOGLE_SHEET_TAB_NAME)
        )
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, username, action]
        
        # Асинхронное добавление строки
        await loop.run_in_executor(
            None,
            lambda: sheet.append_row(row)
        )
        
        print(f"Successfully logged action: {username} - {action}")
        return True
    except Exception as e:
        print(f"Error logging action to Google Sheets: {e}")
        return False

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

# --- Команды ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    print("LOG DEBUG:", message.text)
    await log_action(message.from_user.username or str(message.from_user.id), "Start command")
    await message.answer(
        'Добрый день!\n'
        'Я помощник <a href="https://www.figma.com/files/855101281008648657/project/7717773/Library?fuid=1338884565519455641">дизайн-системы МТС GRANAT.</a>',
        reply_markup=main_menu,
        parse_mode="HTML"
    )

@dp.message(lambda msg: msg.text and msg.text.lower() == "найти компонент")
async def search_start(message: types.Message, state: FSMContext):
    print("LOG DEBUG:", message.text)
    await log_action(message.from_user.username or str(message.from_user.id), "Начат поиск компонентов")
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мобильный компонент"), KeyboardButton(text="Веб-компонент"), KeyboardButton(text="Иконка или Заглушка")],
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
        print("LOG DEBUG:", message.text)
        await log_action(username, "Поиск отменен на выборе типа компонента")
        await state.clear()
        await message.answer("Поиск отменён", reply_markup=main_menu)
        return
        
    if message.text == "Мобильный компонент":
        await state.update_data(type="mobile")
        print("LOG DEBUG:", message.text)
        await log_action(username, "Выбран поиск в мобильных компонентах")
    elif message.text == "Веб-компонент":
        await state.update_data(type="web")
        print("LOG DEBUG:", message.text)
        await log_action(username, "Выбран поиск в веб-компонентах")
    elif message.text == "Иконка":
        await state.update_data(type="icon")
        print("LOG DEBUG:", message.text)
        await log_action(username, "Выбран поиск в иконках")
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
        print("LOG DEBUG:", message.text)
        await log_action(username, "Отмена поиска, возврат в главное меню")
        await state.clear()
        await message.answer("Поиск отменён", reply_markup=main_menu)
        return

    data = await state.get_data()
    query = message.text
    print("LOG DEBUG:", message.text)
    await log_action(username, f"Поисковой запрос: {query} (тип: {data['type']})")
    
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
        print("LOG DEBUG:", message.text)
        await log_action(username, "Запрошен показ дополнительных результатов")
        await show_results_batch(message, state)
    else:
        print("LOG DEBUG:", message.text)
        await log_action(username, "Отказ от показа дополнительных результатов")
        await message.answer(
            f"Введите новый запрос или нажмите 'Отмена'",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Отмена")]],
                resize_keyboard=True
            )
        )
        await state.set_state(SearchFlow.input_query)

# --- Изучить гайды ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "изучить гайды")
async def guides(message: types.Message):
    print("LOG DEBUG:", message.text)
    await log_action(message.from_user.username or str(message.from_user.id), "Просмотр гайдлайнов")
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
    print("LOG DEBUG:", message.text)
    await log_action(message.from_user.username or str(message.from_user.id), "Просмотр предложения доработки")
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
    print("LOG DEBUG:", message.text)
    await log_action(message.from_user.username or str(message.from_user.id), "Просмотр добавления иконки или логотипа")
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
    print("LOG DEBUG:", message.text)
    await log_action(message.from_user.username or str(message.from_user.id), "Просмотр последних изменений")
    await message.answer(
        '<a href="https://t.me/c/1397080567/12194">Последние изменения в DS GRANAT</a>\n\n'
        'Если у вас нет доступа, <a href="https://t.me/mts_guard_bot">авторизуйтесь в корпоративном боте</a>\n\n'
        'Если не можете авторизоваться в корпоративном боте, <a href="https://confluence.mts.ru/pages/viewpage.action?pageId=607687434">ознакомьтесь с инструкцией</a>',
        parse_mode="HTML"
    )

# --- Поддержка ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "поддержка")
async def support(message: types.Message):
    print("LOG DEBUG:", message.text)
    await log_action(message.from_user.username or str(message.from_user.id), "Просмотр поддержки")
    await send_large_message(message.chat.id, """
➡️ Закрытая группа DS Community в Telegram

Добавьтесь в коммьюнити дизайн-системы в Telegram. Здесь вы сможете получать всю самую свежую информацию, новости и обновления, задавать вопросы разработчикам и дизайнерам, а также общаться с коллегами, которые используют дизайн-систему.

1. <a href="https://t.me/mts_guard_bot">Авторизуйтесь в корпоративном боте</a>
2. <a href="https://t.me/+90sy0C1fFPwzNTY6">Вступите в группу DS Community</a>

Если не можете авторизоваться в корпоративном боте, <a href="https://confluence.mts.ru/pages/viewpage.action?pageId=607687434">ознакомьтесь с инструкцией.</a>

➡️ По вопросам обращайтесь на почту kuskova@mts.ru
Кускова Юлия — Design Lead МТС GRANAT
""")

# --- Тестовая команда для проверки логирования ---
@dp.message(Command("test_log"))
async def test_log(message: types.Message):
    print("Received /test_log command")  # Логируем получение команды
    username = message.from_user.username or str(message.from_user.id)
    print(f"Trying to log action for user: {username}")
    
    success = await log_action(username, "Test log entry")
    if success:
        print("Log successful")
        await message.answer("Запись в таблицу добавлена успешно")
    else:
        print("Log failed")
        await message.answer("Ошибка записи в таблицу. Проверьте логи сервера.")

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
        pass
    finally:
        print("Bot stopped gracefully")