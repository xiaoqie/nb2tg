import asyncio
import time
import nonebot
from nonebot import logger
import telegram
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler


class TelegramApp:
    task: asyncio.Task
    bot: telegram.Bot
    me: telegram.User
    def __init__(self, token: str, chat_id: int):
        self.chat_id = chat_id
        self.last_send_timestamp = time.time()
        self.stop = asyncio.Event()
        self.application = ApplicationBuilder().token(token).build()
        self.bot = self.application.bot
        nonebot.get_driver().on_startup(self.start)
        nonebot.get_driver().on_shutdown(self.shutdown)

    async def start_polling(self):
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            self.me = await self.bot.get_me()
            logger.info(self.me)
            await self.stop.wait()
        except (KeyboardInterrupt, SystemExit):
            print("Application received stop signal. Shutting down.")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
    
    async def start(self):
        self.task = asyncio.create_task(self.start_polling())

    async def shutdown(self):
        self.stop.set()
        if not self.task.done():
            self.task.cancel()

    async def create_forum_topic(self, name: str) -> telegram.ForumTopic:
        return await self.bot.create_forum_topic(self.chat_id, name)

    async def send_message(self, text, *args, **kwargs) -> telegram.Message:
        self.last_send_timestamp = time.time()
        logger.info(f"sent {repr(text)} to telegram")
        return await self.bot.send_message(self.chat_id, text, *args, **kwargs)

    async def send_media_group(self, media, *args, **kwargs) -> telegram.Message:
        self.last_send_timestamp = time.time()
        logger.info(f"sent {repr(media)} to telegram")
        return await self.bot.send_media_group(self.chat_id, media, *args, **kwargs)

    def handle_command(self, command: str):
        def wrapper(fn):
            self.application.add_handler(CommandHandler(command, fn))
        return wrapper

    def handle_message(self, filters=None):
        def wrapper(fn):
            self.application.add_handler(MessageHandler(filters, fn))
        return wrapper
