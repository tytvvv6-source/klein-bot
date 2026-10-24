import asyncio
import os
import aiosqlite
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiohttp import web

# ===== ЗАГРУЗКА .env =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ===== ССЫЛКИ =====
CHANNEL_LINK = "https://t.me/Kleinhvh"
REVIEWS_LINK = "https://t.me/oftencore"
OWNER_LINK = "https://t.me/oftencom"

# ===== БАЗА ДАННЫХ =====
DB_PATH = "klein_bot.db"

# ===== АДМИН-ПАНЕЛЬ =====
admin_states = {}

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, has_access INTEGER DEFAULT 0,
            license_key TEXT, purchased_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY, is_used INTEGER DEFAULT 0, used_by INTEGER)""")
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

# ===== КЛАВИАТУРЫ =====
def get_main_menu(has_access: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Получить доступ", callback_data="get_access")],
        [InlineKeyboardButton(text="🎟️ Ввести промокод", callback_data="enter_promo")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🎁 Подарить", callback_data="gift")],
        [InlineKeyboardButton(text="️ О продукте", callback_data="about"),
         InlineKeyboardButton(text="📞 Поддержка", callback_data="support")],
    ])

def get_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

def get_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Закрыть", callback_data="admin_close")]
    ])

# ===== РОУТЕР =====
router = Router()

# --- АДМИН-ПАНЕЛЬ ---
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        " <b>АДМИН-ПАНЕЛЬ KLEIN</b>\n\nВыберите действие:",
        reply_markup=get_admin_menu(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_close")
async def admin_close(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.delete()
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB_PATH) as db:
        total_users = await db.execute("SELECT COUNT(*) FROM users")
        total_users = (await total_users.fetchone())[0]
        paid_users = await db.execute("SELECT COUNT(*) FROM users WHERE has_access = 1")
        paid_users = (await paid_users.fetchone())[0]
        total_promos = await db.execute("SELECT COUNT(*) FROM promo_codes")
        total_promos = (await total_promos.fetchone())[0]
        used_promos = await db.execute("SELECT COUNT(*) FROM promo_codes WHERE is_used = 1")
        used_promos = (await used_promos.fetchone())[0]

    text = (
        f"📊 <b>Статистика бота:</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"• Всего: {total_users}\n"
        f"• Купили доступ: {paid_users}\n\n"
        f"🎟️ <b>Промокоды:</b>\n"
        f"• Создано: {total_promos}\n"
        f"• Активировано: {used_promos}"
    )
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_create_promo")
async def admin_create_promo(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    admin_states[callback.from_user.id] = 'waiting_for_promo'
    await callback.message.edit_text(
        "➕ <b>Создание промокода</b>\n\nОтправьте название промокода:",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    admin_states[callback.from_user.id] = 'waiting_for_broadcast'
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\nОтправьте текст для рассылки:",
        parse_mode="HTML"
    )
    await callback.answer()

# --- ОСНОВНЫЕ ХЕНДЛЕРЫ ---
@router.message(Command("start"))
async def cmd_start(message: Message):
    await add_user(message.from_user.id, message.from_user.username)
    user = await get_user(message.from_user.id)
    has_access = bool(user[2]) if user else False
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

    text = (
        f"Добро пожаловать, {username}! 👋\n\n"
        f"<b>📢 Ссылки проекта:</b>\n"
        f"• Канал: <a href='{CHANNEL_LINK}'>@Kleinhvh</a>\n"
        f"• Отзывы: <a href='{REVIEWS_LINK}'>@oftencore</a>\n"
        f"• Владелец: <a href='{OWNER_LINK}'>@oftencom</a>\n\n"
        f"<b>KLEIN</b> — профессиональный макрос-спаммер для Blade Ball.\n"
        f"Статус: {'✅ Доступ активен' if has_access else ' Доступ не приобретен'}"
    )

    banner_path = "klein_banner.jpg"
    try:
        photo = FSInputFile(banner_path)
        await message.answer_photo(photo=photo, caption=text, reply_markup=get_main_menu(has_access),
                                  parse_mode="HTML", disable_web_page_preview=True)
    except FileNotFoundError:
        await message.answer(text, reply_markup=get_main_menu(has_access),
                            parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    has_access = bool(user[2]) if user else False
    text = "<b>ГЛАВНОЕ МЕНЮ</b>\n<i>KLEIN</i>\n\nВыберите действие 👇"

    banner_path = "klein_banner.jpg"
    try:
        photo = FSInputFile(banner_path)
        await callback.message.answer_photo(photo=photo, caption=text,
                                           reply_markup=get_main_menu(has_access), parse_mode="HTML")
        await callback.message.delete()
    except FileNotFoundError:
        await callback.message.answer(text, reply_markup=get_main_menu(has_access), parse_mode="HTML")

@router.callback_query(F.data == "get_access")
async def get_access(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    has_access = bool(user[2]) if user else False

    if has_access:
        text = f"✅ <b>У вас уже есть доступ!</b>\n\nЛицензия: <code>{user[3]}</code>"
    else:
        text = (
            f"🛒 <b>Покупка KLEIN</b>\n\n"
            f"<b>Товар:</b> KLEIN Macro (Доступ навсегда)\n"
            f"<b>Цена:</b> 100 ₽\n\n"
            f"Выберите способ оплаты:"
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Банковская карта", callback_data="pay_card")],
        [InlineKeyboardButton(text="🏦 СБП (QR-код)", callback_data="pay_sbp")],
        [InlineKeyboardButton(text="₿ USDT (TRC-20)", callback_data="pay_usdt")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

    await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.message.delete()

@router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery):
    text = (
        f"💳 <b>Оплата</b>\n\n"
        f"Для оплаты напишите владельцу: <a href='{OWNER_LINK}'>@oftencom</a>\n"
        f"После оплаты доступ будет активирован в течение 5 минут."
    )
    await callback.message.answer(text, reply_markup=get_back_menu(),
                                  parse_mode="HTML", disable_web_page_preview=True)
    await callback.message.delete()

@router.callback_query(F.data == "enter_promo")
async def enter_promo(callback: CallbackQuery):
    text = "🎟️ <b>Введите промокод</b>\n\nОтправьте код одним сообщением:"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.message.delete()

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

@router.callback_query(F.data == "gift")
async def gift(callback: CallbackQuery):
    text = (
        f"🎁 <b>Подарить KLEIN</b>\n\n"
        f"Напишите владельцу: <a href='{OWNER_LINK}'>@oftencom</a>\n"
        f"Укажите username получателя."
    )
    await callback.message.answer(text, reply_markup=get_back_menu(),
                                  parse_mode="HTML", disable_web_page_preview=True)
    await callback.message.delete()

@router.callback_query(F.data == "about")
async def about(callback: CallbackQuery):
    text = (
        f"ℹ️ <b>О продукте KLEIN</b>\n\n"
        f"<b> ОБЩЕЕ ОПИСАНИЕ:</b>\n"
        f"<b>KLEIN</b> — это революционный программный комплекс для доминирования в Blade Ball.\n\n"
        f"<b>🔥 КЛЮЧЕВЫЕ ХАРАКТЕРИСТИКИ:</b>\n"
        f"• <b>CPS до 2000</b> — без просадок и задержек\n"
        f"• <b>Режимы Toggle и Hold</b> — гибкое управление\n"
        f"• <b>Поддержка клавиатуры и мыши</b> (вкл. боковые кнопки)\n"
        f"• <b>Human-like jitter</b> — имитация человека (±5%)\n\n"
        f"<b>💎 УНИКАЛЬНОСТЬ KLEIN:</b>\n"
        f"<b>СПАМ-МЕХАНИКА НА УРОВНЕ ЯДРА WINDOWS</b>\n"
        f"В отличие от обычных макросов, KLEIN генерирует нажатия напрямую через системные драйверы, минуя стандартный ввод Windows.\n"
        f"• Нулевая задержка между нажатиями\n"
        f"• Невозможность детекта через обычные хуки\n"
        f"• Приоритет потока TIME_CRITICAL на ядре CPU\n\n"
        f"<b>⚙️ Системные требования:</b>\n"
        f"• Windows 10/11 (x64), 4 GB RAM, 50 MB места\n\n"
        f"<b>🛡️ Безопасность:</b>\n"
        f"• Работает на уровне системы, не внедряясь в процессы игр\n"
        f"• Использует только легальные WinAPI функции"
    )
    await callback.message.answer(text, reply_markup=get_back_menu(), parse_mode="HTML")
    await callback.message.delete()

@router.callback_query(F.data == "support")
async def support(callback: CallbackQuery):
    text = (
        f" <b>Поддержка</b>\n\n"
        f"• Владелец: <a href='{OWNER_LINK}'>@oftencom</a>\n"
        f"• Канал: <a href='{CHANNEL_LINK}'>@Kleinhvh</a>\n"
        f"• Отзывы: <a href='{REVIEWS_LINK}'>@oftencore</a>\n\n"
        f"Время ответа: обычно в течение 1 часа"
    )
    await callback.message.answer(text, reply_markup=get_back_menu(),
                                  parse_mode="HTML", disable_web_page_preview=True)
    await callback.message.delete()

# --- ОБРАБОТКА ТЕКСТА ---
@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_input(message: Message):
    uid = message.from_user.id
    
    if uid in admin_states:
        action = admin_states.pop(uid)
        
        if action == 'waiting_for_promo':
            promo_name = message.text.strip().upper()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT OR IGNORE INTO promo_codes (code) VALUES (?)", (promo_name,))
                await db.commit()
            await message.answer(f"✅ Промокод <b>{promo_name}</b> создан!", parse_mode="HTML", reply_markup=get_admin_menu())
            return
            
        elif action == 'waiting_for_broadcast':
            broadcast_text = message.text
            await message.answer(" <b>Начинаю рассылку...</b>", parse_mode="HTML")
            
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute("SELECT user_id FROM users")
                users = await cursor.fetchall()
            
            success_count = 0
            for (user_id,) in users:
                try:
                    await message.bot.send_message(user_id, f"📢 {broadcast_text}")
                    success_count += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    pass
                    
            await message.answer(
                f"✅ <b>Рассылка завершена!</b>\n\n"
                f"• Успешно: {success_count}",
                parse_mode="HTML",
                reply_markup=get_admin_menu()
            )
            return

    promo_code = message.text.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT is_used FROM promo_codes WHERE code = ?", (promo_code,))
        row = await cursor.fetchone()

        if not row:
            await message.answer("❌ Промокод не найден", reply_markup=get_back_menu())
        elif row[0]:
            await message.answer("️ Промокод уже использован", reply_markup=get_back_menu())
        else:
            license_key = f"KLEIN-{promo_code[:4]}-{message.from_user.id}"
            await db.execute("UPDATE users SET has_access = 1, license_key = ?, purchased_at = ? WHERE user_id = ?",
                            (license_key, datetime.now().isoformat(), message.from_user.id))
            await db.execute("UPDATE promo_codes SET is_used = 1, used_by = ? WHERE code = ?",
                            (message.from_user.id, promo_code))
            await db.commit()
            await message.answer(f"✅ <b>Промокод активирован!</b>\n\nЛицензия: <code>{license_key}</code>",
                                reply_markup=get_back_menu(), parse_mode="HTML")

# ===== HTTP-СЕРВЕР ДЛЯ RENDER =====
async def handle_ping(request):
    return web.Response(text="Бот KLEIN работает!")

async def run_bot():
    print("🚀 Запуск бота...")
    await init_db()
    dp = Dispatcher()
    dp.include_router(router)
    bot = Bot(token=BOT_TOKEN)
    print("✅ БОТ ЗАПУЩЕН!")
    await dp.start_polling(bot)

async def main():
    # Запускаем бота и HTTP-сервер параллельно
    app = web.Application()
    app.router.add_get('/', handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("🌐 HTTP-сервер запущен на порту 8080")
    
    # Запускаем бота
    await run_bot()

if __name__ == "__main__":
    asyncio.run(main())
