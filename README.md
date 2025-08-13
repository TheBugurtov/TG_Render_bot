# Telegram Bot for Figma Components

Bot reads the `components.csv` from GitHub raw URL and answers queries via Telegram webhook.

## Usage

### Environment variables
- `BOT_TOKEN` – Telegram Bot Token.
- `CSV_RAW_URL` – Raw GitHub URL to `components.csv`.

### Deployment (Render)
1. Create new **Web Service**.
2. Set build command: `npm install`
3. Start command: `npm start`
4. Add environment variables `BOT_TOKEN` and `CSV_RAW_URL`.
5. Deploy.
6. Set webhook: https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook?url=https://<YOUR_RENDER_DOMAIN>/webhook