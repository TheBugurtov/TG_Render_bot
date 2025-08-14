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
async function searchComponents(query) {
  const res = await fetch(CSV_URL);
  const csvText = await res.text();

  const records = parse(csvText, {
    columns: true,
    skip_empty_lines: true
  });

  const q = query.toLowerCase();
  const found = records.filter(r => r.Tags.toLowerCase().includes(q));

  return found.map(r => `*${r.Component}* из *${r.File}*\n${r.Link}`);
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
  const chatId = msg.chat.id;
  const text = msg.text.trim();
  const lower = text.toLowerCase();

  // --- Назад ---
  if (lower === 'назад') {
    state[chatId] = null;
    await sendMessage(chatId, `Вы в главном меню:`, mainMenu);
    return;
  }

  // --- Команды или кнопки ---
  if (lower === '/start') {
    state[chatId] = null;
    await sendMessage(chatId, `Добрый день!\nЯ помощник Дизайн-системы. Постараюсь помочь в решении проблем.`, mainMenu);
    return;
  }

  if (lower === '/search' || lower === 'найти компонент') {
    state[chatId] = 'search';
    await sendMessage(chatId, 'Введите название компонента для поиска:', { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } });
    return;
  }

  if (lower === '/guides' || lower === 'изучить гайды') {
    state[chatId] = null;
    await sendMessage(chatId,
`Общий список гайдлайнов DS Granat:
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=181-20673

Color Hierarchy
https://www.figma.com/design/iqTCxAPRJJm6UlANLlYfva/Variables?node-id=48097-1187

Typography
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=313-8196

Themization
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=186-429

Buttons
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=154-386

Cards
https://www.figma.com/design/oZGlxnWyOHTAgG6cyLkNJh/Web-Components-Molecules-2.0?node-id=141917-4145

Fieldset
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=178-384

Modal
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=178-386

Skeleton
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=154-385

Statuses Color Code
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=659-70

Interface Icons
https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=547-206394

Product Icons Guide
https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=23895-7907

MTS Logos Presets
https://www.figma.com/design/a3nZmvTc8B9cZcrke9goCE/Icons?node-id=29711-16374

Selection
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=31-1794

Loading
https://www.figma.com/design/5ZYTwB6jw2wutqg60sc4Ff/Granat-Guides-WIP?node-id=181-20669`,
      { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } }
    );
    return;
  }

  if (lower === '/suggest' || lower === 'предложить доработку') {
    state[chatId] = null;
    await sendMessage(chatId,
`Вы можете предложить доработку по ссылке:
https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new`,
      { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } }
    );
    return;
  }

  if (lower === '/icon' || lower === 'добавить иконку или логотип') {
    state[chatId] = null;
    await sendMessage(chatId,
`Вы можете добавить иконку или логотип по ссылке:
https://gitlab.services.mts.ru/digital-products/design-system/support/design/-/issues/new`,
      { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } }
    );
    return;
  }

  if (lower === '/changes' || lower === 'посмотреть последние изменения') {
    state[chatId] = null;
    await sendMessage(chatId, 'Последние изменения в DS GRANAT: https://t.me/c/1397080567/12194');
    return;
  }

  if (lower === '/support' || lower === 'поддержка') {
    state[chatId] = null;
    await sendMessage(chatId,
`Если вам необходима поддержка, пишите на почту:
kuskova@mts.ru`,
      { reply_markup: { keyboard: [['Назад']], resize_keyboard: true } }
    );
    return;
  }

  // --- Обработка поиска только в режиме search ---
  if (state[chatId] === 'search') {
    const results = await searchComponents(text);
    if (results.length === 0) {
      await sendMessage(chatId, `Компоненты по запросу "${text}" не найдены.\nПопробуйте использовать более общий запрос, например "Кнопка", "Checkbox" и т.п.`);
    } else {
      await sendMessage(chatId, `Найдено: ${results.length}\n\n${results.join('\n\n')}`);
    }
    return;
  }
}

// --- Пуллинг Telegram ---
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
  poll();
});