# Telegram Gaming Bank Bot

MVP Telegram-бота с игровым банком, казино, крипторынком, достижениями, анти-абьюз ограничениями и базовой системой монетизации через премиум-уровни.

## Возможности

- Игровой кошелёк, банковский счёт и депозит с автоначислением процентов
- Переводы между пользователями с комиссией и лимитами
- Казино: рулетка, слот-машина, блэкджек
- Крипторынок с динамическими курсами `BTC`, `ETH`, `TON`
- Покупка, продажа и перевод криптовалют между игроками
- Достижения, профиль игрока, таблица лидеров и блок конкурсов
- Базовая анти-чит логика: лимиты, требования к выводу и торговле
- Премиум-уровни для повышения лимитов

## Стек

- Python 3.11+
- aiogram 3
- SQLite

## Запуск

1. Установи зависимости:

```bash
pip install -r requirements.txt
```

2. Создай `.env` на основе `.env.example`.

3. Укажи токен Telegram-бота:

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_PATH=bot.db
ADMIN_IDS=123456789
```

4. Запусти приложение:

```bash
python main.py
```

## Основные команды

- `/start`
- `/help`
- `/balance`
- `/bank`
- `/depositbank <amount>`
- `/withdrawbank <amount>`
- `/opendeposit <amount>`
- `/closedeposit <amount>`
- `/transfer <user_id|@username> <amount>`
- `/daily`
- `/market`
- `/buy <symbol> <amount>`
- `/sell <symbol> <amount>`
- `/portfolio`
- `/sendcrypto <user_id|@username> <symbol> <amount>`
- `/slots <bet>`
- `/roulette <bet> <red|black|green>`
- `/blackjack <bet>`
- `/hit`
- `/stand`
- `/achievements`
- `/stats`
- `/top`
- `/contests`
- `/premium`
- `/grantpremium <user_id|@username> <level>`

## Важные замечания

- Все валюты в проекте виртуальные.
- Реальные платежи и вывод средств не подключены.
- Для реальной монетизации можно добавить Telegram Stars или внешний платёжный провайдер.
- Для production стоит вынести логику в отдельные сервисы, добавить миграции, тесты, rate limiting, аудит-логи и админ-панель.
