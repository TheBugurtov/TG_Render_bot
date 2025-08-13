const express = require('express');
const fetch = require('node-fetch');
const fs = require('fs');
const { parse } = require('csv-parse/sync');

const app = express();
app.use(express.json());

// --- Настройки ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const PORT = process.env.PORT || 3000;
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

// --- Webhook endpoint ---
app.post(`/${BOT_TOKEN}`, async (req, res) => {
  try {
    const msg = req.body.message;
    if (!msg || !msg.text) return res.sendStatus(200);

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

    res.sendStatus(200);
  } catch (err) {
    console.error(err);
    res.sendStatus(500);
  }
});

// --- Запуск сервера ---
app.listen(PORT, () => {
  console.log(`Bot listening on port ${PORT}`);
});