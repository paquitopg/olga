"""Demarre le bot Telegram et le site dans un meme processus."""
import asyncio
import logging
import sys

import uvicorn
from aiogram import Bot

from .bot import TelegramMessenger, build_dispatcher
from .brain import Brain
from .config import MissingSetting, load
from .service import Service
from .store import Store
from .web import create_app

log = logging.getLogger("ideadesk")


async def run_all(server, service, start_poll, stop_poll, drain_timeout=30):
    """Site et interrogation Telegram ensemble ; l'arret du site arrete l'autre, et un bot mort arrete le site."""
    poll = asyncio.create_task(start_poll())
    poll.add_done_callback(lambda _: setattr(server, "should_exit", True))
    try:
        await server.serve()
    finally:
        await stop_poll()
        await asyncio.gather(poll, return_exceptions=True)
        try:
            await asyncio.wait_for(service.drain(), drain_timeout)
        except asyncio.TimeoutError:
            log.warning("des taches n'ont pas fini avant l'arret")
    if not poll.cancelled() and poll.exception():
        raise poll.exception()


async def serve(settings):
    store = Store(settings.library_dir, settings.library_repo_url, settings.library_git_token)
    await asyncio.to_thread(store.ensure_clone)
    brain = Brain(settings.claude_bin, settings.claude_model, settings.claude_token, settings.anthropic_api_key)
    bot = Bot(settings.telegram_bot_token)
    service = Service(store, brain, TelegramMessenger(bot, settings.owner_telegram_id), settings.public_base_url, settings.owner_telegram_id)
    service.start()
    dp = build_dispatcher(service)
    app = create_app(store, settings.site_password_hash, settings.session_secret)
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info"))

    async def start_poll():
        await bot.delete_webhook()  # interrogation continue et webhook s'excluent
        await dp.start_polling(bot, handle_signals=False)

    async def stop_poll():
        try:
            await dp.stop_polling()
        except RuntimeError:
            pass  # pas encore demarre

    try:
        await run_all(server, service, start_poll, stop_poll)
    finally:
        await bot.session.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    try:
        settings = load()
    except MissingSetting as err:
        print(err, file=sys.stderr)
        sys.exit(2)
    asyncio.run(serve(settings))


if __name__ == "__main__":
    main()
