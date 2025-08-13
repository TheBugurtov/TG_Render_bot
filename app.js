const fetch = require('node-fetch');
const { parse } = require('csv-parse/sync');
const express = require('express');

const app = express();

// --- Настройки ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const CSV_URL = 'https://raw.githubusercontent.com/TheBugurtov/Figma-components-to-Google-Sheets/main/components.csv';
const PORT = process.env.PORT || 10000;

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

// --- Обработка сообщений ---
async function handleMessage(msg) {
  const chatId = msg.chat.id;
  const text = msg.text.trim();

  // Проверяем кнопки
  if (text === '/start') {
    await sendMessage(chatId, `Добрый день!\nЯ помощник Дизайн-системы. Постараюсь помочь в решении проблем.`, {
      reply_markup: {
        keyboard: [
          ['Поиск в дизайн-системе'],
          ['Отправить запрос/баг'],
          ['Посмотреть последние изменения']
        ],
        resize_keyboard: true,
        one_time_keyboard: false
      }
    });
    return;
  }

  if (text === 'Отправить запрос/баг') {
    await sendMessage(chatId, 'В разработке');
    return;
  }

  if (text === 'Посмотреть последние изменения') {
    await sendMessage(chatId, 'Ссылка на последние изменения: https://t.me/c/1397080567/12194');
    return;
  }

  if (text === 'Поиск в дизайн-системе') {
    await sendMessage(chatId, 'Что бы вы хотели найти?');
    return;
  }

  // Поиск компонентов
  const results = await searchComponents(text);

  if (results.length === 0) {
    await sendMessage(chatId, `Компоненты по запросу "${text}" не найдены`);
  } else {
    await sendMessage(chatId, `Найдено ${results.length} компонента(ов):\n\n${results.join('\n\n')}`);
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
  poll(); // старт пуллинга после старта сервера
});