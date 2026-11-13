"""Logique d'une idee : accuse, brouillon, challenge, reponses, /prete. Independante de Telegram."""
import asyncio
import logging

from .brain import BrainUnavailable
from .fiche import CHALLENGE_DONE, CHALLENGE_FAILED, CHALLENGE_PENDING, READY, title_of

log = logging.getLogger("ideadesk.service")

# Messages du bot, par langue de la fiche. Sans fiche connue (ou avant le choix de la langue) : les deux.
MSG = {
    "fr": {
        "saved": "Idée enregistrée en brouillon. Fiche : {url}",
        "objections": "Objections :",
        "postponed": "Le challenge est reporté ({why}). Réponds dans ce fil pour le relancer. Fiche : {url}",
        "no_integrate": "Je n'ai pas pu intégrer ta réponse ({why}). Renvoie-la plus tard.",
        "updated": "Fiche mise à jour : {url}",
        "ready": "Fiche prête : {url}",
        "use_ready": "Utilise /prete dans le fil d'une idée.",
        "newidea_prompt": "Écris ton idée dans ce fil.",
        "no_threads": "Je n'ai pas pu créer de fil : active le Threaded mode du bot dans BotFather.",
    },
    "en": {
        "saved": "Idea saved as a draft. Sheet: {url}",
        "objections": "Objections:",
        "postponed": "The challenge is postponed ({why}). Reply in this thread to retry it. Sheet: {url}",
        "no_integrate": "I could not fold in your answer ({why}). Please send it again later.",
        "updated": "Sheet updated: {url}",
        "ready": "Sheet ready: {url}",
        "use_ready": "Use /prete inside an idea's thread.",
        "newidea_prompt": "Write your idea in this thread.",
        "no_threads": "I could not create a thread: enable the bot's Threaded mode in BotFather.",
    },
}


def say(key, lang=None, **kw):
    """Message dans la langue de la fiche ; les deux langues si elle n'est pas encore choisie."""
    if lang in MSG:
        return MSG[lang][key].format(**kw)
    return " / ".join(MSG[l][key].format(**kw) for l in MSG)


class Service:
    def __init__(self, store, brain, messenger, base_url, owner_id):
        self.store, self.brain, self.messenger = store, brain, messenger
        self.base_url, self.owner_id = base_url.rstrip("/"), owner_id
        self._queue = None
        self._worker_task = None

    def start(self):
        # Une seule file : tous les appels au cerveau passent l'un apres l'autre.
        self._queue = asyncio.Queue()
        self._queue.put_nowait(self._resume)
        self._worker_task = asyncio.create_task(self._worker())

    async def _resume(self):
        # Un redemarrage a pu interrompre un challenge : les fiches restees en cours le reprennent.
        for fiche in await asyncio.to_thread(self.store.list):
            if fiche.challenge == CHALLENGE_PENDING:
                await self._challenge(fiche.id)

    async def drain(self):
        await self._queue.join()

    async def _worker(self):
        while True:
            job = await self._queue.get()
            try:
                await job()
            except Exception:
                log.exception("tache en echec")
            finally:
                self._queue.task_done()

    def _url(self, fiche):
        return f"{self.base_url}/fiche/{fiche.id}"

    async def _fiche(self, fiche_id):
        return await asyncio.to_thread(self.store.get, fiche_id)

    async def _save(self, fiche):
        await asyncio.to_thread(self.store.save, fiche)

    async def on_message(self, user_id, text, thread_id):
        if user_id != self.owner_id:
            log.info("expéditeur inconnu ignoré : %s", user_id)
            return
        text = (text or "").strip()
        if not text:
            return
        command, _, rest = text.partition(" ")
        command = command.split("@")[0]  # /newidea@nom_du_bot
        if command == "/prete":
            return await self._on_ready(thread_id)
        if command == "/newidea":
            return await self._on_newidea(rest.strip())
        if text.startswith("/"):
            return
        if thread_id is None:
            return await self._on_new_idea(text)
        fiche = await asyncio.to_thread(self.store.find_by_thread, thread_id)
        if fiche is None:
            # Avec les sujets actives, chaque message arrive dans un fil : un fil sans fiche ouvre une nouvelle idee.
            return await self._on_new_idea(text, thread_id)
        self._queue.put_nowait(lambda: self._reply(fiche.id, text))

    async def _on_newidea(self, text):
        if text:  # /newidea mon idee : meme chemin qu'une idee ecrite hors de tout fil
            return await self._on_new_idea(text)
        try:
            thread_id = await self.messenger.new_thread("New idea")
        except Exception:
            log.exception("creation du fil impossible")
            return await self.messenger.send(None, say("no_threads"))
        await self.messenger.send(thread_id, say("newidea_prompt"))

    async def _on_new_idea(self, text, thread_id=None):
        if thread_id is None:
            try:
                thread_id = await self.messenger.new_thread(title_of(text))
            except Exception:
                log.exception("creation du fil impossible, idée gardée sans fil")
        fiche = await asyncio.to_thread(self.store.create, text, thread_id)
        try:
            await self.messenger.send(thread_id, say("saved", url=self._url(fiche)))
        except Exception:
            log.exception("accusé non envoyé, le challenge part quand même")
        self._queue.put_nowait(lambda: self._challenge(fiche.id))

    async def _challenge(self, fiche_id):
        fiche = await self._fiche(fiche_id)
        try:
            fiche.lang, fiche.objections = await asyncio.to_thread(self.brain.challenge, fiche)
        except BrainUnavailable as err:
            fiche.challenge = CHALLENGE_FAILED
            await self._save(fiche)
            await self.messenger.send(fiche.thread_id, say("postponed", why=err, url=self._url(fiche)))
            return
        fiche.challenge = CHALLENGE_DONE
        await self._save(fiche)
        lines = []
        for o in fiche.objections:
            lines.append(f"{o.id}. {o.texte}\n   " + "\n   ".join(o.sources))
        await self.messenger.send(fiche.thread_id, say("objections", fiche.lang) + "\n\n" + "\n\n".join(lines) + f"\n\n{self._url(fiche)}")

    async def _reply(self, fiche_id, text):
        fiche = await self._fiche(fiche_id)
        if fiche.challenge == CHALLENGE_FAILED:
            await self._challenge(fiche_id)
            fiche = await self._fiche(fiche_id)
        try:
            themes = await asyncio.to_thread(self.store.themes)
            fiche = await asyncio.to_thread(self.brain.integrate, fiche, text, themes)
        except BrainUnavailable as err:
            await self.messenger.send(fiche.thread_id, say("no_integrate", fiche.lang, why=err))
            return
        await self._save(fiche)
        await self.messenger.send(fiche.thread_id, say("updated", fiche.lang, url=self._url(fiche)))

    async def _on_ready(self, thread_id):
        fiche = None if thread_id is None else await asyncio.to_thread(self.store.find_by_thread, thread_id)
        if fiche is None:
            return await self.messenger.send(thread_id, say("use_ready"))

        async def mark():
            current = await self._fiche(fiche.id)
            current.status = READY
            await self._save(current)
            await self.messenger.send(current.thread_id, say("ready", current.lang, url=self._url(current)))

        self._queue.put_nowait(mark)
