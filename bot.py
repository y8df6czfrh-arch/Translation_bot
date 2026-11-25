import asyncio
import logging
import os
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Не заданы BOT_TOKEN или OPENAI_API_KEY в .env")

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# Стало (добавь base_url):
ai_client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    base_url=os.getenv("BASE_URL")
)

MODEL = "meta-llama/llama-3-8b-instruct:free"

@dataclass(frozen=True)
class Style:
    code: str
    label: str
    prompt: str

STYLES: dict[str, Style] = {
    "official": Style("official", "📄 Официальный", "Перепиши текст в строгом официально-деловом стиле. Сохрани весь смысл, но используй формальную лексику."),
    "friendly": Style("friendly", "😊 Дружеский", "Перепиши текст в дружеском, тёплом и разговорном стиле."),
    "short": Style("short", "✂️ Краткий", "Сократи текст до 1–3 предложений, сохранив ключевую мысль."),
    "creative": Style("creative", "🎨 Креативный", "Перепиши текст в креативном, образном стиле. Допустимы метафоры."),
    "academic": Style("academic", "🎓 Академический", "Перепиши текст в академическом стиле: нейтральный тон, точные формулировки."),
}
DEFAULT_STYLE = "official"

def style_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=s.label, callback_data=f"style:{code}")]
        for code, s in STYLES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def translate_text(text: str, target_lang: str = "ru") -> str:
    prompt = (
        f"Переведи следующий текст на язык '{target_lang}'. "
        "Если текст уже на этом языке, верни его без изменений. "
        f"Выведи ТОЛЬКО перевод.\n\nТекст:\n{text}"
    )
    response = await ai_client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()

async def restyle_text(text: str, style: Style) -> str:
    prompt = (
        f"{style.prompt}\n\n"
        "Выведи ТОЛЬКО переработанный текст, без вступлений и пояснений.\n\n"
        f"Исходный текст:\n{text}"
    )
    response = await ai_client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()

user_style: dict[int, str] = {}

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_style[message.from_user.id] = DEFAULT_STYLE
    await message.answer(
        "👋 Привет! Я перевожу текст на русский (если нужно) и переформатирую его.\n\n"
        "Выбери стиль кнопкой ниже, а затем просто отправь текст.",
        reply_markup=style_keyboard(),
    )

@dp.message(Command("style"))
async def cmd_style(message: Message):
    await message.answer("Выбери стиль переформатирования:", reply_markup=style_keyboard())

@dp.callback_query(F.data.startswith("style:"))
async def on_style_selected(callback: CallbackQuery):
    code = callback.data.split(":", 1)[1]
    if code not in STYLES:
        await callback.answer("Неизвестный стиль", show_alert=True)
        return

    user_style[callback.from_user.id] = code
    style = STYLES[code]

    await callback.message.edit_text(
        f"✅ Стиль изменён на: <b>{style.label}</b>\n\nТеперь отправь текст, и я его обработаю.",
        reply_markup=style_keyboard(),
    )
    await callback.answer()

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message):
    user_id = message.from_user.id
    style_code = user_style.get(user_id, DEFAULT_STYLE)
    style = STYLES[style_code]

    source_text = message.text.strip()
    if not source_text:
        return

    processing_msg = await message.answer("⏳ Перевожу и переформатирую…")

    try:
        translated = await translate_text(source_text, target_lang="ru")
        styled = await restyle_text(translated, style)

        result = f"<b>Стиль:</b> {style.label}\n\n<b>Результат:</b>\n{styled}"
        await processing_msg.edit_text(result)

    except Exception as e:
        logging.exception("Ошибка при обработке текста")
        await processing_msg.edit_text(
            "😔 Не удалось обработать текст. Попробуй позже.\n"
            f"<code>{type(e).__name__}: {e}</code>"
        )

async def main():
    logging.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
