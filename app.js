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

  return found.map(r => `Название: ${r.Component}\nГруппа: ${r.File}\nСсылка: ${r.Link}`);
}

// --- Обработка сообщений ---
async function handleMessage(msg) {
  const chatId = msg.chat.id;
  const text = msg.text.trim();

  const results = await searchComponents(text);

  let reply = '';
  if (results.length === 0) {
    reply = `Компоненты по запросу "${text}" не найдены`;
  } else {
    reply = `Найдено ${results.length} компонента(ов):\n\n${results.join('\n\n')}`;
  }

  await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text: reply })
  });
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