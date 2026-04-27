from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
import random
from typing import Iterable

from app.database import Database, now_iso


RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
ACHIEVEMENT_NAMES = {
    "first_bet": "Первый риск",
    "banker": "Банкир",
    "investor": "Инвестор",
    "whale": "Крипто-кит",
    "streak_3": "На серии",
    "high_roller": "Хайроллер",
}


class AppError(Exception):
    pass


@dataclass(frozen=True)
class Limits:
    transfer_limit: float
    bank_withdraw_limit: float
    max_bet: float
    crypto_trade_limit: float


class BotService:
    def __init__(self, db: Database, starting_balance: float, admin_ids: set[int], bot_name: str = "21БАНК") -> None:
        self.db = db
        self.starting_balance = starting_balance
        self.admin_ids = admin_ids
        self.bot_name = bot_name

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def get_bot_name(self) -> str:
        return self.bot_name

    def ensure_user(self, user_id: int, username: str | None, display_name: str) -> None:
        current_time = now_iso()
        row = self.db.fetchone("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if row is None:
            with self.db.transaction():
                self.db.execute(
                    """
                    INSERT INTO users (
                        user_id, username, display_name, wallet_balance, bank_balance,
                        deposit_balance, deposit_updated_at, premium_level, is_verified,
                        total_wagered, total_won, daily_streak, last_daily_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 0, 0, ?, 0, 0, 0, 0, 0, NULL, ?, ?)
                    """,
                    (user_id, username, display_name, self.starting_balance, current_time, current_time, current_time),
                )
                for symbol in ("BTC", "ETH", "TON"):
                    self.db.execute(
                        "INSERT INTO portfolios (user_id, symbol, amount) VALUES (?, ?, 0)",
                        (user_id, symbol),
                    )
                self._record_transaction(user_id, "signup_bonus", self.starting_balance, note="Стартовый баланс")
        else:
            self.db.execute(
                "UPDATE users SET username = ?, display_name = ?, updated_at = ? WHERE user_id = ?",
                (username, display_name, current_time, user_id),
            )

    def get_help_text(self) -> str:
        return (
            "🧭 <b>Навигация</b>\n"
            "Используй кнопки меню: Баланс, Платежи, Криптовалюта, Казино.\n\n"
            "🏦 <b>Банк</b>\n"
            "/opendeposit 100 — открыть депозит\n"
            "/closedeposit 100 — закрыть депозит\n\n"
            "💸 <b>Платежи</b>\n"
            "/transfer 123456 50 — перевод\n\n"
            "🪙 <b>Крипта</b>\n"
            "/market — рынок\n"
            "/buy BTC 250 — купить\n"
            "/sell BTC 0.01 — продать\n"
            "/sendcrypto 123456 BTC 0.005 — перевод крипты\n\n"
            "🎲 <b>Казино</b>\n"
            "/roulette 50 red\n"
            "/slots 50\n"
            "/blackjack 100\n"
            "/hit и /stand — ход в блэкджеке\n\n"
            "🏆 <b>Прогресс</b>\n"
            "/achievements — достижения\n"
            "/top — топ по капиталу\n"
            "/contests — конкурсы\n\n"
            "👥 <b>В групповом чате</b>\n"
            "Можно писать командами или короткими словами:\n"
            "• <code>/me</code> или <code>я</code> — твой баланс (счёт, депозит, крипта)\n"
            "• <code>/balance</code> — то же самое\n"
            "• <code>/top</code> — топ игроков по капиталу\n"
            "• <code>/pay @user сумма</code> или <code>перевод @user сумма</code> — перевод\n"
            "• <code>/slots 100</code> или <code>слоты 100</code> — слоты\n"
            "• <code>/roulette 50 red</code> или <code>ролл 50 red</code> — рулетка\n"
            "• <code>/daily</code> — ежедневный бонус\n"
            "• <code>/market</code> — курсы крипты\n\n"
            "⚠️ <b>Блэкджек</b> доступен только в личке с ботом."
        )

    def get_bank_overview(self, user_id: int) -> str:
        user = self._get_user(user_id)
        self._accrue_deposit(user_id)
        user = self._get_user(user_id)
        limits = self._get_limits(user)
        return (
            "🏦 <b>Игровой банк</b>\n"
            f"• Счёт: <b>{self._fmt_money(user['wallet_balance'])}</b>\n"
            f"• Депозит: <b>{self._fmt_money(user['deposit_balance'])}</b>\n"
            f"• Комиссия на перевод: <b>{self._transfer_fee_rate(user) * 100:.1f}%</b>\n"
            f"• Операции без лимитов\n"
            f"• Ставка депозита: <b>{self._deposit_rate(user) * 100:.2f}% каждые 12 часов</b>"
        )

    def get_balance_text(self, user_id: int) -> str:
        self._accrue_deposit(user_id)
        self._refresh_market()
        user = self._get_user(user_id)
        wallet = float(user["wallet_balance"])
        deposit = float(user["deposit_balance"])
        holdings = self.db.fetchall(
            """
            SELECT p.symbol, p.amount, m.price
            FROM portfolios p
            JOIN market m ON m.symbol = p.symbol
            WHERE p.user_id = ?
            ORDER BY p.symbol
            """,
            (user_id,),
        )
        portfolio_value = 0.0
        crypto_lines: list[str] = []
        for item in holdings:
            amount = float(item["amount"])
            value = amount * float(item["price"])
            portfolio_value += value
            crypto_lines.append(
                f"   — {item['symbol']}: <b>{self._fmt_crypto(amount)}</b> (<i>{self._fmt_money(value)}</i>)"
            )
        total = wallet + deposit + portfolio_value
        lines = [
            "💳 <b>Баланс</b>",
            f"• Счёт: <b>{self._fmt_money(wallet)}</b>",
            f"• Депозит: <b>{self._fmt_money(deposit)}</b>",
            f"• Криптопортфель: <b>{self._fmt_money(portfolio_value)}</b>",
        ]
        lines.extend(crypto_lines)
        lines.append(f"• Итого капитал: <b>{self._fmt_money(total)}</b>")
        return "\n".join(lines)

    def claim_daily(self, user_id: int) -> str:
        user = self._get_user(user_id)
        current_time = self._now()
        if user["last_daily_at"]:
            last_daily = self._parse_time(user["last_daily_at"])
            if current_time - last_daily < timedelta(hours=20):
                next_time = last_daily + timedelta(hours=20)
                remaining = next_time - current_time
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                raise AppError(f"Следующий бонус будет доступен через {hours}ч {minutes}м.")

        streak = user["daily_streak"] + 1
        base_reward = 200 + min(streak, 7) * 25
        reward = round(base_reward, 2)
        with self.db.transaction():
            self.db.execute(
                """
                UPDATE users
                SET wallet_balance = wallet_balance + ?, daily_streak = ?, last_daily_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (reward, streak, current_time.isoformat(), current_time.isoformat(), user_id),
            )
            self._record_transaction(user_id, "daily_bonus", reward, note=f"Серия {streak}")
        unlocked = self._check_achievements(user_id)
        text = f"Ты получил ежедневный бонус: <b>{self._fmt_money(reward)}</b>. Серия: <b>{streak}</b>."
        if unlocked:
            text += "\n\n" + self._format_unlocked(unlocked)
        return text

    def deposit_to_bank(self, user_id: int, amount: float) -> str:
        self._validate_amount(amount)
        user = self._get_user(user_id)
        if user["wallet_balance"] < amount:
            raise AppError("Недостаточно средств в кошельке.")
        with self.db.transaction():
            self.db.execute(
                """
                UPDATE users
                SET wallet_balance = wallet_balance - ?, bank_balance = bank_balance + ?, updated_at = ?
                WHERE user_id = ?
                """,
                (amount, amount, now_iso(), user_id),
            )
            self._record_transaction(user_id, "bank_deposit", amount, note="Пополнение банка")
        return f"В банк переведено <b>{self._fmt_money(amount)}</b>."

    def withdraw_from_bank(self, user_id: int, amount: float) -> str:
        self._validate_amount(amount)
        user = self._get_user(user_id)
        limits = self._get_limits(user)
        if amount > limits.bank_withdraw_limit:
            raise AppError(f"Сумма превышает лимит вывода: {self._fmt_money(limits.bank_withdraw_limit)}.")
        if user["bank_balance"] < amount:
            raise AppError("На банковском счёте недостаточно средств.")
        with self.db.transaction():
            self.db.execute(
                """
                UPDATE users
                SET bank_balance = bank_balance - ?, wallet_balance = wallet_balance + ?, updated_at = ?
                WHERE user_id = ?
                """,
                (amount, amount, now_iso(), user_id),
            )
            self._record_transaction(user_id, "bank_withdraw", amount, note="Вывод в кошелёк")
        return f"Из банка выведено <b>{self._fmt_money(amount)}</b> в игровой кошелёк."

    def open_deposit(self, user_id: int, amount: float) -> str:
        self._validate_amount(amount)
        self._accrue_deposit(user_id)
        user = self._get_user(user_id)
        if user["wallet_balance"] < amount:
            raise AppError("Недостаточно средств на счёте для открытия депозита.")
        with self.db.transaction():
            self.db.execute(
                """
                UPDATE users
                SET wallet_balance = wallet_balance - ?, deposit_balance = deposit_balance + ?, deposit_updated_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (amount, amount, now_iso(), now_iso(), user_id),
            )
            self._record_transaction(user_id, "deposit_open", amount, note="Открытие депозита")
        unlocked = self._check_achievements(user_id)
        text = f"На депозит отправлено <b>{self._fmt_money(amount)}</b>."
        if unlocked:
            text += "\n\n" + self._format_unlocked(unlocked)
        return text

    def close_deposit(self, user_id: int, amount: float) -> str:
        self._validate_amount(amount)
        self._accrue_deposit(user_id)
        user = self._get_user(user_id)
        if user["deposit_balance"] < amount:
            raise AppError("На депозите недостаточно средств.")
        with self.db.transaction():
            self.db.execute(
                """
                UPDATE users
                SET deposit_balance = deposit_balance - ?, wallet_balance = wallet_balance + ?, deposit_updated_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (amount, amount, now_iso(), now_iso(), user_id),
            )
            self._record_transaction(user_id, "deposit_close", amount, note="Закрытие части депозита")
        return f"С депозита возвращено <b>{self._fmt_money(amount)}</b> на счёт."

    def transfer_money(self, sender_id: int, recipient_ref: str, amount: float) -> str:
        self._validate_amount(amount)
        sender = self._get_user(sender_id)
        recipient = self._resolve_user(recipient_ref)
        if recipient["user_id"] == sender_id:
            raise AppError("Нельзя переводить деньги самому себе.")
        limits = self._get_limits(sender)
        if amount > limits.transfer_limit:
            raise AppError(f"Сумма превышает лимит перевода: {self._fmt_money(limits.transfer_limit)}.")
        fee = round(amount * self._transfer_fee_rate(sender), 2)
        total = amount + fee
        if sender["wallet_balance"] < total:
            raise AppError(f"Недостаточно средств. Нужно {self._fmt_money(total)} с учётом комиссии.")
        with self.db.transaction():
            self.db.execute(
                "UPDATE users SET wallet_balance = wallet_balance - ?, updated_at = ? WHERE user_id = ?",
                (total, now_iso(), sender_id),
            )
            self.db.execute(
                "UPDATE users SET wallet_balance = wallet_balance + ?, updated_at = ? WHERE user_id = ?",
                (amount, now_iso(), recipient["user_id"]),
            )
            self._record_transaction(sender_id, "transfer_out", amount, fee, f"Перевод игроку {recipient['display_name']}", recipient["user_id"])
            self._record_transaction(recipient["user_id"], "transfer_in", amount, 0.0, f"Перевод от {sender['display_name']}", sender_id)
        return (
            f"Перевод выполнен. Игрок <b>{self._safe_name(recipient)}</b> получил <b>{self._fmt_money(amount)}</b>.\n"
            f"Комиссия: <b>{self._fmt_money(fee)}</b>."
        )

    def get_market_text(self) -> str:
        rows = self._refresh_market()
        lines = ["🪙 <b>Крипторынок</b>"]
        for row in rows:
            direction = "🟢" if row["buy_pressure"] >= row["sell_pressure"] else "🔴"
            lines.append(
                f"{direction} <b>{row['symbol']}</b>: {self._fmt_money(row['price'])} | "
                f"спрос {row['buy_pressure']:.3f} / предложение {row['sell_pressure']:.3f}"
            )
        return "\n".join(lines)

    def buy_crypto(self, user_id: int, symbol: str, amount_money: float) -> str:
        self._validate_amount(amount_money)
        user = self._get_user(user_id)
        limits = self._get_limits(user)
        if amount_money > limits.crypto_trade_limit:
            raise AppError(f"Сумма сделки превышает лимит: {self._fmt_money(limits.crypto_trade_limit)}.")
        market = self._get_market_symbol(symbol)
        if user["wallet_balance"] < amount_money:
            raise AppError("Недостаточно средств в кошельке.")
        amount_asset = round(amount_money / market["price"], 8)
        if amount_asset <= 0:
            raise AppError("Слишком маленькая сумма для покупки.")
        with self.db.transaction():
            self.db.execute(
                "UPDATE users SET wallet_balance = wallet_balance - ?, updated_at = ? WHERE user_id = ?",
                (amount_money, now_iso(), user_id),
            )
            self.db.execute(
                "UPDATE portfolios SET amount = amount + ? WHERE user_id = ? AND symbol = ?",
                (amount_asset, user_id, market["symbol"]),
            )
            self.db.execute(
                "UPDATE market SET buy_pressure = buy_pressure + ?, updated_at = ? WHERE symbol = ?",
                (amount_asset, now_iso(), market["symbol"]),
            )
            self._record_transaction(user_id, "crypto_buy", amount_money, note=f"Покупка {amount_asset:.8f} {market['symbol']}", asset=market["symbol"])
        unlocked = self._check_achievements(user_id)
        text = f"Куплено <b>{amount_asset:.8f} {market['symbol']}</b> за <b>{self._fmt_money(amount_money)}</b>."
        if unlocked:
            text += "\n\n" + self._format_unlocked(unlocked)
        return text

    def sell_crypto(self, user_id: int, symbol: str, amount_asset: float) -> str:
        self._validate_amount(amount_asset)
        self._refresh_market()
        market = self._get_market_symbol(symbol)
        holding = self.db.fetchone(
            "SELECT amount FROM portfolios WHERE user_id = ? AND symbol = ?",
            (user_id, market["symbol"]),
        )
        if holding is None or holding["amount"] < amount_asset:
            raise AppError("Недостаточно криптовалюты для продажи.")
        amount_money = round(amount_asset * market["price"], 2)
        with self.db.transaction():
            self.db.execute(
                "UPDATE portfolios SET amount = amount - ? WHERE user_id = ? AND symbol = ?",
                (amount_asset, user_id, market["symbol"]),
            )
            self.db.execute(
                "UPDATE users SET wallet_balance = wallet_balance + ?, updated_at = ? WHERE user_id = ?",
                (amount_money, now_iso(), user_id),
            )
            self.db.execute(
                "UPDATE market SET sell_pressure = sell_pressure + ?, updated_at = ? WHERE symbol = ?",
                (amount_asset, now_iso(), market["symbol"]),
            )
            self._record_transaction(user_id, "crypto_sell", amount_money, note=f"Продажа {amount_asset:.8f} {market['symbol']}", asset=market["symbol"])
        return f"Продано <b>{amount_asset:.8f} {market['symbol']}</b> за <b>{self._fmt_money(amount_money)}</b>."

    def send_crypto(self, sender_id: int, recipient_ref: str, symbol: str, amount_asset: float) -> str:
        self._validate_amount(amount_asset)
        sender = self._get_user(sender_id)
        recipient = self._resolve_user(recipient_ref)
        if recipient["user_id"] == sender_id:
            raise AppError("Нельзя отправлять крипту самому себе.")
        asset_symbol = symbol.upper()
        market = self._get_market_symbol(asset_symbol)
        amount_row = self.db.fetchone(
            "SELECT amount FROM portfolios WHERE user_id = ? AND symbol = ?",
            (sender_id, asset_symbol),
        )
        if amount_row is None or amount_row["amount"] < amount_asset:
            raise AppError("Недостаточно криптовалюты на балансе.")
        limits = self._get_limits(sender)
        transfer_value = amount_asset * market["price"]
        if transfer_value > limits.crypto_trade_limit:
            raise AppError(f"Стоимость перевода превышает лимит: {self._fmt_money(limits.crypto_trade_limit)}.")
        fee_asset = round(amount_asset * 0.01, 8)
        total_asset = amount_asset + fee_asset
        if amount_row["amount"] < total_asset:
            raise AppError(f"Нужно {total_asset:.8f} {asset_symbol} с учётом комиссии 1%.")
        with self.db.transaction():
            self.db.execute(
                "UPDATE portfolios SET amount = amount - ? WHERE user_id = ? AND symbol = ?",
                (total_asset, sender_id, asset_symbol),
            )
            self.db.execute(
                "UPDATE portfolios SET amount = amount + ? WHERE user_id = ? AND symbol = ?",
                (amount_asset, recipient["user_id"], asset_symbol),
            )
            self._record_transaction(sender_id, "crypto_transfer_out", amount_asset, note=f"Перевод {asset_symbol} игроку {recipient['display_name']}", asset=asset_symbol, counterparty_id=recipient["user_id"])
            self._record_transaction(recipient["user_id"], "crypto_transfer_in", amount_asset, note=f"Получено {asset_symbol} от {sender['display_name']}", asset=asset_symbol, counterparty_id=sender_id)
        return f"Отправлено <b>{amount_asset:.8f} {asset_symbol}</b> игроку <b>{self._safe_name(recipient)}</b>."

    def get_portfolio_text(self, user_id: int) -> str:
        self._refresh_market()
        holdings = self.db.fetchall(
            """
            SELECT p.symbol, p.amount, m.price
            FROM portfolios p
            JOIN market m ON m.symbol = p.symbol
            WHERE p.user_id = ?
            ORDER BY p.symbol
            """,
            (user_id,),
        )
        total = 0.0
        lines = ["🧩 <b>Криптопортфель</b>"]
        for item in holdings:
            value = item["amount"] * item["price"]
            total += value
            lines.append(f"• {item['symbol']}: {item['amount']:.8f} ≈ {self._fmt_money(value)}")
        lines.append(f"• Итого: <b>{self._fmt_money(total)}</b>")
        return "\n".join(lines)

    def play_slots(self, user_id: int, bet: float) -> str:
        self._validate_bet(user_id, bet)
        symbols = ["🍒", "🍋", "🍀", "💎", "7️⃣"]
        roll = [random.choice(symbols) for _ in range(3)]
        reward = 0.0
        if len(set(roll)) == 1:
            multipliers = {"🍒": 3, "🍋": 3.5, "🍀": 4, "💎": 6, "7️⃣": 10}
            reward = bet * multipliers[roll[0]]
        result = self._settle_game(user_id, bet, reward, "slots", f"{' '.join(roll)}")
        return (
            f"🎰 <b>{' '.join(roll)}</b>\n"
            f"{result}"
        )

    def play_roulette(self, user_id: int, bet: float, choice: str) -> str:
        self._validate_bet(user_id, bet)
        normalized_choice = choice.lower()
        color_map = {"ред": "red", "красный": "red", "блэк": "black", "чёрный": "black", "черный": "black", "грин": "green", "зелёный": "green", "зеленый": "green"}
        normalized_choice = color_map.get(normalized_choice, normalized_choice)
        if normalized_choice not in {"red", "black", "green"}:
            raise AppError("Выбор должен быть red, black или green (или ред, блэк, грин).")
        number = random.randint(0, 36)
        if number == 0:
            outcome = "green"
        elif number in RED_NUMBERS:
            outcome = "red"
        else:
            outcome = "black"
        multiplier = 0
        if normalized_choice == outcome:
            multiplier = 14 if outcome == "green" else 2
        reward = bet * multiplier
        result = self._settle_game(user_id, bet, reward, "roulette", f"Выпало {number} ({outcome})")
        return f"Рулетка: выпало <b>{number}</b> ({outcome}).\n{result}"

    def start_blackjack(self, user_id: int, bet: float) -> str:
        self._validate_bet(user_id, bet)
        existing = self.db.fetchone("SELECT user_id FROM blackjack_sessions WHERE user_id = ?", (user_id,))
        if existing:
            raise AppError("У тебя уже есть активная партия. Напиши 'еще' или 'пас'.")
        deck = self._draw_hand(2)
        dealer = self._draw_hand(2)
        with self.db.transaction():
            self._debit_wallet(user_id, bet)
            self.db.execute(
                "UPDATE users SET total_wagered = total_wagered + ?, updated_at = ? WHERE user_id = ?",
                (bet, now_iso(), user_id),
            )
            self.db.execute(
                """
                INSERT INTO blackjack_sessions (user_id, bet, player_hand, dealer_hand, status, created_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (user_id, bet, json.dumps(deck), json.dumps(dealer), now_iso()),
            )
            self._record_transaction(user_id, "blackjack_bet", bet, note="Начало партии")
        if self._score(deck) == 21:
            return self.blackjack_stand(user_id)
        return self._blackjack_state_text(deck, dealer, hide_dealer=True, extra="Партия началась. Жми «Ещё» или «Хватит».")

    def blackjack_hit(self, user_id: int) -> str:
        session = self._get_blackjack_session(user_id)
        player_hand = json.loads(session["player_hand"])
        dealer_hand = json.loads(session["dealer_hand"])
        player_hand.append(self._draw_card())
        player_score = self._score(player_hand)
        if player_score > 21:
            with self.db.transaction():
                self.db.execute("DELETE FROM blackjack_sessions WHERE user_id = ?", (user_id,))
            unlocked = self._check_achievements(user_id)
            text = self._blackjack_state_text(player_hand, dealer_hand, hide_dealer=False, extra="Перебор. Ставка проиграна.")
            if unlocked:
                text += "\n\n" + self._format_unlocked(unlocked)
            return text
        self.db.execute(
            "UPDATE blackjack_sessions SET player_hand = ? WHERE user_id = ?",
            (json.dumps(player_hand), user_id),
        )
        return self._blackjack_state_text(player_hand, dealer_hand, hide_dealer=True, extra="Карточка взята. Жми «Ещё» или «Хватит».")

    def blackjack_stand(self, user_id: int) -> str:
        session = self._get_blackjack_session(user_id)
        player_hand = json.loads(session["player_hand"])
        dealer_hand = json.loads(session["dealer_hand"])
        bet = session["bet"]
        while self._score(dealer_hand) < 17:
            dealer_hand.append(self._draw_card())
        player_score = self._score(player_hand)
        dealer_score = self._score(dealer_hand)
        if dealer_score > 21 or player_score > dealer_score:
            reward = bet * (2.5 if player_score == 21 and len(player_hand) == 2 else 2)
            extra = f"Ты победил и получил {self._fmt_money(reward)}."
        elif player_score == dealer_score:
            reward = bet
            extra = "Ничья. Ставка возвращена."
        else:
            reward = 0.0
            extra = "Дилер победил. Ставка проиграна."
        with self.db.transaction():
            if reward > 0:
                self.db.execute(
                    "UPDATE users SET wallet_balance = wallet_balance + ?, total_won = total_won + ?, updated_at = ? WHERE user_id = ?",
                    (reward, reward, now_iso(), user_id),
                )
            self.db.execute("DELETE FROM blackjack_sessions WHERE user_id = ?", (user_id,))
            self._record_transaction(user_id, "blackjack_result", reward, note=extra)
        unlocked = self._check_achievements(user_id)
        text = self._blackjack_state_text(player_hand, dealer_hand, hide_dealer=False, extra=extra)
        if unlocked:
            text += "\n\n" + self._format_unlocked(unlocked)
        return text

    def get_achievements_text(self, user_id: int) -> str:
        unlocked = self.db.fetchall(
            "SELECT code, unlocked_at FROM achievements WHERE user_id = ? ORDER BY unlocked_at",
            (user_id,),
        )
        if not unlocked:
            return "Пока достижений нет. Играй, инвестируй и развивай банк, чтобы открыть первые награды."
        lines = ["<b>Достижения</b>"]
        for item in unlocked:
            lines.append(f"🏆 {ACHIEVEMENT_NAMES.get(item['code'], item['code'])} — {item['unlocked_at'][:10]}")
        return "\n".join(lines)

    def get_stats_text(self, user_id: int) -> str:
        return self.get_balance_text(user_id)

    def get_leaderboard_text(self) -> str:
        self._refresh_market()
        users = self.db.fetchall(
            "SELECT user_id, display_name, wallet_balance, deposit_balance FROM users"
        )
        ranked = []
        for user in users:
            total = user["wallet_balance"] + user["deposit_balance"] + self._portfolio_value(user["user_id"])
            ranked.append((total, user["display_name"]))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked:
            return "Пока в таблице лидеров пусто."
        lines = ["🏆 <b>Топ игроков по капиталу</b>"]
        for index, (capital, name) in enumerate(ranked[:10], start=1):
            lines.append(f"{index}. {name} — <b>{self._fmt_money(capital)}</b>")
        return "\n".join(lines)

    def get_contests_text(self) -> str:
        users = self.db.fetchall(
            "SELECT display_name, total_won, daily_streak FROM users ORDER BY total_won DESC LIMIT 5"
        )
        if not users:
            return "Конкурсы появятся, когда в проекте появятся первые игроки."
        lines = [
            "🎯 <b>Конкурсы и турниры</b>",
            "Еженедельный турнир: лидеры по суммарным выигрышам.",
        ]
        for index, user in enumerate(users, start=1):
            lines.append(
                f"{index}. {user['display_name']} — выиграно {self._fmt_money(user['total_won'])}, серия бонусов {user['daily_streak']}"
            )
        lines.append("Награды можно выдавать вручную администраторам или автоматически в будущих обновлениях.")
        return "\n".join(lines)

    def get_premium_text(self, user_id: int) -> str:
        return "Премиум временно отключён."

    def grant_premium(self, admin_id: int, recipient_ref: str, level: int) -> str:
        raise AppError("Премиум временно отключён.")

    def grant_balance(self, admin_id: int, recipient_ref: str, amount: float) -> str:
        if admin_id not in self.admin_ids:
            raise AppError("Только администратор может начислять баланс.")
        self._validate_amount(amount)
        recipient = self._resolve_user(recipient_ref)
        with self.db.transaction():
            self.db.execute(
                "UPDATE users SET wallet_balance = wallet_balance + ?, updated_at = ? WHERE user_id = ?",
                (amount, now_iso(), recipient["user_id"]),
            )
            self._record_transaction(recipient["user_id"], "admin_credit", amount, note=f"Начислено админом {admin_id}")
        return f"Игроку <b>{self._safe_name(recipient)}</b> начислено <b>{self._fmt_money(amount)}</b>."

    def reset_player_assets(self, admin_id: int, recipient_ref: str) -> str:
        if admin_id not in self.admin_ids:
            raise AppError("Только администратор может обнулять имущество.")
        recipient = self._resolve_user(recipient_ref)
        with self.db.transaction():
            self.db.execute(
                "UPDATE users SET wallet_balance = 0, deposit_balance = 0, updated_at = ? WHERE user_id = ?",
                (now_iso(), recipient["user_id"]),
            )
            self.db.execute(
                "UPDATE portfolios SET amount = 0 WHERE user_id = ?",
                (recipient["user_id"],),
            )
            self._record_transaction(recipient["user_id"], "admin_reset", 0, note=f"Обнулено админом {admin_id}")
        return f"Имущество игрока <b>{self._safe_name(recipient)}</b> полностью обнулено."

    def wipe_all_players(self, admin_id: int) -> str:
        if admin_id not in self.admin_ids:
            raise AppError("Только администратор может проводить вайп.")
        with self.db.transaction():
            self.db.execute("UPDATE users SET wallet_balance = 0, deposit_balance = 0, updated_at = ?", (now_iso(),))
            self.db.execute("UPDATE portfolios SET amount = 0")
            self._record_transaction(admin_id, "admin_wipe", 0, note="Глобальный вайп")
        return "💥 Глобальный вайп проведён. Имущество всех игроков обнулено."

    def _settle_game(self, user_id: int, bet: float, reward: float, kind: str, note: str) -> str:
        unlocked: list[str] = []
        with self.db.transaction():
            self._debit_wallet(user_id, bet)
            self.db.execute(
                "UPDATE users SET total_wagered = total_wagered + ?, updated_at = ? WHERE user_id = ?",
                (bet, now_iso(), user_id),
            )
            if reward > 0:
                self.db.execute(
                    "UPDATE users SET wallet_balance = wallet_balance + ?, total_won = total_won + ?, updated_at = ? WHERE user_id = ?",
                    (reward, reward, now_iso(), user_id),
                )
            self._record_transaction(user_id, f"{kind}_result", reward - bet, note=note)
        unlocked = self._check_achievements(user_id)
        if reward > 0:
            result = f"Победа. Выплата: <b>{self._fmt_money(reward)}</b>."
        else:
            result = "Не повезло. Ставка проиграна."
        if unlocked:
            result += "\n\n" + self._format_unlocked(unlocked)
        return result

    def _debit_wallet(self, user_id: int, amount: float) -> None:
        user = self._get_user(user_id)
        if user["wallet_balance"] < amount:
            raise AppError("Недостаточно средств в кошельке для этой операции.")
        self.db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ?, updated_at = ? WHERE user_id = ?",
            (amount, now_iso(), user_id),
        )

    def _validate_bet(self, user_id: int, bet: float) -> None:
        self._validate_amount(bet)
        user = self._get_user(user_id)
        limits = self._get_limits(user)
        if bet > limits.max_bet:
            raise AppError(f"Ставка превышает лимит: {self._fmt_money(limits.max_bet)}.")

    def _get_user(self, user_id: int):
        row = self.db.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if row is None:
            raise AppError("Пользователь не найден. Используй /start для инициализации аккаунта.")
        return row

    def _resolve_user(self, reference: str):
        ref = reference.strip()
        if not ref:
            raise AppError("Не указан получатель.")
        if ref.startswith("@"):
            username = ref[1:].lower()
            row = self.db.fetchone("SELECT * FROM users WHERE lower(username) = ?", (username,))
        else:
            try:
                row = self.db.fetchone("SELECT * FROM users WHERE user_id = ?", (int(ref),))
            except ValueError as exc:
                raise AppError("Получателя нужно указывать через numeric user_id или @username.") from exc
        if row is None:
            raise AppError("Получатель не найден. Он должен хотя бы один раз запустить бота.")
        return row

    def _record_transaction(
        self,
        user_id: int,
        kind: str,
        amount: float,
        fee: float = 0.0,
        note: str | None = None,
        counterparty_id: int | None = None,
        asset: str | None = None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO transactions (user_id, counterparty_id, kind, asset, amount, fee, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, counterparty_id, kind, asset, round(amount, 8), round(fee, 8), note, now_iso()),
        )

    def _refresh_market(self):
        rows = self.db.fetchall("SELECT * FROM market ORDER BY symbol")
        current_time = self._now()
        updated_rows = []
        for row in rows:
            previous_time = self._parse_time(row["updated_at"])
            elapsed_hours = max((current_time - previous_time).total_seconds() / 3600, 0.0)
            if elapsed_hours > 0.02:
                pressure = (row["buy_pressure"] - row["sell_pressure"]) / max(row["circulating_supply"], 1.0)
                deviation = (row["price"] - ((row["floor_price"] + row["ceiling_price"]) / 2)) / max(row["ceiling_price"], 1.0)
                drift = random.uniform(-row["volatility"], row["volatility"]) * math.sqrt(min(elapsed_hours, 6.0))
                mean_reversion = -0.03 * deviation
                pressure_effect = pressure * 0.45
                new_price = row["price"] * (1 + drift + mean_reversion + pressure_effect)
                new_price = max(row["floor_price"], min(row["ceiling_price"], new_price))
                new_buy = max(0.0, row["buy_pressure"] * (0.72 ** elapsed_hours))
                new_sell = max(0.0, row["sell_pressure"] * (0.72 ** elapsed_hours))
                self.db.execute(
                    """
                    UPDATE market
                    SET price = ?, buy_pressure = ?, sell_pressure = ?, updated_at = ?
                    WHERE symbol = ?
                    """,
                    (round(new_price, 6), round(new_buy, 6), round(new_sell, 6), current_time.isoformat(), row["symbol"]),
                )
                row = self.db.fetchone("SELECT * FROM market WHERE symbol = ?", (row["symbol"],))
            updated_rows.append(row)
        return updated_rows

    def _get_market_symbol(self, symbol: str):
        self._refresh_market()
        row = self.db.fetchone("SELECT * FROM market WHERE symbol = ?", (symbol.upper(),))
        if row is None:
            raise AppError("Неизвестный тикер. Доступно: BTC, ETH, TON.")
        return row

    def _portfolio_value(self, user_id: int) -> float:
        rows = self.db.fetchall(
            """
            SELECT p.amount, m.price
            FROM portfolios p
            JOIN market m ON m.symbol = p.symbol
            WHERE p.user_id = ?
            """,
            (user_id,),
        )
        return round(sum(item["amount"] * item["price"] for item in rows), 2)

    def _deposit_rate(self, user) -> float:
        return 0.015 + user["premium_level"] * 0.0025

    def _accrue_deposit(self, user_id: int) -> None:
        user = self._get_user(user_id)
        balance = user["deposit_balance"]
        if balance <= 0:
            return
        updated_at = self._parse_time(user["deposit_updated_at"])
        current_time = self._now()
        elapsed_hours = max((current_time - updated_at).total_seconds() / 3600, 0.0)
        periods = int(elapsed_hours // 12)
        if periods <= 0:
            return
        new_balance = balance * ((1 + self._deposit_rate(user)) ** periods)
        new_timestamp = updated_at + timedelta(hours=12 * periods)
        self.db.execute(
            "UPDATE users SET deposit_balance = ?, deposit_updated_at = ?, updated_at = ? WHERE user_id = ?",
            (round(new_balance, 2), new_timestamp.isoformat(), current_time.isoformat(), user_id),
        )

    def _check_achievements(self, user_id: int) -> list[str]:
        self._refresh_market()
        self._accrue_deposit(user_id)
        user = self._get_user(user_id)
        crypto_value = self._portfolio_value(user_id)
        total_capital = user["wallet_balance"] + user["deposit_balance"] + crypto_value
        conditions = {
            "first_bet": user["total_wagered"] >= 50,
            "banker": user["deposit_balance"] >= 1000,
            "investor": crypto_value >= 1000,
            "whale": crypto_value >= 5000,
            "streak_3": user["daily_streak"] >= 3,
            "high_roller": user["total_wagered"] >= 5000 or total_capital >= 20000,
        }
        unlocked = []
        with self.db.transaction():
            for code, condition in conditions.items():
                if not condition:
                    continue
                exists = self.db.fetchone(
                    "SELECT 1 FROM achievements WHERE user_id = ? AND code = ?",
                    (user_id, code),
                )
                if exists:
                    continue
                self.db.execute(
                    "INSERT INTO achievements (user_id, code, unlocked_at) VALUES (?, ?, ?)",
                    (user_id, code, now_iso()),
                )
                unlocked.append(ACHIEVEMENT_NAMES.get(code, code))
        return unlocked

    def _format_unlocked(self, names: Iterable[str]) -> str:
        lines = ["<b>Новые достижения</b>"]
        for name in names:
            lines.append(f"🏆 {name}")
        return "\n".join(lines)

    def _get_limits(self, user) -> Limits:
        base_transfer = 1_000_000_000.0
        base_withdraw = 1_000_000_000.0
        base_bet = 1_000_000_000.0
        base_trade = 1_000_000_000.0
        return Limits(
            transfer_limit=round(base_transfer, 2),
            bank_withdraw_limit=round(base_withdraw, 2),
            max_bet=round(base_bet, 2),
            crypto_trade_limit=round(base_trade, 2),
        )

    def _transfer_fee_rate(self, user) -> float:
        return 0.02

    def has_blackjack_session(self, user_id: int) -> bool:
        return self.db.fetchone("SELECT 1 FROM blackjack_sessions WHERE user_id = ?", (user_id,)) is not None

    def _get_blackjack_session(self, user_id: int):
        session = self.db.fetchone("SELECT * FROM blackjack_sessions WHERE user_id = ?", (user_id,))
        if session is None:
            raise AppError("У тебя нет активной партии. Запусти /blackjack (или 'бж 100').")
        return session

    def _draw_card(self) -> str:
        deck = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        return random.choice(deck)

    def _draw_hand(self, count: int) -> list[str]:
        return [self._draw_card() for _ in range(count)]

    def _score(self, hand: list[str]) -> int:
        score = 0
        aces = 0
        for card in hand:
            if card == "A":
                score += 11
                aces += 1
            elif card in {"J", "Q", "K"}:
                score += 10
            else:
                score += int(card)
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    def _blackjack_state_text(self, player_hand: list[str], dealer_hand: list[str], hide_dealer: bool, extra: str) -> str:
        dealer_view = dealer_hand[:1] + ["?"] if hide_dealer else dealer_hand
        dealer_score = "?" if hide_dealer else str(self._score(dealer_hand))
        return (
            "<b>Блэкджек</b>\n"
            f"Твои карты: {' '.join(player_hand)} | очки: <b>{self._score(player_hand)}</b>\n"
            f"Карты дилера: {' '.join(dealer_view)} | очки: <b>{dealer_score}</b>\n"
            f"{extra}"
        )

    def _validate_amount(self, amount: float) -> None:
        if amount <= 0:
            raise AppError("Сумма должна быть больше нуля.")
        if amount > 1_000_000_000:
            raise AppError("Слишком большая сумма.")

    def _fmt_money(self, amount: float) -> str:
        return f"{amount:,.2f}".replace(",", " ")

    def _fmt_crypto(self, amount: float) -> str:
        text = f"{amount:.8f}".rstrip("0").rstrip(".")
        return text or "0"

    def _safe_name(self, user) -> str:
        return user["display_name"] or user["username"] or str(user["user_id"])

    def _parse_time(self, value: str) -> datetime:
        return datetime.fromisoformat(value)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
