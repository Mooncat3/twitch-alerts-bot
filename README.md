# Twitch Alerts Bot

A Telegram bot built with Python (`aiogram`) that tracks Twitch streams and sends customizable notifications. 

## Features
- **Twitch Integration**: Automatically monitors streamers and sends alerts when they go live, change categories, or update their stream title.
- **Configurable**: Configured via a SQLite/database backend.
- **Dockerized**: Easy deployment using Docker and Docker Compose.
- **Multi-language Support**: Designed to support multiple languages for user interactions.

## Prerequisites
Before you begin, ensure you have the following:
- Docker and Docker Compose installed on your machine.
- A Telegram Bot Token (obtained from [@BotFather](https://t.me/botfather)).
- Twitch API credentials (Client ID and Client Secret) from the [Twitch Developer Console](https://dev.twitch.tv/console).

## Installation and Setup

1. **Clone the repository:**
   ```bash
   git clone <your-repository-url>
   cd twitch-alerts-bot
   ```

2. **Configure Environment Variables:**
   Create a `.env` file in the `app/` directory and populate it with your necessary secrets and configurations. You may also need to configure the initial database records depending on the `models.py` structure (e.g., Bot Token and Twitch credentials).

3. **Deploy with Docker Compose:**
   Run the following command to build the image and start the container in the background:
   ```bash
   docker-compose up -d --build
   ```

4. **Data Persistence:**
   The SQLite database and logs are stored in the `app/data` folder, which is mounted as a volume in `docker-compose.yml` to ensure data persists across container restarts.

## Stack
- Python 3.12
- [aiogram](https://github.com/aiogram/aiogram) for Telegram bot interactions
- SQLAlchemy (or similar, inferred from `models.py`)
- Twitch Helix API

## License
MIT (or add your preferred license here)
