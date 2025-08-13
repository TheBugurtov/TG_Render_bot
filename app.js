const fetch = require('node-fetch');
const { parse } = require('csv-parse/sync');

// --- Настройки ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const CSV_URL = 'https://raw.githubusercontent.com/TheBugurtov/Figma-components-to-Google-Sheets/main/components.csv';

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

// --- Функция обработки входящих сообщений ---
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

// --- Пуллинг Telegram API ---
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

    await new Promise(r => setTimeout(r, 1000)); // 1 сек задержка между запросами
  }
}

// --- Старт ---
console.log('Bot started...');
poll();