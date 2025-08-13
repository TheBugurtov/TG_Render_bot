const fetch = require('node-fetch');
const { parse } = require('csv-parse/sync');
const TelegramBot = require('node-telegram-bot-api');

// --- Настройки ---
const BOT_TOKEN = process.env.BOT_TOKEN;
const CSV_URL = 'https://raw.githubusercontent.com/TheBugurtov/Figma-components-to-Google-Sheets/main/components.csv';

// --- Инициализация бота (polling) ---
const bot = new TelegramBot(BOT_TOKEN, { polling: true });
console.log('Bot started...');

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

  return found.map(
    r => `Название: ${r.Component}\nГруппа: ${r.File}\nСсылка: ${r.Link}`
  );
}

// --- Обработка сообщений ---
bot.onText(/(.+)/, async (msg, match) => {
  const chatId = msg.chat.id;
  const query = match[1].trim();

  if (!query) return;

  try {
    const results = await searchComponents(query);

    let reply = '';
    if (results.length === 0) {
      reply = `Компоненты по запросу "${query}" не найдены`;
    } else {
      reply = `Найдено ${results.length} компонента(ов):\n\n${results.join(
        '\n\n'
      )}`;
    }

    bot.sendMessage(chatId, reply);
  } catch (err) {
    console.error(err);
    bot.sendMessage(chatId, 'Произошла ошибка при поиске компонента.');
  }
});
