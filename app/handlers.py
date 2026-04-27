from __future__ import annotations

import logging
from inspect import isawaitable
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, Message

from app.config import BASE_DIR

from app.keyboards import (
    admin_keyboard,
    back_keyboard,
    casino_keyboard,
    crypto_keyboard,
    main_keyboard,
    payments_keyboard,
)
from app.service import AppError, BotService


class PaymentStates(StatesGroup):
    transfer = State()
    open_deposit = State()
    close_deposit = State()


class CryptoStates(StatesGroup):
    buy = State()
    sell = State()
    send = State()


class CasinoStates(StatesGroup):
    roulette = State()
    slots = State()
    blackjack = State()


class AdminStates(StatesGroup):
    grant_balance = State()
    reset_assets = State()
    wipe_all = State()


def create_router(service: BotService) -> Router:
    router = Router()

    async def ensure_user(message: Message) -> None:
        user = message.from_user
        if user is None:
            raise AppError("Не удалось определить пользователя Telegram.")
        service.ensure_user(
            user_id=user.id,
            username=user.username,
            display_name=user.full_name,
        )

    async def reply(message: Message, text: str, keyboard=None) -> None:
        is_private = message.chat.type == "private"
        if is_private:
            markup = keyboard
            if markup is None and message.from_user:
                markup = main_keyboard(service.is_admin(message.from_user.id))
        else:
            markup = None
        await message.answer(text, parse_mode="HTML", reply_markup=markup)

    async def execute(message: Message, action: Callable[[], str | Awaitable[str]], keyboard=None) -> None:
        try:
            await ensure_user(message)
            result = action()
            text = await result if isawaitable(result) else result
            await reply(message, text, keyboard=keyboard)
        except AppError as error:
            await reply(message, f"<b>Ошибка</b>\n{error}", keyboard=keyboard)
        except Exception:
            await reply(
                message,
                "<b>Ошибка</b>\nПроизошёл внутренний сбой. Проверь логи приложения.",
                keyboard=keyboard,
            )
            raise

    async def show_menu(message: Message, text: str, keyboard) -> None:
        await execute(message, lambda: text, keyboard=keyboard)

    def split_args(message: Message) -> list[str]:
        return (message.text or "").split()[1:]

    def parse_amount(raw: str) -> float:
        try:
            return float(raw.replace(",", "."))
        except ValueError as exc:
            raise AppError("Не удалось разобрать число.") from exc

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        try:
            await ensure_user(message)
            text = (
                f"<b>{service.get_bot_name()}</b> — игровой банк нового поколения\n"
                "Храни валюту, переводи её друзьям, играй в казино и торгуй криптой.\n\n"
                f"{service.get_balance_text(message.from_user.id)}\n\n"
                "Нажми кнопку <b>💸 Платежи</b> или <b>🪙 Криптовалюта</b> в меню, чтобы начать."
            )
            is_private = message.chat.type == "private"
            markup = main_keyboard(service.is_admin(message.from_user.id)) if is_private and message.from_user else None
            photo_path = BASE_DIR / "start.png"
            if photo_path.is_file():
                try:
                    if len(text) <= 1024:
                        await message.answer_photo(
                            photo=FSInputFile(str(photo_path)),
                            caption=text,
                            parse_mode="HTML",
                            reply_markup=markup,
                        )
                    else:
                        await message.answer_photo(photo=FSInputFile(str(photo_path)))
                        await message.answer(text, parse_mode="HTML", reply_markup=markup)
                    return
                except Exception:
                    logger.exception("Failed to send start.png from %s, falling back to text", photo_path)
            else:
                logger.warning("start.png not found at %s", photo_path)
            await message.answer(text, parse_mode="HTML", reply_markup=markup)
        except AppError as error:
            await reply(message, f"<b>Ошибка</b>\n{error}")
        except Exception:
            await reply(
                message,
                "<b>Ошибка</b>\nПроизошёл внутренний сбой. Проверь логи приложения.",
            )
            raise

    @router.message(Command("help"))
    @router.message(F.text == "ℹ️ Помощь")
    async def help_command(message: Message) -> None:
        await execute(message, service.get_help_text)

    @router.message(Command("balance"))
    @router.message(F.text == "💳 Баланс")
    async def balance_command(message: Message) -> None:
        await execute(message, lambda: service.get_balance_text(message.from_user.id))

    @router.message(Command("bank"))
    @router.message(F.text == "🏦 Банк")
    async def bank_command(message: Message) -> None:
        await execute(message, lambda: service.get_bank_overview(message.from_user.id))

    @router.message(Command("daily"))
    @router.message(F.text == "🎁 Ежедневный бонус")
    async def daily_command(message: Message) -> None:
        await execute(message, lambda: service.claim_daily(message.from_user.id))

    @router.message(Command("opendeposit"))
    async def opendeposit_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 1:
                raise AppError("Формат: /opendeposit сумма")
            return service.open_deposit(message.from_user.id, parse_amount(args[0]))

        await execute(message, action)

    @router.message(Command("closedeposit"))
    async def closedeposit_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 1:
                raise AppError("Формат: /closedeposit сумма")
            return service.close_deposit(message.from_user.id, parse_amount(args[0]))

        await execute(message, action)

    @router.message(Command("transfer"))
    async def transfer_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 2:
                raise AppError("Формат: /transfer user_id/@username сумма")
            return service.transfer_money(message.from_user.id, args[0], parse_amount(args[1]))

        await execute(message, action)

    @router.message(Command("market"))
    @router.message(F.text == "📈 Рынок")
    async def market_command(message: Message) -> None:
        await execute(message, service.get_market_text, keyboard=crypto_keyboard())

    @router.message(Command("buy"))
    async def buy_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 2:
                raise AppError("Формат: /buy тикер сумма")
            return service.buy_crypto(message.from_user.id, args[0], parse_amount(args[1]))

        await execute(message, action)

    @router.message(Command("sell"))
    async def sell_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 2:
                raise AppError("Формат: /sell тикер количество")
            return service.sell_crypto(message.from_user.id, args[0], parse_amount(args[1]))

        await execute(message, action)

    @router.message(Command("portfolio"))
    @router.message(F.text == "🧩 Портфель")
    async def portfolio_command(message: Message) -> None:
        await execute(message, lambda: service.get_portfolio_text(message.from_user.id), keyboard=crypto_keyboard())

    @router.message(Command("sendcrypto"))
    async def sendcrypto_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 3:
                raise AppError("Формат: /sendcrypto user_id/@username тикер количество")
            return service.send_crypto(message.from_user.id, args[0], args[1], parse_amount(args[2]))

        await execute(message, action)

    @router.message(Command("slots"))
    @router.message(F.text.lower().startswith("слоты "))
    async def slots_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 1:
                raise AppError("Формат: /slots ставка")
            return service.play_slots(message.from_user.id, parse_amount(args[0]))

        await execute(message, action)

    @router.message(Command("roulette"))
    @router.message(F.text.lower().startswith("ролл "))
    async def roulette_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 2:
                raise AppError("Формат: /roulette ставка red|black|green")
            return service.play_roulette(message.from_user.id, parse_amount(args[0]), args[1])

        await execute(message, action)

    @router.message(Command("blackjack"))
    @router.message(F.text.lower().startswith("бж "))
    async def blackjack_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 1:
                raise AppError("Формат: /blackjack ставка")
            return service.start_blackjack(message.from_user.id, parse_amount(args[0]))

        await execute(message, action)

    @router.message(Command("hit"))
    @router.message(F.text.lower().in_({"еще", "ещё", "хит"}))
    async def hit_command(message: Message) -> None:
        await execute(message, lambda: service.blackjack_hit(message.from_user.id))

    @router.message(Command("stand"))
    @router.message(F.text.lower().in_({"хватит", "пас", "стенд", "стэнд"}))
    async def stand_command(message: Message) -> None:
        await execute(message, lambda: service.blackjack_stand(message.from_user.id))

    @router.message(Command("achievements"))
    @router.message(F.text == "🏆 Достижения")
    async def achievements_command(message: Message) -> None:
        await execute(message, lambda: service.get_achievements_text(message.from_user.id))

    @router.message(Command("stats"))
    async def stats_command(message: Message) -> None:
        await execute(message, lambda: service.get_stats_text(message.from_user.id))

    @router.message(Command("me"))
    @router.message(F.text.lower() == "я")
    async def me_command(message: Message) -> None:
        await execute(message, lambda: service.get_stats_text(message.from_user.id))

    @router.message(Command("pay"))
    @router.message(F.text.lower().startswith("перевод "))
    async def pay_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 2:
                raise AppError("Формат: /pay @username сумма")
            return service.transfer_money(message.from_user.id, args[0].lstrip("@") if args[0].startswith("@") else args[0], parse_amount(args[1]))

        await execute(message, action)

    @router.message(Command("top"))
    @router.message(F.text == "📊 Топ")
    async def top_command(message: Message) -> None:
        await execute(message, service.get_leaderboard_text)

    @router.message(Command("contests"))
    async def contests_command(message: Message) -> None:
        await execute(message, service.get_contests_text)

    @router.message(Command("premium"))
    async def premium_command(message: Message) -> None:
        await execute(message, lambda: "Премиум временно отключён.")

    @router.message(Command("grantbalance"))
    async def grantbalance_command(message: Message) -> None:
        async def action() -> str:
            args = split_args(message)
            if len(args) != 2:
                raise AppError("Формат: /grantbalance user_id/@username сумма")
            return service.grant_balance(message.from_user.id, args[0], parse_amount(args[1]))

        await execute(message, action)

    @router.message(F.text == "🎲 Казино")
    async def casino_button(message: Message) -> None:
        await show_menu(
            message,
            "<b>Казино 21БАНК</b>\nВыбери игру и введи ставку.",
            casino_keyboard(),
        )

    @router.message(F.text == "💸 Платежи")
    async def payments_button(message: Message) -> None:
        await show_menu(
            message,
            "<b>Платежи</b>\nПереводы и депозиты.",
            payments_keyboard(),
        )

    @router.message(F.text == "🪙 Криптовалюта")
    async def crypto_button(message: Message) -> None:
        await show_menu(
            message,
            "<b>Криптовалюта</b>\nРынок, покупки и продажи.",
            crypto_keyboard(),
        )

    @router.message(F.text == "🛠 Админка")
    async def admin_button(message: Message) -> None:
        async def action() -> str:
            if not message.from_user or not service.is_admin(message.from_user.id):
                raise AppError("Админ-панель доступна только администраторам.")
            return "<b>Админ-панель</b>\nДоступ к управлению балансами и премиумом."

        await execute(message, action, keyboard=admin_keyboard())

    @router.message(F.text == "⬅️ Назад")
    async def back_button(message: Message, state: FSMContext) -> None:
        await state.clear()
        await execute(message, lambda: "Ты в главном меню.")

    @router.message(F.text == "💸 Перевод")
    async def payment_transfer(message: Message, state: FSMContext) -> None:
        await state.set_state(PaymentStates.transfer)
        await show_menu(
            message,
            "Введи перевод в формате: <b>user_id сумма</b> или <b>@username сумма</b>.",
            back_keyboard(),
        )

    @router.message(PaymentStates.transfer)
    async def payment_transfer_apply(message: Message, state: FSMContext) -> None:
        async def action() -> str:
            args = (message.text or "").split()
            if len(args) != 2:
                raise AppError("Формат: user_id сумма")
            return service.transfer_money(message.from_user.id, args[0], parse_amount(args[1]))

        await execute(message, action, keyboard=payments_keyboard())
        await state.clear()

    @router.message(F.text == "🏦 Открыть депозит")
    async def payment_open_deposit(message: Message, state: FSMContext) -> None:
        await state.set_state(PaymentStates.open_deposit)
        await show_menu(message, "Введи сумму депозита:", back_keyboard())

    @router.message(PaymentStates.open_deposit)
    async def payment_open_deposit_apply(message: Message, state: FSMContext) -> None:
        await execute(
            message,
            lambda: service.open_deposit(message.from_user.id, parse_amount(message.text or "")),
            keyboard=payments_keyboard(),
        )
        await state.clear()

    @router.message(F.text == "🏦 Закрыть депозит")
    async def payment_close_deposit(message: Message, state: FSMContext) -> None:
        await state.set_state(PaymentStates.close_deposit)
        await show_menu(message, "Введи сумму закрытия депозита:", back_keyboard())

    @router.message(PaymentStates.close_deposit)
    async def payment_close_deposit_apply(message: Message, state: FSMContext) -> None:
        await execute(
            message,
            lambda: service.close_deposit(message.from_user.id, parse_amount(message.text or "")),
            keyboard=payments_keyboard(),
        )
        await state.clear()

    @router.message(F.text == "🪙 Купить крипту")
    async def crypto_buy(message: Message, state: FSMContext) -> None:
        await state.set_state(CryptoStates.buy)
        await execute(
            message,
            lambda: (
                "<b>Покупка крипты</b>\n"
                "Шаг 1: посмотри рынок ниже.\n"
                "Шаг 2: отправь покупку в формате <b>BTC сумма</b>.\n\n"
                f"{service.get_market_text()}"
            ),
            keyboard=back_keyboard(),
        )

    @router.message(CryptoStates.buy)
    async def crypto_buy_apply(message: Message, state: FSMContext) -> None:
        async def action() -> str:
            args = (message.text or "").split()
            if len(args) != 2:
                raise AppError("Формат: BTC сумма")
            return service.buy_crypto(message.from_user.id, args[0], parse_amount(args[1]))

        await execute(message, action, keyboard=crypto_keyboard())
        await state.clear()

    @router.message(F.text == "💰 Продать крипту")
    async def crypto_sell(message: Message, state: FSMContext) -> None:
        await state.set_state(CryptoStates.sell)
        await show_menu(message, "Введи продажу: <b>BTC количество</b>.", back_keyboard())

    @router.message(CryptoStates.sell)
    async def crypto_sell_apply(message: Message, state: FSMContext) -> None:
        async def action() -> str:
            args = (message.text or "").split()
            if len(args) != 2:
                raise AppError("Формат: BTC количество")
            return service.sell_crypto(message.from_user.id, args[0], parse_amount(args[1]))

        await execute(message, action, keyboard=crypto_keyboard())
        await state.clear()

    @router.message(F.text == "🔁 Перевести крипту")
    async def crypto_send(message: Message, state: FSMContext) -> None:
        await state.set_state(CryptoStates.send)
        await show_menu(message, "Введи перевод: <b>user_id BTC количество</b>.", back_keyboard())

    @router.message(CryptoStates.send)
    async def crypto_send_apply(message: Message, state: FSMContext) -> None:
        async def action() -> str:
            args = (message.text or "").split()
            if len(args) != 3:
                raise AppError("Формат: user_id BTC количество")
            return service.send_crypto(message.from_user.id, args[0], args[1], parse_amount(args[2]))

        await execute(message, action, keyboard=crypto_keyboard())
        await state.clear()

    @router.message(F.text == "🎡 Рулетка")
    async def casino_roulette(message: Message, state: FSMContext) -> None:
        await state.set_state(CasinoStates.roulette)
        await show_menu(message, "Введи ставку и цвет: <b>50 red</b>.", back_keyboard())

    @router.message(CasinoStates.roulette)
    async def casino_roulette_apply(message: Message, state: FSMContext) -> None:
        async def action() -> str:
            args = (message.text or "").split()
            if len(args) != 2:
                raise AppError("Формат: ставка red|black|green")
            return service.play_roulette(message.from_user.id, parse_amount(args[0]), args[1])

        await execute(message, action, keyboard=casino_keyboard())
        await state.clear()

    @router.message(F.text == "🎰 Слоты")
    async def casino_slots(message: Message, state: FSMContext) -> None:
        await state.set_state(CasinoStates.slots)
        await show_menu(message, "Введи ставку для слотов:", back_keyboard())

    @router.message(CasinoStates.slots)
    async def casino_slots_apply(message: Message, state: FSMContext) -> None:
        await execute(
            message,
            lambda: service.play_slots(message.from_user.id, parse_amount(message.text or "")),
            keyboard=casino_keyboard(),
        )
        await state.clear()

    @router.message(F.text == "🃏 Блэкджек")
    async def casino_blackjack(message: Message, state: FSMContext) -> None:
        await state.set_state(CasinoStates.blackjack)
        await show_menu(message, "Введи ставку для блэкджека:", back_keyboard())

    @router.message(CasinoStates.blackjack)
    async def casino_blackjack_apply(message: Message, state: FSMContext) -> None:
        await execute(
            message,
            lambda: service.start_blackjack(message.from_user.id, parse_amount(message.text or "")),
            keyboard=casino_keyboard(),
        )
        await state.clear()

    @router.message(F.text == "➕ Начислить баланс")
    async def admin_grant_balance(message: Message, state: FSMContext) -> None:
        await state.set_state(AdminStates.grant_balance)
        await show_menu(message, "Введи: <b>@username/user_id сумма</b>", back_keyboard())

    @router.message(AdminStates.grant_balance)
    async def admin_grant_balance_apply(message: Message, state: FSMContext) -> None:
        async def action() -> str:
            args = (message.text or "").split()
            if len(args) != 2:
                raise AppError("Формат: @username/user_id сумма")
            return service.grant_balance(message.from_user.id, args[0], parse_amount(args[1]))

        await execute(message, action, keyboard=admin_keyboard())
        await state.clear()

    @router.message(F.text == "🗑 Обнулить игрока")
    async def admin_reset_assets(message: Message, state: FSMContext) -> None:
        await state.set_state(AdminStates.reset_assets)
        await show_menu(message, "Введи <b>@username</b> или <b>user_id</b> игрока для обнуления:", back_keyboard())

    @router.message(AdminStates.reset_assets)
    async def admin_reset_assets_apply(message: Message, state: FSMContext) -> None:
        async def action() -> str:
            ref = (message.text or "").strip()
            if not ref:
                raise AppError("Введи @username или user_id")
            return service.reset_player_assets(message.from_user.id, ref)

        await execute(message, action, keyboard=admin_keyboard())
        await state.clear()

    @router.message(F.text == "💥 Вайп всех")
    async def admin_wipe_all(message: Message, state: FSMContext) -> None:
        await state.set_state(AdminStates.wipe_all)
        await show_menu(message, "⚠️ Это обнулит имущество ВСЕХ игроков!\nНапиши <b>подтверждаю</b> для продолжения.", back_keyboard())

    @router.message(AdminStates.wipe_all)
    async def admin_wipe_all_apply(message: Message, state: FSMContext) -> None:
        async def action() -> str:
            if (message.text or "").lower().strip() != "подтверждаю":
                raise AppError("Операция отменена. Напиши 'подтверждаю'.")
            return service.wipe_all_players(message.from_user.id)

        await execute(message, action, keyboard=admin_keyboard())
        await state.clear()

    @router.message()
    async def fallback(message: Message) -> None:
        if message.chat.type != "private":
            return
        await execute(
            message,
            lambda: (
                "Не понял сообщение. Используй кнопки меню или /help для списка команд."
            ),
        )

    return router
