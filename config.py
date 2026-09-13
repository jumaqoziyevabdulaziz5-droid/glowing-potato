import os

# ==========================================
# ASOSIY SOZLAMALAR — bu yerlarni o'zgartiring
# ==========================================

# @BotFather dan olingan bot tokeni
BOT_TOKEN = os.getenv("BOT_TOKEN", "8892389501:AAFe-FP4oQKRCCE9NCGbG75LejikGn9DBjw")

# Kinolar saqlanadigan kanalning ID raqami (masalan: -1001234567890)
# ID ni topish uchun README.md dagi ko'rsatmaga qarang
CHANNEL_ID = os.getenv("CHANNEL_ID", "@abuxankino")

# Botni boshqaradigan adminlarning Telegram ID raqamlari
ADMIN_IDS = [
    7170382261,  # Abdulaziz Jumaqo'ziyev
]

# ------------------------------------------
# MAJBURIY OBUNA (ixtiyoriy funksiya)
# ------------------------------------------
# Agar foydalanuvchi botdan foydalanishdan oldin ma'lum kanal(lar)ga
# obuna bo'lishi shart bo'lsa, shu ro'yxatga kanal username larini yozing.
# Masalan: ["@mening_kanalim", "@boshqa_kanal"]
# Agar kerak bo'lmasa, bo'sh ro'yxat qoldiring: []
FORCE_SUB_CHANNELS = ["@abuxan_kino", "@abuxankinobot", "@abuxan_kinobot"]

# Kinolar ma'lumotlari saqlanadigan fayl (JSON)
DB_PATH = os.getenv("DB_PATH", "movies.json")
