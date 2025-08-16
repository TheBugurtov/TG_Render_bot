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

async def send_large_message(chat_id: int, text: str, delay: float = 0.8):
    """Отправляет большое сообщение частями с задержкой"""
    max_length = 4000  # Лимит Telegram на одно сообщение
    parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    
    for part in parts:
        await bot.send_message(chat_id, part)
        if len(parts) > 1:  # Задержка только если сообщение разбито на части
            await asyncio.sleep(delay)

# --- Команды ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "Добрый день!\nЯ помощник Дизайн-системы. Постараюсь помочь в решении проблем.",
        reply_markup=main_menu
    )

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
    
    if not results:
        await message.answer(f'Компоненты по запросу "{message.text}" не найдены.')
        await state.clear()
        await message.answer("Вы в главном меню:", reply_markup=main_menu)
        return
    
    # Форматируем результаты
    formatted_results = [
        f"▪️ <b>{r['Component']}</b> ({r['File']})\n🔗 {r['Link']}\n"
        for r in results
    ]
    
    # Лимит на показ за раз
    MAX_ITEMS = 15
    if len(formatted_results) > MAX_ITEMS:
        first_part = "Найдено {} компонентов. Показаны первые {}:\n\n".format(
            len(formatted_results), MAX_ITEMS
        ) + "\n".join(formatted_results[:MAX_ITEMS])
        
        await send_large_message(message.chat.id, first_part)
        
        await message.answer(
            "Показать остальные?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Да"), KeyboardButton(text="Нет")]
                ],
                resize_keyboard=True
            )
        )
        await state.update_data(all_results=formatted_results, shown=MAX_ITEMS)
        await state.set_state(SearchFlow.show_more)
    else:
        full_response = "Найдено {} компонентов:\n\n".format(len(formatted_results)) + "\n".join(formatted_results)
        await send_large_message(message.chat.id, full_response)
        await state.clear()
        await message.answer("Вы в главном меню:", reply_markup=main_menu)

@dp.message(SearchFlow.show_more)
async def handle_show_more(message: types.Message, state: FSMContext):
    if message.text.lower() != "да":
        await state.clear()
        return await message.answer("Главное меню:", reply_markup=main_menu)
    
    data = await state.get_data()
    results = data["all_results"]
    shown = data["shown"]
    remaining = results[shown:]
    
    # Показываем следующие MAX_ITEMS
    next_chunk = remaining[:15]
    await send_large_message(message.chat.id, "\n".join(next_chunk))
    
    if len(remaining) > 15:
        await state.update_data(shown=shown+15)
        await message.answer(
            "Показать еще?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Да"), KeyboardButton(text="Нет")]
                ],
                resize_keyboard=True
            )
        )
    else:
        await state.clear()
        await message.answer("Все результаты показаны.", reply_markup=main_menu)

# --- Изучить гайды ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "изучить гайды")
async def guides(message: types.Message):
    guide_text = """
<b>Хранилище правил и рекомендаций дизайн-системы в Figma</b> — <a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=181-20673">Granat Guides.</a>

<b>Быстрые ссылки на материалы:</b>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=313-8196">Гайд по типографике</a>

<a href="https://www.figma.com/design/iqTCxAPRJJm6UlANLlYfva/Variables?node-id=48097-1187">Иерархия цвета: cветлая и темная тема</a>

Правила отрисовки <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=547-206394">интерфейсных иконок</a> и <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=23895-7907">продуктовых иконок</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=154-386">Кнопки: допустимая темизация, иерахия, расположение и пр.</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=154-385">Скелетная загрузка</a>

<a href="https://www.figma.com/design/oZGlxnWyOHTAgG6cyLkNJh/Web-Components-Molecules-2.0?node-id=141917-4145">Карточки в вебе</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=178-386">Модальные окна</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=659-70">Цветовое кодирование статусов</a>
"""
    await send_large_message(
        message.chat.id,
        guide_text,
        delay=0.5
    )
    await message.answer(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )

# --- Предложить доработку ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "предложить доработку")
async def suggest(message: types.Message):
    suggest_text = """
<b>➡️ Нашли баг в работе компонента Granat в Figma?</b>
Заведите запрос на доработку <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">в GitLab.</a>

<b>➡️ Есть предложение добавить новый компонент или доработать текущий?</b>
Ознакомьтесь <a href="https://www.figma.com/design/Bew9jPI8yO0fclFUBJ22Nu/DS-Components-Process?node-id=4217-110&t=GlXxEhaJGkfzNspM-4">с блок-схемой принятия решений.</a> Если ваше предложение не носит локальную специфику, заведите запрос на доработку <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">в GitLab.</a>

Для работы с gitlab.services.mts.ru нужно включать корпоративный VPN и быть авторизованным под корпоративным логином и паролем.

🔗 <b>Чтобы коммуникация была быстрой и эффективной, просим прикладывать прямые ссылки на все материалы, касающиеся запроса:</b> макет до и после, best practices, исследование, скрины или видео.

⏳ <b>Команда дизайн-системы реагирует на запрос в порядке очереди в течение 3 рабочих дней.</b>
"""
    await send_large_message(
        message.chat.id,
        suggest_text,
        delay=0.5
    )
    await message.answer(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )

# --- Добавить иконку или логотип ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "добавить иконку или логотип")
async def add_icon(message: types.Message):
    icon_text = """
<b>➡️ Интерфейсные иконки</b>

Недостающие интерфейсные иконки продукт создает своими силами или нанимает подрядчика. Созданные иконки проходят ревью и согласование у дизайн лида или арт-директора продукта.
Ознакомьтесь <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">с требованиями к иконкам.</a>

<b>Иконка нарисована?</b>

Для создания запроса на публикацию используется <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">GitLab.</a> Прикрепите к запросу ссылку на готовый компонент.

Дизайн-система спланирует ревью компонента в спринт в соответствии с текущими приоритетами. При успешном прохождении ревью дизайнер ДС добавит иконку в библиотеку и опубликует обновление. Если иконка не соответствует гайдам, дизайнер ДС оставит фидбек в виде комментария к запросу продукта в GitLab.

<b>➡️ Продуктовые иконки и логотипы</b>

Продуктовые иконки для мобильных приложений создаются по <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">экосистемному гайду.</a>
Для логотипов веб-сервисов существуют <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=29711-16375&t=DumT4AudgflUKzRs-4">компоненты-шаблоны.</a>

Любую новую иконку или логотип необходимо согласовать с Департаментом Маркетинговых Коммуникаций.

Чтобы добавить продуктовую иконку или логотип в ДС, создайте запрос <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=29711-16375&t=DumT4AudgflUKzRs-4">в GitLab.</a>
"""
    await send_large_message(
        message.chat.id,
        icon_text,
        delay=0.5
    )
    await message.answer(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )

# --- Посмотреть последние изменения ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "посмотреть последние изменения")
async def changes(message: types.Message):
    await message.answer(
        "Последние изменения в DS GRANAT: https://t.me/c/1397080567/12194",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )

# --- Поддержка ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "поддержка")
async def support(message: types.Message):
    support_text = """
<b>➡️ Закрытая группа DS Community в Telegram</b>

Добавьтесь в коммьюнити дизайн-системы в Telegram. Здесь вы сможете получать всю самую свежую информацию, новости и обновления, задавать вопросы разработчикам и дизайнерам, а также общаться с коллегами, которые используют дизайн-систему.

1. <a href="https://confluence.mts.ru/pages/viewpage.action?pageId=607687434">Авторизуйтесь в корпоративном боте</a>
2. <a href="https://t.me/+90sy0C1fFPwzNTY6">Вступите в группу DS Community</a>

Если не можете авторизоваться в корпоративном боте, <a href="https://confluence.mts.ru/pages/viewpage.action?pageId=607687434">ознакомьтесь с инструкцией.</a>

<b>➡️ По вопросам обращайтесь на почту kuskova@mts.ru</b>
Кускова Юлия — Design Lead МТС GRANAT
"""
    await send_large_message(
        message.chat.id,
        support_text,
        delay=0.5
    )
    await message.answer(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад")]],
            resize_keyboard=True
        )
    )

# --- Запуск ---
async def main():
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())