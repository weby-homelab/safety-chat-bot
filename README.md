# 🛡️ Safety-chat-bot v0.4.0

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/weby-homelab/safety-chat-bot?style=flat-square&color=blue)](https://github.com/weby-homelab/safety-chat-bot/releases)
[![Docker Pulls](https://img.shields.io/docker/pulls/webyhomelab/safety-chat-bot?style=flat-square&color=green)](https://hub.docker.com/r/webyhomelab/safety-chat-bot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square&logo=python)](https://www.python.org/)

Сучасний, легкий та повністю безкоштовний Telegram-бот для модерації та управління спільнотами. Побудований на базі **Aiogram 3** та **PostgreSQL**.

## ✨ Основні можливості

- **🛡️ Автоматична Модерація:** Швидкі евристичні фільтри миттєво видаляють спам-посилання, фішинг (наприклад, `scam.site`) та заборонені слова чи фрази.
- **👥 Авто-реєстрація:** Бот автоматично реєструє профілі для нових учасників чату при їх першій активності.
- **📢 Сповіщення Адміністратора:** Автоматичні сповіщення в окремий чат адміністратора про всі ключові події модерації (пройдена чи провалена капча, видалений спам, скарги користувачів через команду `/report`).
- **⚙️ Надійна Архітектура:** Використання SQLAlchemy 2.0, Alembic для міграцій та Docker для швидкого розгортання.

## 🏗 Архітектура

```mermaid
graph TD;
    User[Користувач Telegram] -->|Повідомлення| Bot[Safety-chat-bot]
    
    subgraph Telegram Bot
        Bot --> Middleware[DbSessionMiddleware]
        Middleware --> Router2[Messages Handler]
    end
    
    subgraph Database Layer
        Router2 --> DB[(PostgreSQL)]
        DB --> Users[Users Table]
        DB --> Chats[Chats Table]
    end
```

## 🚀 Швидкий старт (Docker)

### Запуск однією командою:
```bash
curl -sSL https://raw.githubusercontent.com/weby-homelab/safety-chat-bot/master/run.sh | bash
```
або через `wget`:
```bash
wget -qO- https://raw.githubusercontent.com/weby-homelab/safety-chat-bot/master/run.sh | bash
```

### Ручне встановлення:

1. **Клонуйте репозиторій:**
   ```bash
   git clone https://github.com/weby-homelab/safety-chat-bot.git
   cd safety-chat-bot
   ```

2. **Налаштуйте `.env`:**
   ```bash
   cp .env.example .env
   # Вкажіть ваш BOT_TOKEN, DATABASE_URL, а також TELEGRAM_BOT_TOKEN_ADMIN та TELEGRAM_CHAT_ID_ADMIN для сповіщень
   ```

3. **Запустіть:**
   ```bash
   docker compose up -d
   ```

## 🛠 Технологічний стек

- **Python 3.11+**
- **Aiogram 3.x**
- **PostgreSQL** + **SQLAlchemy 2.0**
- **Alembic**
- **Docker** & **Docker Compose**

## 📝 Важливе налаштування
Для коректної роботи антиспаму, вимкніть **Group Privacy** у @BotFather та надайте боту права адміністратора на видалення повідомлень.

##

<p align="center">
  Built in Ukraine under air raid sirens &amp; blackouts ⚡<br>
  &copy; 2026 Weby Homelab
</p>
