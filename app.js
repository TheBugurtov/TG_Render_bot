const fetch = require('node-fetch');
const { parse } = require('csv-parse/sync');
const express = require('express');

const app = express();

// --- Настройки ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const CSV_URL = 'https://raw.githubusercontent.com/TheBugurtov/Figma-components-to-Google-Sheets/main/components.csv';
const PORT = process.env.PORT || 10000;

// --- Глобальный кэш для данных CSV ---
let componentCache = null;
let lastFetchTime = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 минут кэширования

// --- Хранилище состояний пользователей ---
const state = {};

// --- Главное меню ---
const mainMenu = {
  reply_markup: {
    keyboard: [
      ['Найти компонент'],
      ['Изучить гайды', 'Предложить доработку'],
      ['Добавить иконку или логотип', 'Посмотреть последние изменения'],
      ['Поддержка']
    ],
    resize_keyboard: true,
    one_time_keyboard: false
  }
};

// --- Функция для получения данных с кэшированием ---
async function getComponentData() {
  const now = Date.now();
  
  // Если данные в кэше и не устарели
  if (componentCache && now - lastFetchTime < CACHE_TTL) {
    return componentCache;
  }
  
  try {
    // Загрузка новых данных
    const res = await fetch(CSV_URL);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    
    const csvText = await res.text();
    componentCache = parse(csvText, {
      columns: true,
      skip_empty_lines: true,
      bom: true
    });
    
    lastFetchTime = now;
    console.log('Данные CSV успешно обновлены');
    return componentCache;
  } catch (error) {
    console.error('Ошибка загрузки CSV:', error);
    
    // Возвращаем старые данные, если есть
    if (componentCache) {
      console.log('Используем кэшированные данные из-за ошибки');
      return componentCache;
    }
    
    // Если кэша нет - возвращаем пустой массив
    return [];
  }
}

// --- Функция поиска (с кэшированием) ---
async function searchComponents(query, type) {
  const records = await getComponentData();
  
  if (records.length === 0) {
    console.error('Нет данных для поиска');
    return [];
  }

  const q = (query || '').toLowerCase().trim();

  let filtered = records.filter(r => {
    // Улучшенная обработка тегов
    const tags = (r.Tags || '')
      .replace(/\s*,\s*/g, ',')   // Нормализация пробелов вокруг запятых
      .toLowerCase()
      .split(',')
      .map(t => t.trim());
    
    // Ищем точное или частичное совпадение
    return tags.some(tag => tag === q || tag.includes(q));
  });

  // Упрощенная и надежная фильтрация по типу
  if (type === 'mobile') {
    filtered = filtered.filter(r => r.File.trim() === 'App Components');
  } else if (type === 'web') {
    filtered = filtered.filter(r => r.File.trim() !== 'App Components');
  }

  return filtered.map(r => `*${r.Component}* из *${r.File}*\n${r.Link}`);
}

// --- Отправка сообщения в Telegram ---
async function sendMessage(chatId, text, extra = {}) {
  await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: 'Markdown', ...extra })
  });
}

// --- Основная обработка сообщений ---
async function handleMessage(msg) {
  if (!msg || !msg.text) return;
  const chatId = msg.chat.id;
  const text = msg.text.trim();
  const lower = text.toLowerCase();

  // --- Назад ---
  if (lower === 'назад') {
    state[chatId] = null;
    await sendMessage(chatId, `Вы в главном меню:`, mainMenu);
    return;
  }

  // --- Старт ---
  if (lower === '/start') {
    state[chatId] = null;
    await sendMessage(chatId, `Добрый день!\nЯ помощник Дизайн-системы. Постараюсь помочь в решении проблем.`, mainMenu);
    return;
  }

  // --- Найти компонент (новый флоу: выбор типа) ---
  if (lower === '/search' || lower === 'найти компонент') {
    state[chatId] = 'choose_type';
    await sendMessage(chatId, 'Выберите тип компонента:', {
      reply_markup: {
        keyboard: [['Мобильный компонент', 'Веб-компонент'], ['Назад']],
        resize_keyboard: true
      }
    });
    return;
  }

  // --- Обработка выбора типа поиска ---
  if (state[chatId] === 'choose_type') {
    if (lower === 'мобильный компонент') {
      state[chatId] = { mode: 'search', type: 'mobile' };
      await sendMessage(chatId, 'Введите название мобильного компонента для поиска:', { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } });
      return;
    }
    if (lower === 'веб-компонент') {
      state[chatId] = { mode: 'search', type: 'web' };
      await sendMessage(chatId, 'Введите название веб-компонента для поиска:', { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } });
      return;
    }
    // если в режиме выбора типа пришёл другой текст — просто игнорируем (пользователь должен выбрать кнопку)
    return;
  }

// --- Изучить гайды ---
if (lower === '/guides' || lower === 'изучить гайды') {
  state[chatId] = null;
  await sendMessage(chatId,
`Хранилище правил и рекомендаций дизайн-системы в Figma — <a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=181-20673">Granat Guides.</a>

Быстрые ссылки на материалы:

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=313-8196">Гайд по типографике</a>

<a href="https://www.figma.com/design/iqTCxAPRJJm6UlANLlYfva/Variables?node-id=48097-1187">Иерархия цвета: cветлая и темная тема</a>

Правила отрисовки <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=547-206394">интерфейсных иконок</a> и <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=23895-7907">продуктовых иконок</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=154-386">Кнопки: допустимая темизация, иерахия, расположение и пр.</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=154-385">Скелетная загрузка</a>

<a href="https://www.figma.com/design/oZGlxnWyOHTAgG6cyLkNJh/Web-Components-Molecules-2.0?node-id=141917-4145">Карточки в вебе</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=178-386">Модальные окна</a>

<a href="https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=659-70">Цветовое кодирование статусов</a>
`,
  { 
    reply_markup: { keyboard: [['Назад']], resize_keyboard: true },
    parse_mode: 'HTML'
  }
  );
  return;
}


// --- Предложить доработку ---
if (lower === '/suggest' || lower === 'предложить доработку') {
  state[chatId] = null;
  await sendMessage(chatId,
`➡️ Нашли баг в работе компонента Granat в Figma?
Заведите запрос на доработку <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">в GitLab.</a>

➡️ Есть предложение добавить новый компонент или доработать текущий?
Ознакомьтесь <a href="https://www.figma.com/design/Bew9jPI8yO0fclFUBJ22Nu/DS-Components-Process?node-id=4217-110&t=GlXxEhaJGkfzNspM-4">с блок-схемой принятия решений.</a> Если ваше предложение не носит локальную специфику, заведите запрос на доработку <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">в GitLab.</a>

Для работы с gitlab.services.mts.ru нужно включать корпоративный VPN и быть авторизованным под корпоративным логином и паролем.

🔗 Чтобы коммуникация была быстрой и эффективной, просим прикладывать прямые ссылки на все материалы, касающиеся запроса: макет до и после, best practices, исследование, скрины или видео.

⏳ Команда дизайн-системы реагирует на запрос в порядке очереди в течение 3 рабочих дней.
`,
  {
    reply_markup: { keyboard: [['Назад']], resize_keyboard: true },
    parse_mode: 'HTML'
  }
  );
  return;
}


// --- Добавить иконку или логотип ---
if (lower === '/icon' || lower === 'добавить иконку или логотип') {
  state[chatId] = null;
  await sendMessage(chatId,
`➡️ Интерфейсные иконки

Недостающие интерфейсные иконки продукт создает своими силами или нанимает подрядчика. Созданные иконки проходят ревью и согласование у дизайн лида или арт-директора продукта.
Ознакомьтесь <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">с требованиями к иконкам.</a>

Иконка нарисована?

Для создания запроса на публикацию используется <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">GitLab.</a> Прикрепите к запросу ссылку на готовый компонент.

Дизайн-система спланирует ревью компонента в спринт в соответствии с текущими приоритетами. При успешном прохождении ревью дизайнер ДС добавит иконку в библиотеку и опубликует обновление. Если иконка не соответствует гайдам, дизайнер ДС оставит фидбек в виде комментария к запросу продукта в GitLab.

➡️ Продуктовые иконки и логотипы

Продуктовые иконки для мобильных приложений создаются по <a href="https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new">экосистемному гайду.</a>
Для логотипов веб-сервисов существуют <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=29711-16375&t=DumT4AudgflUKzRs-4">компоненты-шаблоны.</a>

Любую новую иконку или логотип необходимо согласовать с Департаментом Маркетинговых Коммуникаций.

Чтобы добавить продуктовую иконку или логотип в ДС, создайте запрос <a href="https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=29711-16375&t=DumT4AudgflUKzRs-4">в GitLab.</a>
`,
  {
    reply_markup: { keyboard: [['Назад']], resize_keyboard: true },
    parse_mode: 'HTML'
  }
  );
  return;
}


  // --- Посмотреть последние изменения ---
  if (lower === '/changes' || lower === 'посмотреть последние изменения') {
    state[chatId] = null;
    await sendMessage(chatId, 'Последние изменения в DS GRANAT: https://t.me/c/1397080567/12194');
    return;
  }

// --- Поддержка ---
if (lower === '/support' || lower === 'поддержка') {
  state[chatId] = null;
  await sendMessage(chatId,
`➡️ Закрытая группа DS Community в Telegram

Добавьтесь в коммьюнити дизайн-системы в Telegram. Здесь вы сможете получать всю самую свежую информацию, новости и обновления, задавать вопросы разработчикам и дизайнерам, а также общаться с коллегами, которые используют дизайн-систему.

1. <a href="https://confluence.mts.ru/pages/viewpage.action?pageId=607687434">Авторизуйтесь в корпоративном боте</a>
2. <a href="https://t.me/+90sy0C1fFPwzNTY6">Вступите в группу DS Community</a>

Если не можете авторизоваться в корпоративном боте, <a href="https://confluence.mts.ru/pages/viewpage.action?pageId=607687434">ознакомьтесь с инструкцией.</a>

➡️ По вопросам обращайтесь на почту kuskova@mts.ru
Кускова Юлия — Design Lead МТС GRANAT
`,
  {
    reply_markup: { keyboard: [['Назад']], resize_keyboard: true },
    parse_mode: 'HTML'
  }
  );
  return;
}


  // --- Обработка поиска только в режиме search (с учётом типа) ---
  if (typeof state[chatId] === 'object' && state[chatId].mode === 'search') {
    const results = await searchComponents(text, state[chatId].type);
    if (results.length === 0) {
      await sendMessage(chatId, `Компоненты по запросу "${text}" не найдены.\nПопробуйте использовать более общий запрос, например "Кнопка", "Checkbox" и т.п.`);
    } else {
      await sendMessage(chatId, `Найдено: ${results.length}\n\n${results.join('\n\n')}`);
    }
    return;
  }

  // Если ничего не подошло — молчим (не запускаем поиск вне режима поиска)
  return;
}

// --- Пуллинг Telegram (getUpdates) ---
async function poll() {
  let offset = 0;

  while (true) {
    try {
      const res = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?timeout=30&offset=${offset}`);
      const data = await res.json();

      if (data.ok && data.result.length > 0) {
        for (const update of data.result) {
          if (update.message && update.message.text) {
            handleMessage(update.message);
            offset = update.update_id + 1;
          }
        }
      }
    } catch (err) {
      console.error('Ошибка при getUpdates:', err);
    }

    await new Promise(r => setTimeout(r, 1000));
  }
}

// --- Web Endpoint для Render ---
app.get('/', (req, res) => {
  res.send('Bot is running...');
});

app.listen(PORT, () => {
  console.log(`Bot listening on port ${PORT}`);
  poll(); // старт пуллинга после старта сервера
});