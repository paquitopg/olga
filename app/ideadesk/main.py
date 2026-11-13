"""Demarre le bot Telegram et le site dans un meme processus."""
import asyncio
import contextlib
import logging
import signal
import sys

import uvicorn
from aiogram import Bot
from aiogram.types import BotCommand

from .bot import TelegramMessenger, build_dispatcher
from .brain import Brain
from .config import MissingSetting, load
from .service import Service
from .store import Store
from .web import create_app

log = logging.getLogger("ideadesk")


class Server(uvicorn.Server):
    """uvicorn renvoie le signal recu apres son arret propre, ce qui tuerait le processus avant notre nettoyage."""

    @contextlib.contextmanager
    def capture_signals(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, setattr, self, "should_exit", True)
        try:
            yield
        finally:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)


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
    error = None if poll.cancelled() else poll.exception()
    if error:
        raise error


async def serve(settings):
    store = Store(settings.library_dir, settings.library_repo_url, settings.library_git_token)
    await asyncio.to_thread(store.ensure_clone)
    brain = Brain(settings.claude_bin, settings.claude_model, settings.claude_token, settings.anthropic_api_key)
    bot = Bot(settings.telegram_bot_token)
    service = Service(store, brain, TelegramMessenger(bot, settings.owner_telegram_id), settings.public_base_url, settings.owner_telegram_id,
                      explore_limits=(settings.explore_max_five_hour, settings.explore_max_seven_day))
    service.start()
    dp = build_dispatcher(service)
    app = create_app(store, settings.site_password_hash, settings.session_secret)
    server = Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info"))

    async def start_poll():
        await bot.delete_webhook()  # interrogation continue et webhook s'excluent
        try:  # menu "/" de Telegram ; un echec ici ne doit pas empecher le bot de demarrer
            await bot.set_my_commands([
                BotCommand(command="newidea", description="New idea / Nouvelle idée"),
                BotCommand(command="prete", description="Mark this sheet ready / Fiche prête"),
                BotCommand(command="rechallenge", description="New objections for this sheet / Nouvelles objections"),
                BotCommand(command="explore", description="Use spare quota to find new ideas / Explorer de nouvelles idées"),
                BotCommand(command="lang", description="Sheet language: /lang fr or /lang en / Langue de la fiche"),
            ])
        except Exception:
            log.exception("menu des commandes non enregistré")
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
