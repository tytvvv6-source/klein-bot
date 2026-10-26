import asyncio
import os
import aiosqlite
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, URLInputFile, PreCheckoutQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web
import threading

# ===== ЗАГРУЗКА .env =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ===== ССЫЛКИ =====
CHANNEL_LINK = "https://t.me/Kleinhvh"
REVIEWS_LINK = "https://t.me/oftencore"
OWNER_LINK = "https://t.me/oftencom"
CRYPTOBOT_LINK = "https://t.me/send?start=IVJT7NWFK0J6"

# ️ ВСТАВЬ СЮДА ПРЯМУЮ ССЫЛКУ НА ТВОЙ KLEIN.EXE ИЗ GITHUB RELEASES
KLEIN_FILE_URL = "https://github.com/tytvvv6-source/klein-bot/releases/download/v1.0/Klein.exe"
KLEIN_FILE_NAME = "Klein.exe"

# ===== СОСТОЯНИЯ (FSM) =====
class SupportStates(StatesGroup):
    category = State()
    message = State()

class GiftStates(StatesGroup):
    username = State()

class AdminStates(StatesGroup):
    waiting_for_promo_name = State()
    waiting_for_promo_uses = State()
    waiting_for_promo_days = State()
    waiting_for_ban_user_id = State()
    waiting_for_unban_user_id = State()

# ===== БАЗА ДАННЫХ =====
DB_PATH = "klein_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, has_access INTEGER DEFAULT 0,
            license_key TEXT, purchased_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY, uses_left INTEGER DEFAULT 1, duration_days INTEGER DEFAULT 0,
            created_by INTEGER, is_used INTEGER DEFAULT 0, used_by INTEGER)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS gifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gifter_id INTEGER,
            target_username TEXT,
            status TEXT DEFAULT 'pending')""")
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
        except aiosqlite.OperationalError:
            pass
            
        await db.commit()
        print("✅ База данных инициализирована")

async def add_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()

async def check_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    if user and len(user) >= 7 and user[6] == 1:
        return True
    return False

# ===== КЛАВИАТУРЫ =====
def get_main_menu(has_access: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Получить доступ", callback_data="get_access")],
        [InlineKeyboardButton(text="🎟️ Ввести промокод", callback_data="enter_promo")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🎁 Подарить", callback_data="gift")],
        [InlineKeyboardButton(text="ℹ️ О продукте", callback_data="about"),
         InlineKeyboardButton(text=" Поддержка", callback_data="support")],
    ])

def get_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

def get_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎟️ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="🚫 Забанить", callback_data="admin_ban")],
        [InlineKeyboardButton(text="✅ Разбанить", callback_data="admin_unban")],
        [InlineKeyboardButton(text="🔙 Закрыть", callback_data="admin_close")]
    ])

# ===== РОУТЕР =====
router = Router()

async def ban_middleware(handler, event, data):
    if isinstance(event, Message):
        if await check_banned(event.from_user.id):
            return
    elif isinstance(event, CallbackQuery):
        if await check_banned(event.from_user.id):
            await event.answer("Вы заблокированы администрацией.", show_alert=True)
            return
    return await handler(event, data)

router.message.middleware(ban_middleware)
router.callback_query.middleware(ban_middleware)

# ===== ПОДДЕРЖКА =====
@router.callback_query(F.data == "support")
async def support_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐞 Нашел баг", callback_data="support_bug")],
        [InlineKeyboardButton(text="💡 Предложить улучшение", callback_data="support_idea")],
        [InlineKeyboardButton(text="💬 Другой вопрос", callback_data="support_other")],
        [InlineKeyboardButton(text="️ Назад", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text("📞 **Служба поддержки KLEIN**\n\nВыберите категорию вашего обращения:", reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.in_(["support_bug", "support_idea", "support_other"]))
async def support_category_selected(callback: CallbackQuery, state: FSMContext):
    category_map = {
        "support_bug": "🐞 Баг",
        "support_idea": "💡 Предложение",
        "support_other": "💬 Другой вопрос"
    }
    await state.update_data(category=category_map[callback.data])
    await callback.message.edit_text(f"Вы выбрали: {category_map[callback.data]}\n\nОпишите вашу проблему или предложение одним сообщением:")
    await callback.answer()
    await state.set_state(SupportStates.message)

@router.message(SupportStates.message)
async def support_message_received(message: Message, state: FSMContext):
    data = await state.get_data()
    category = data.get("category", "Неизвестно")
    
    admin_text = (
        f" **Новое обращение в поддержку!**\n\n"
        f"👤 **От:** @{message.from_user.username} (ID: `{message.from_user.id}`)\n"
        f"📂 **Категория:** {category}\n"
        f"📝 **Сообщение:**\n{message.text}"
    )
    try:
        await message.bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
        await message.answer("✅ Ваше сообщение успешно отправлено администрации! Мы ответим вам в ближайшее время.", reply_markup=get_back_menu())
    except Exception:
        await message.answer("❌ Произошла ошибка при отправке. Попробуйте написать напрямую: @oftencom", reply_markup=get_back_menu())
    
    await state.clear()

# ===== ПОДАРКИ =====
@router.callback_query(F.data == "gift")
async def gift_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎁 **Система подарков KLEIN**\n\nВведите `@username` пользователя, которому вы хотите подарить доступ (например: `@oftencom`):")
    await callback.answer()
    await state.set_state(GiftStates.username)

@router.message(GiftStates.username)
async def gift_process_username(message: Message, state: FSMContext):
    target = message.text.strip().replace("@", "")
    if not target.isalnum():
        await message.answer("❌ Некорректный username. Используйте только латинские буквы и цифры (без @).")
        return
    
    await state.update_data(target_username=target)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Telegram Stars (100 ⭐)", callback_data="gift_pay_stars")],
        [InlineKeyboardButton(text="💳 CryptoBot", url=CRYPTOBOT_LINK)],
        [InlineKeyboardButton(text="️ Назад", callback_data="back_to_menu")]
    ])
    await message.answer(
        f"🎯 Получатель: **@{target}**\n\n"
        f"Стоимость подарка: **100 Stars**\n\n"
        f"Выберите способ оплаты. После оплаты доступ будет выдан получателю, а вам придет чек.",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(None)

@router.callback_query(F.data == "gift_pay_stars")
async def gift_pay_stars(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_username = data.get("target_username")
    
    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Подарок: Доступ к KLEIN",
        description=f"Подарок доступа к макросу KLEIN для пользователя @{target_username}",
        payload=f"gift:{target_username}",
        provider_token="",
        currency="XTR",
        prices=[types.LabeledPrice(label="KLEIN Gift", amount=100)],
        start_parameter="klein_gift"
    )
    await callback.message.delete()
    await callback.answer()

# ===== АВТОВЫДАЧА ФАЙЛА =====
async def deliver_product(user_id: int, username: str, is_gift: bool = False):
    license_key = f"KLEIN-GIFT-{user_id}" if is_gift else f"KLEIN-BUY-{user_id}"
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET has_access = 1, license_key = ?, purchased_at = ? WHERE user_id = ?",
            (license_key, datetime.now().isoformat(), user_id)
        )
        await db.commit()

    caption = (
        f"🎉 **Спасибо за покупку!**\n\n"
        f"Ваш доступ к KLEIN активирован.\n"
        f" Лицензия: `{license_key}`\n\n"
        f"📥 Скачайте файл ниже и запустите его:"
    ) if not is_gift else (
        f"🎁 **Вам подарили доступ к KLEIN!**\n\n"
        f"Ваш доступ активирован.\n"
        f"🔑 Лицензия: `{license_key}`\n\n"
        f"📥 Скачайте файл ниже и запустите его:"
    )

    try:
        file_to_send = URLInputFile(url=KLEIN_FILE_URL, filename=KLEIN_FILE_NAME)
        await router.bot.send_document(
            user_id, 
            document=file_to_send, 
            caption=caption, 
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка отправки файла: {e}")
        await router.bot.send_message(user_id, f"{caption}\n\n⚠️ Ошибка автовыдачи файла. Напишите в поддержку: @oftencom", parse_mode="Markdown")

@router.pre_checkout_query()
async def pre_checkout(pre_checkout: PreCheckoutQuery):
    await pre_checkout.answer(ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    
    if payload.startswith("gift:"):
        target_username = payload.split("gift:")[1]
        gifter_id = message.from_user.id
        
        await message.answer(
            f"✅ **Оплата прошла успешно!**\n\n"
            f"Вы подарили доступ пользователю **@{target_username}**.\n"
            f"Как только он запустит бота, он получит файл и доступ.",
            parse_mode="Markdown"
        )
        
        await message.bot.send_message(
            ADMIN_ID,
            f"💰 **Новый подарок!**\n"
            f"Покупатель: {message.from_user.id} (@{message.from_user.username})\n"
            f"Получатель: @{target_username}\n"
            f"Сумма: 100 Stars"
        )
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO gifts (gifter_id, target_username, status) VALUES (?, ?, 'pending')",
                (gifter_id, target_username)
            )
            await db.commit()
            
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT user_id FROM users WHERE username = ?", (target_username,))
            row = await cursor.fetchone()
            if row:
                target_id = row[0]
                await deliver_product(target_id, target_username, is_gift=True)
                await db.execute("UPDATE gifts SET status = 'claimed' WHERE target_username = ? AND status = 'pending'", (target_username,))
                await db.commit()
    else:
        await deliver_product(message.from_user.id, message.from_user.username, is_gift=False)

# ===== /start С ПРОВЕРКОЙ ПОДАРКОВ =====
@router.message(Command("start"))
async def cmd_start(message: Message):
    if await check_banned(message.from_user.id):
        await message.answer("🚫 Ваш аккаунт заблокирован администрацией.")
        return
        
    await add_user(message.from_user.id, message.from_user.username)
    user = await get_user(message.from_user.id)
    has_access = bool(user[2]) if user else False
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

    if not has_access:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id FROM gifts WHERE target_username = ? AND status = 'pending'", (message.from_user.username,))
            gift_row = await cursor.fetchone()
            if gift_row:
                await deliver_product(message.from_user.id, message.from_user.username, is_gift=True)
                await db.execute("UPDATE gifts SET status = 'claimed' WHERE id = ?", (gift_row[0],))
                await db.commit()
                has_access = True

    text = (
        f"Добро пожаловать, {username}! 👋\n\n"
        f"<b>📢 Ссылки проекта:</b>\n"
        f"• Канал: <a href='{CHANNEL_LINK}'>@Kleinhvh</a>\n"
        f"• Отзывы: <a href='{REVIEWS_LINK}'>@oftencore</a>\n"
        f"• Владелец: <a href='{OWNER_LINK}'>@oftencom</a>\n\n"
        f"<b>KLEIN</b> — профессиональный макрос-спаммер для Blade Ball.\n"
        f"Статус: {'✅ Доступ активен' if has_access else '❌ Доступ не приобретен'}"
    )

    await message.answer(text, reply_markup=get_main_menu(has_access), parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    has_access = bool(user[2]) if user else False
    text = "<b>ГЛАВНОЕ МЕНЮ</b>\n<i>KLEIN</i>\n\nВыберите действие 👇"
    await callback.message.answer(text, reply_markup=get_main_menu(has_access), parse_mode="HTML")
    try:
        await callback.message.delete()
    except:
        pass

# ===== АДМИН ПАНЕЛЬ =====
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👑 <b>АДМИН-ПАНЕЛЬ KLEIN</b>\n\nВыберите действие:", reply_markup=get_admin_menu(), parse_mode="HTML")

@router.callback_query(F.data == "admin_close")
async def admin_close(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.delete()
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB_PATH) as db:
        total_users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        paid_users = (await (await db.execute("SELECT COUNT(*) FROM users WHERE has_access = 1")).fetchone())[0]
        banned_users = (await (await db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")).fetchone())[0]
        total_promos = (await (await db.execute("SELECT COUNT(*) FROM promo_codes")).fetchone())[0]

    text = (
        f"📊 <b>Статистика бота:</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"• Всего: {total_users}\n"
        f"• Купили доступ: {paid_users}\n"
        f"• Забанено: {banned_users}\n\n"
        f"🎟️ <b>Промокоды:</b>\n"
        f"• Создано: {total_promos}"
    )
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_create_promo")
async def admin_create_promo(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.edit_text("🎟️ <b>Создание промокода</b>\n\nВведите <b>название</b> промокода (например, SALE50):", parse_mode="HTML")
    await callback.answer()
    await callback.state.set_state(AdminStates.waiting_for_promo_name)

@router.message(AdminStates.waiting_for_promo_name)
async def process_promo_name(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    promo_name = message.text.strip().upper()
    await state.update_data(promo_name=promo_name)
    await message.answer("Сколько <b>активаций</b> должен иметь этот промокод? (введите число, например, 1, 5, 10):", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_promo_uses)

@router.message(AdminStates.waiting_for_promo_uses)
async def process_promo_uses(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        uses = int(message.text.strip())
        if uses < 1:
            await message.answer("Число активаций должно быть больше 0. Попробуйте еще раз:")
            return
        await state.update_data(uses=uses)
        await message.answer("На сколько <b>дней</b> действует промокод? (введите 0, если навсегда):", parse_mode="HTML")
        await state.set_state(AdminStates.waiting_for_promo_days)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число:")

@router.message(AdminStates.waiting_for_promo_days)
async def process_promo_days(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        days = int(message.text.strip())
        if days < 0:
            await message.answer("Число дней не может быть отрицательным. Введите 0 для бессрочного действия:")
            return
        
        data = await state.get_data()
        promo_name = data['promo_name']
        uses = data['uses']
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO promo_codes (code, uses_left, duration_days, created_by) VALUES (?, ?, ?, ?)",
                (promo_name, uses, days, message.from_user.id)
            )
            await db.commit()
            
        days_text = "навсегда" if days == 0 else f"{days} дней"
        await message.answer(
            f"✅ Промокод <b>{promo_name}</b> успешно создан!\n"
            f"• Активаций: {uses}\n"
            f"• Срок действия: {days_text}",
            parse_mode="HTML",
            reply_markup=get_admin_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число дней:")

@router.callback_query(F.data == "admin_ban")
async def admin_ban(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.edit_text("🚫 <b>Блокировка пользователя</b>\n\nВведите <b>User ID</b> пользователя, которого нужно забанить:", parse_mode="HTML")
    await callback.answer()
    await callback.state.set_state(AdminStates.waiting_for_ban_user_id)

@router.message(AdminStates.waiting_for_ban_user_id)
async def process_ban(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.strip())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_id,))
            await db.commit()
        await message.answer(f"✅ Пользователь с ID <code>{target_id}</code> заблокирован.", parse_mode="HTML", reply_markup=get_admin_menu())
        await state.clear()
    except ValueError:
        await message.answer("Пожалуйста, введите корректный числовой ID:")

@router.callback_query(F.data == "admin_unban")
async def admin_unban(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.edit_text("✅ <b>Разблокировка пользователя</b>\n\nВведите <b>User ID</b> пользователя, которого нужно разбанить:", parse_mode="HTML")
    await callback.answer()
    await callback.state.set_state(AdminStates.waiting_for_unban_user_id)

@router.message(AdminStates.waiting_for_unban_user_id)
async def process_unban(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.strip())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target_id,))
            await db.commit()
        await message.answer(f"✅ Пользователь с ID <code>{target_id}</code> разблокирован.", parse_mode="HTML", reply_markup=get_admin_menu())
        await state.clear()
    except ValueError:
        await message.answer("Пожалуйста, введите корректный числовой ID:")

@router.callback_query(F.data == "get_access")
async def get_access(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    has_access = bool(user[2]) if user else False

    if has_access:
        text = f"✅ <b>У вас уже есть доступ!</b>\n\nЛицензия: <code>{user[3]}</code>"
        keyboard = get_back_menu()
    else:
        text = (
            f"🛒 <b>Покупка KLEIN</b>\n\n"
            f"<b>Товар:</b> KLEIN Macro (Доступ навсегда)\n"
            f"<b>Цена:</b> 100 ₽ / 100 Stars\n\n"
            f"Выберите способ оплаты:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 CryptoBot (Криптовалюта)", url=CRYPTOBOT_LINK)],
            [InlineKeyboardButton(text="⭐ Оплатить Telegram Stars (100 ⭐)", callback_data="pay_stars")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ])

    await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.message.delete()

@router.callback_query(F.data == "pay_stars")
async def pay_stars(callback: CallbackQuery):
    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Доступ к KLEIN",
        description="Активация доступа к макросу KLEIN через Telegram Stars",
        payload="klein_access_100",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Доступ KLEIN", amount=100)],
        start_parameter="klein_stars"
    )
    await callback.message.delete()
    await callback.answer()

@router.callback_query(F.data == "enter_promo")
async def enter_promo(callback: CallbackQuery):
    text = "🎟️ <b>Введите промокод</b>\n\nОтправьте код одним сообщением:"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.message.delete()

@router.message(F.text & ~F.text.startswith("/"))
async def process_promo(message: Message):
    promo_code = message.text.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT uses_left, duration_days FROM promo_codes WHERE code = ?", (promo_code,))
        row = await cursor.fetchone()

        if not row:
            await message.answer("❌ Промокод не найден", reply_markup=get_back_menu())
        else:
            uses_left, duration_days = row
            if uses_left <= 0:
                await message.answer("⚠️ Этот промокод больше не действителен (закончились активации)", reply_markup=get_back_menu())
            else:
                license_key = f"KLEIN-{promo_code[:4]}-{message.from_user.id}"
                purchased_at = datetime.now().isoformat()
                
                await db.execute(
                    "UPDATE users SET has_access = 1, license_key = ?, purchased_at = ? WHERE user_id = ?",
                    (license_key, purchased_at, message.from_user.id)
                )
                await db.execute(
                    "UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?",
                    (promo_code,)
                )
                await db.commit()
                
                days_text = f" (действует {duration_days} дн.)" if duration_days > 0 else ""
                await message.answer(
                    f"✅ <b>Промокод активирован!</b>{days_text}\n\n"
                    f"Лицензия: <code>{license_key}</code>",
                    reply_markup=get_back_menu(), 
                    parse_mode="HTML"
                )

@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user or not user[2]:
        text = (
            f"👤 <b>Профиль</b>\n\n"
            f"<b>Username:</b> @{callback.from_user.username}\n"
            f"<b>ID:</b> {callback.from_user.id}\n"
            f"<b>Статус:</b> ❌ Доступ не приобретен"
        )
    else:
        text = (
            f"👤 <b>Профиль</b>\n\n"
            f"<b>Username:</b> @{callback.from_user.username}\n"
            f"<b>ID:</b> {callback.from_user.id}\n"
            f"<b>Статус:</b> ✅ Доступ активен\n"
            f"<b>Лицензия:</b> <code>{user[3]}</code>"
        )
    await callback.message.answer(text, reply_markup=get_back_menu(), parse_mode="HTML")
    await callback.message.delete()

@router.callback_query(F.data == "about")
async def about(callback: CallbackQuery):
    text = (
        f"ℹ️ <b>О продукте KLEIN</b>\n\n"
        f"<b>🎯 ОБЩЕЕ ОПИСАНИЕ:</b>\n"
        f"<b>KLEIN</b> — это профессиональный программный комплекс для Blade Ball.\n\n"
        f"<b>🔥 КЛЮЧЕВЫЕ ХАРАКТЕРИСТИКИ:</b>\n"
        f"• <b>CPS до 2000</b> — без просадок и задержек\n"
        f"• <b>Режимы Toggle и Hold</b> — гибкое управление\n"
        f"• <b>Триггер-бот</b> — авто-отбивание мяча при красном свечении\n"
        f"• <b>Human-like jitter</b> — имитация движений человека\n\n"
        f"<b>⚙️ Системные требования:</b>\n"
        f"• Windows 10/11 (x64)\n\n"
        f"<b>🛡️ Безопасность:</b>\n"
        f"• Работает на уровне системы, не внедряясь в процессы игр."
    )
    await callback.message.answer(text, reply_markup=get_back_menu(), parse_mode="HTML")
    await callback.message.delete()

# ===== HTTP-СЕРВЕР ДЛЯ UPTIMEROBOT =====
async def handle_ping(request):
    return web.Response(text="Бот KLEIN работает!")

async def init_app():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    return app

def run_http_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = loop.run_until_complete(init_app())
    web.run_app(app, host='0.0.0.0', port=8080)

threading.Thread(target=run_http_server, daemon=True).start()

# ===== ЗАПУСК =====
async def main():
    print("🚀 Запуск бота...")
    await init_db()

    dp = Dispatcher()
    dp.include_router(router)

    bot = Bot(token=BOT_TOKEN)

    print("✅ БОТ ЗАПУЩЕН! Нажимай кнопки в Telegram.")
    print("=" * 60)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
