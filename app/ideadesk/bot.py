"""Colle aiogram : un message du proprietaire devient un appel au service."""
from aiogram import Bot, Dispatcher
from aiogram.types import Message

MAX_LEN = 4000  # limite Telegram : 4096 caracteres par message


def chunks(text, limit=MAX_LEN):
    parts, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit and current:
            parts.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current:
        parts.append(current)
    return parts


class TelegramMessenger:
    def __init__(self, bot: Bot, chat_id: int):
        self.bot, self.chat_id = bot, chat_id

    async def new_thread(self, title):
        topic = await self.bot.create_forum_topic(self.chat_id, name=title[:128])
        return topic.message_thread_id

    async def send(self, thread_id, text):
        for part in chunks(text):
            await self.bot.send_message(self.chat_id, part, message_thread_id=thread_id)


def build_dispatcher(service):
    dp = Dispatcher()

    @dp.message()
    async def on_message(message: Message):
        thread_id = message.message_thread_id if message.is_topic_message else None
        await service.on_message(message.from_user.id if message.from_user else None, message.text or "", thread_id)

    return dp
