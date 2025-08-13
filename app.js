const express = require('express');
const fetch = require('node-fetch');
const csvParse = require('csv-parse/lib/sync');
const bodyParser = require('body-parser');

const BOT_TOKEN = process.env.BOT_TOKEN;
const CSV_RAW_URL = process.env.CSV_RAW_URL;
const PORT = process.env.PORT || 3000;

if (!BOT_TOKEN || !CSV_RAW_URL) {
  console.error('ENV VARS missing: BOT_TOKEN and/or CSV_RAW_URL');
  process.exit(1);
}

const API_URL = `https://api.telegram.org/bot${BOT_TOKEN}`;
const app = express();
app.use(bodyParser.json());

let csvCache = { ts: 0, rows: [] };
const TTL = 1000 * 60 * 2;

async function loadCsv() {
  const now = Date.now();
  if (csvCache.rows.length && now - csvCache.ts < TTL) return csvCache.rows;

  const res = await fetch(CSV_RAW_URL);
  if (!res.ok) throw new Error(`CSV fetch failed: ${res.status}`);
  const text = await res.text();
  const rows = csvParse(text, { columns: true, skip_empty_lines: true });
  csvCache = { ts: now, rows };
  return rows;
}

function search(rows, query) {
  const q = query.toLowerCase();
  return rows.filter(r => 
    (r.Component || '').toLowerCase().includes(q) ||
    (r.Tags || '').toLowerCase().includes(q)
  );
}

async function sendMessage(chatId, text, keyboard) {
  const body = { chat_id: chatId, text, parse_mode: "HTML" };
  if (keyboard) body.reply_markup = keyboard;
  await fetch(`${API_URL}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

const pending = {};

app.post('/webhook', async (req, res) => {
  res.sendStatus(200);
  const msg = req.body.message;
  if (!msg) return;

  const chatId = msg.chat.id;
  const text = (msg.text || '').trim();

  if (text === '/start') {
    await sendMessage(chatId, 'Привет! Нажми кнопку, чтобы начать поиск.', {
      keyboard: [[{ text: '🔍 Найти компонент' }]],
      resize_keyboard: true
    });
    return;
  }

  if (text === '🔍 Найти компонент') {
    await sendMessage(chatId, 'Введите ключевое слово (например: иконка)');
    pending[chatId] = true;
    return;
  }

  if (pending[chatId]) {
    delete pending[chatId];
    let rows;
    try {
      rows = await loadCsv();
    } catch (error) {
      await sendMessage(chatId, 'Ошибка загрузки данных. Попробуйте позже.');
      return;
    }
    const results = search(rows, text);
    if (!results.length) {
      await sendMessage(chatId, 'Ничего не найдено 😢');
    } else {
      const lines = results.slice(0, 20).map(r =>
        `${r.Component} из ${r.File}\n${r.Link}`
      );
      await sendMessage(chatId, `Найдено ${results.length} компонент(ов):\n\n${lines.join('\n\n')}`);
    }
    return;
  }

  await sendMessage(chatId, 'Нажми "🔍 Найти компонент" или /start');
});

app.get('/', (req, res) => res.send('Bot is running.'));
app.listen(PORT, () => console.log(`Listening on port ${PORT}`));
