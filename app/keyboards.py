from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="💳 Баланс"), KeyboardButton(text="🎁 Ежедневный бонус")],
        [KeyboardButton(text="🏦 Банк"), KeyboardButton(text="💸 Платежи")],
        [KeyboardButton(text="🪙 Криптовалюта"), KeyboardButton(text="🎲 Казино")],
        [KeyboardButton(text="🏆 Достижения"), KeyboardButton(text="📊 Топ")],
        [KeyboardButton(text="ℹ️ Помощь")],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Админка")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def payments_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💸 Перевод"), KeyboardButton(text="🏦 Открыть депозит")],
            [KeyboardButton(text="🏦 Закрыть депозит"), KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def crypto_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🪙 Купить крипту"), KeyboardButton(text="💰 Продать крипту")],
            [KeyboardButton(text="📈 Рынок"), KeyboardButton(text="🧩 Портфель")],
            [KeyboardButton(text="🔁 Перевести крипту"), KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def casino_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎡 Рулетка"), KeyboardButton(text="🎰 Слоты")],
            [KeyboardButton(text="🃏 Блэкджек"), KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Начислить баланс")],
            [KeyboardButton(text="🗑 Обнулить игрока"), KeyboardButton(text="💥 Вайп всех")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)
