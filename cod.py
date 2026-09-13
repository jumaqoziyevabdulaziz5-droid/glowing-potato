import asyncio
import logging

from telebot.async_telebot import AsyncTeleBot
from telebot import types
from telebot.asyncio_storage import StateMemoryStorage
from telebot.asyncio_handler_backends import State, StatesGroup
from telebot.asyncio_filters import StateFilter
from telebot.apihelper import ApiTelegramException
from telebot.util import extract_arguments

import config
import database as db

logging.basicConfig(level=logging.INFO)

state_storage = StateMemoryStorage()
bot = AsyncTeleBot(config.BOT_TOKEN, state_storage=state_storage)


# ==========================================
# HOLATLAR (FSM) — kino qo'shish jarayoni uchun
# ==========================================
class AddMovie(StatesGroup):
    waiting_for_code = State()
    waiting_for_video = State()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ==========================================
# MAJBURIY OBUNANI TEKSHIRISH
# ==========================================
async def check_subscription(user_id: int) -> list:
    """Obuna bo'lmagan kanallar ro'yxatini qaytaradi (bo'sh bo'lsa — hammasiga obuna)."""
    not_subscribed = []
    for channel in config.FORCE_SUB_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                not_subscribed.append(channel)
        except ApiTelegramException:
            # Bot kanalda admin bo'lmasa yoki kanal topilmasa, tekshiruvni o'tkazib yuboramiz
            continue
    return not_subscribed


async def send_force_sub_message(message: types.Message, channels: list):
    text = "Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling, so'ng /start bosing:\n\n"
    text += "\n".join(f"➡️ {ch}" for ch in channels)
    await bot.send_message(message.chat.id, text)


# ==========================================
# FOYDALANUVCHI BUYRUQLARI
# ==========================================
@bot.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    not_sub = await check_subscription(message.from_user.id)
    if not_sub:
        await send_force_sub_message(message, not_sub)
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📸 Biz bilan birga bo'ling", url="https://www.instagram.com/primekinobot"))
    await bot.send_message(
        message.chat.id,
        "🎬 Assalomu alaykum!\n\n"
        "Kino kodini yuboring, men sizga kinoni topib beraman.\n"
        "Masalan: <code>123</code>",
        parse_mode="HTML",
        reply_markup=kb,
    )


@bot.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    text = (
        "🎬 <b>Kino bot</b>\n\n"
        "Kino kodini yuboring — men kanaldan topib, sizga yuboraman.\n\n"
    )
    if is_admin(message.from_user.id):
        text += (
            "<b>Admin buyruqlari:</b>\n"
            "/add — yangi kino qo'shish\n"
            "/delete &lt;kod&gt; — kinoni o'chirish\n"
            "/list — oxirgi qo'shilgan kinolar\n"
            "/top — eng ko'p ko'rilgan kinolar\n"
            "/stats — statistika\n"
        )
    await bot.send_message(message.chat.id, text, parse_mode="HTML")


# ==========================================
# ADMIN: KINO QO'SHISH (FSM orqali)
# ==========================================
@bot.message_handler(commands=["add"])
async def cmd_add(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await bot.send_message(
        message.chat.id,
        "Kino uchun kod kiriting (masalan: <code>123</code> yoki <code>avatar2</code>):",
        parse_mode="HTML",
    )
    await bot.set_state(message.from_user.id, AddMovie.waiting_for_code, message.chat.id)


@bot.message_handler(state=AddMovie.waiting_for_code)
async def process_code(message: types.Message):
    code = message.text.strip()
    if not code:
        await bot.send_message(message.chat.id, "Kod bo'sh bo'lishi mumkin emas. Qaytadan kiriting:")
        return

    existing = await db.get_movie(code)
    if existing:
        await bot.send_message(
            message.chat.id,
            f"⚠️ <code>{code}</code> kodi allaqachon band. "
            f"Davom etsangiz, eski kino ustidan yoziladi.",
            parse_mode="HTML",
        )

    async with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data["code"] = code

    await bot.send_message(
        message.chat.id,
        "Endi kino videosini (yoki faylini) shu yerga yuboring, "
        "yoki uni to'g'ridan-to'g'ri kanaldan forward qiling:",
    )
    await bot.set_state(message.from_user.id, AddMovie.waiting_for_video, message.chat.id)


@bot.message_handler(content_types=["video", "document", "animation"], state=AddMovie.waiting_for_video)
async def process_video(message: types.Message):
    async with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        code = data["code"]

    # Videoni (yoki forward qilingan xabarni) kanalga nusxalaymiz va saqlaymiz
    sent = await bot.copy_message(config.CHANNEL_ID, message.chat.id, message.message_id)
    channel_message_id = sent.message_id
    title = message.caption or None

    await db.add_movie(code, channel_message_id, title, message.from_user.id)
    await bot.send_message(message.chat.id, f"✅ Kino saqlandi!\nKod: <code>{code}</code>", parse_mode="HTML")
    await bot.delete_state(message.from_user.id, message.chat.id)


@bot.message_handler(state=AddMovie.waiting_for_video)
async def process_video_invalid(message: types.Message):
    await bot.send_message(
        message.chat.id,
        "Iltimos, video yoki fayl yuboring (yoki /add ni bekor qilish uchun /cancel yozing).",
    )


@bot.message_handler(commands=["cancel"])
async def cmd_cancel(message: types.Message):
    current_state = await bot.get_state(message.from_user.id, message.chat.id)
    if current_state is not None:
        await bot.delete_state(message.from_user.id, message.chat.id)
        await bot.send_message(message.chat.id, "Bekor qilindi.")


# ==========================================
# ADMIN: KINONI O'CHIRISH
# ==========================================
@bot.message_handler(commands=["delete"])
async def cmd_delete(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    code = extract_arguments(message.text).strip()
    if not code:
        await bot.send_message(message.chat.id, "Foydalanish: /delete <kod>")
        return

    ok = await db.delete_movie(code)
    if ok:
        await bot.send_message(message.chat.id, f"🗑 <code>{code}</code> o'chirildi.", parse_mode="HTML")
    else:
        await bot.send_message(message.chat.id, f"<code>{code}</code> topilmadi.", parse_mode="HTML")


# ==========================================
# ADMIN: RO'YXAT VA STATISTIKA
# ==========================================
@bot.message_handler(commands=["list"])
async def cmd_list(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    movies = await db.list_movies()
    if not movies:
        await bot.send_message(message.chat.id, "Hozircha kinolar yo'q.")
        return

    text = "🎬 Oxirgi qo'shilgan kinolar:\n\n"
    for code, title, views in movies:
        title_part = f" — {title}" if title else ""
        text += f"<code>{code}</code>{title_part} (👁 {views})\n"
    await bot.send_message(message.chat.id, text, parse_mode="HTML")


@bot.message_handler(commands=["stats"])
async def cmd_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    total = await db.count_movies()
    await bot.send_message(message.chat.id, f"📊 Bazadagi kinolar soni: {total}")


@bot.message_handler(commands=["top"])
async def cmd_top(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    movies = await db.top_movies(10)
    if not movies:
        await bot.send_message(message.chat.id, "Hozircha kinolar yo'q.")
        return

    text = "🔥 Eng ko'p ko'rilgan kinolar:\n\n"
    for i, (code, title, views) in enumerate(movies, start=1):
        title_part = f" — {title}" if title else ""
        text += f"{i}. <code>{code}</code>{title_part} (👁 {views})\n"
    await bot.send_message(message.chat.id, text, parse_mode="HTML")


# ==========================================
# FOYDALANUVCHI: KOD YUBORGANDA QIDIRISH
# ==========================================
@bot.message_handler(content_types=["text"], state=None)
async def search_movie(message: types.Message):
    if message.text.startswith("/"):
        return  # noma'lum buyruqlarni e'tiborsiz qoldiramiz

    not_sub = await check_subscription(message.from_user.id)
    if not_sub:
        await send_force_sub_message(message, not_sub)
        return

    code = message.text.strip()
    result = await db.get_movie(code)
    if not result:
        await bot.send_message(message.chat.id, "❌ Bunday kodli kino topilmadi. Kodni tekshirib qaytadan yuboring.")
        return

    channel_message_id, title = result
    try:
        await bot.copy_message(message.chat.id, config.CHANNEL_ID, channel_message_id)
        await db.increment_views(code)
    except ApiTelegramException:
        await bot.send_message(
            message.chat.id,
            "⚠️ Kinoni yuborishda xatolik yuz berdi. "
            "Ehtimol, u kanaldan o'chirilgan. Admin bilan bog'laning.",
        )


# ==========================================
# ISHGA TUSHIRISH
# ==========================================
async def main():
    await db.init_db()
    bot.add_custom_filter(StateFilter(bot))
    print("Bot ishga tushdi...")
    await bot.polling(non_stop=True)


if __name__ == "__main__":
    asyncio.run(main())
