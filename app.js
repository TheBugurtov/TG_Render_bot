const fetch = require('node-fetch');
const { parse } = require('csv-parse/sync');
const express = require('express');

const app = express();

// --- Настройки ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const CSV_URL = 'https://raw.githubusercontent.com/TheBugurtov/Figma-components-to-Google-Sheets/main/components.csv';
const PORT = process.env.PORT || 10000;

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

// --- Функция поиска ---
// Теперь принимает второй параметр type: 'mobile' | 'web' | undefined
async function searchComponents(query, type) {
  const res = await fetch(CSV_URL);
  const csvText = await res.text();

  const records = parse(csvText, {
    columns: true,
    skip_empty_lines: true
  });

  const q = (query || '').toLowerCase();

  // Изначальная фильтрация по Tags (как было)
  let filtered = records.filter(r => {
    const tags = (r.Tags || '').toLowerCase();
    return tags.includes(q);
  });

  // Применяем дополнительный фильтр по типу
  if (type === 'mobile') {
    filtered = filtered.filter(r => r.File === 'App Components');
  } else if (type === 'web') {
    filtered = filtered.filter(r => r.File !== 'App Components');
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
`Вы можете предложить доработку по ссылке:
https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new`,
      { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } }
    );
    return;
  }

  // --- Добавить иконку или логотип ---
  if (lower === '/icon' || lower === 'добавить иконку или логотип') {
    state[chatId] = null;
    await sendMessage(chatId,
`Вы можете добавить иконку или логотип по ссылке:
https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new`,
      { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } }
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
`Если вам необходима поддержка, пишите на почту kuskova@mts.ru`,
      { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } }
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