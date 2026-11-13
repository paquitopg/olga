"""Logique d'une idee : accuse, brouillon, challenge, reponses, /prete. Independante de Telegram."""
import asyncio
import logging

from .brain import BrainUnavailable
from .fiche import CHALLENGE_DONE, CHALLENGE_FAILED, READY, title_of

log = logging.getLogger("ideadesk.service")


class Service:
    def __init__(self, store, brain, messenger, base_url, owner_id):
        self.store, self.brain, self.messenger = store, brain, messenger
        self.base_url, self.owner_id = base_url.rstrip("/"), owner_id
        self._queue = None
        self._worker_task = None

    def start(self):
        # Une seule file : tous les appels au cerveau passent l'un apres l'autre.
        self._queue = asyncio.Queue()
        self._worker_task = asyncio.create_task(self._worker())

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
        if text.startswith("/prete"):
            return await self._on_ready(thread_id)
        if text.startswith("/"):
            return
        if thread_id is None:
            return await self._on_new_idea(text)
        fiche = await asyncio.to_thread(self.store.find_by_thread, thread_id)
        if fiche is None:
            return await self.messenger.send(thread_id, "Je ne retrouve pas cette idée.")
        self._queue.put_nowait(lambda: self._reply(fiche.id, text))

    async def _on_new_idea(self, text):
        try:
            thread_id = await self.messenger.new_thread(title_of(text))
        except Exception:
            log.exception("creation du fil impossible, idée gardée sans fil")
            thread_id = None
        fiche = await asyncio.to_thread(self.store.create, text, thread_id)
        await self.messenger.send(thread_id, f"Idée enregistrée en brouillon. Fiche : {self._url(fiche)}")
        self._queue.put_nowait(lambda: self._challenge(fiche.id))

    async def _challenge(self, fiche_id):
        fiche = await self._fiche(fiche_id)
        try:
            fiche.objections = await asyncio.to_thread(self.brain.challenge, fiche)
        except BrainUnavailable as err:
            fiche.challenge = CHALLENGE_FAILED
            await self._save(fiche)
            await self.messenger.send(
                fiche.thread_id,
                f"Le challenge est reporté ({err}). Réponds dans ce fil pour le relancer. Fiche : {self._url(fiche)}",
            )
            return
        fiche.challenge = CHALLENGE_DONE
        await self._save(fiche)
        lines = []
        for o in fiche.objections:
            lines.append(f"{o.id}. {o.texte}\n   " + "\n   ".join(o.sources))
        await self.messenger.send(fiche.thread_id, "Objections :\n\n" + "\n\n".join(lines) + f"\n\nFiche : {self._url(fiche)}")

    async def _reply(self, fiche_id, text):
        fiche = await self._fiche(fiche_id)
        if fiche.challenge == CHALLENGE_FAILED:
            await self._challenge(fiche_id)
            fiche = await self._fiche(fiche_id)
        try:
            themes = await asyncio.to_thread(self.store.themes)
            fiche = await asyncio.to_thread(self.brain.integrate, fiche, text, themes)
        except BrainUnavailable as err:
            await self.messenger.send(fiche.thread_id, f"Je n'ai pas pu intégrer ta réponse ({err}). Renvoie-la plus tard.")
            return
        await self._save(fiche)
        await self.messenger.send(fiche.thread_id, f"Fiche mise à jour : {self._url(fiche)}")

    async def _on_ready(self, thread_id):
        fiche = None if thread_id is None else await asyncio.to_thread(self.store.find_by_thread, thread_id)
        if fiche is None:
            return await self.messenger.send(thread_id, "Utilise /prete dans le fil d'une idée.")

        async def mark():
            current = await self._fiche(fiche.id)
            current.status = READY
            await self._save(current)
            await self.messenger.send(current.thread_id, f"Fiche prête : {self._url(current)}")

        self._queue.put_nowait(mark)
