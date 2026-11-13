import asyncio
import logging
import threading

from ideadesk.brain import BrainUnavailable
from ideadesk.fiche import Objection
from ideadesk.service import Service

OWNER = 42
BASE = "https://ideas.example"


class FakeMessenger:
    def __init__(self, events):
        self.sent, self.events, self.next_thread = [], events, 100

    async def new_thread(self, title):
        self.next_thread += 1
        return self.next_thread

    async def send(self, thread_id, text):
        self.sent.append((thread_id, text))
        self.events.append(("send", thread_id))


class FakeBrain:
    def __init__(self, events, store=None):
        self.events, self.store = events, store
        self.fail_challenge = False
        self.integrate_raises = None
        self.challenge_calls = 0
        self.gate = None  # threading.Event : bloque le challenge tant qu'il n'est pas leve
        self.started = threading.Event()

    def challenge(self, fiche):
        self.events.append("challenge")
        self.challenge_calls += 1
        if self.store is not None:
            assert self.store.get(fiche.id) is not None  # le brouillon existe deja
        self.started.set()
        if self.gate:
            self.gate.wait(5)
        if self.fail_challenge:
            raise BrainUnavailable("recherche indisponible")
        return [Objection("O1", "Marché saturé ?", ["https://a.example"])]

    def integrate(self, fiche, answer, themes):
        self.events.append("integrate")
        if self.integrate_raises:
            raise self.integrate_raises
        import dataclasses
        objs = [dataclasses.replace(o, reponse=answer) for o in fiche.objections]
        return dataclasses.replace(fiche, problem=f"P:{answer}", objections=objs)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()


def make(store):
    events = []
    messenger, brain = FakeMessenger(events), FakeBrain(events, store)
    return Service(store, brain, messenger, BASE, OWNER), messenger, brain, events


def test_unknown_sender_gets_no_reply_and_creates_nothing(store, caplog):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        with caplog.at_level(logging.INFO):
            await service.on_message(999, "mon idée", None)
        await service.drain()

    run(go())
    assert messenger.sent == [] and store.list() == []
    assert "999" in caplog.text


def test_new_idea_saves_the_draft_then_acks_with_link_then_challenges(store):
    service, messenger, brain, events = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "Une app de covoiturage pour chiens", None)
        await service.drain()

    run(go())
    [fiche] = store.list()
    assert fiche.status == "brouillon" and fiche.challenge == "fait"
    assert messenger.sent[0][1].endswith(f"{BASE}/fiche/{fiche.id}")
    assert events[:2] == [("send", 101), "challenge"]  # accusé avant challenge
    assert fiche.objections[0].texte == "Marché saturé ?"


def test_two_quick_ideas_stay_separate_and_a_reply_hits_the_right_one(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée un", None)
        await service.on_message(OWNER, "idée deux", None)
        await service.drain()
        await service.on_message(OWNER, "ma réponse", 102)
        await service.drain()

    run(go())
    first = store.find_by_thread(101)
    second = store.find_by_thread(102)
    assert first.id != second.id
    assert second.problem == "P:ma réponse" and first.problem == ""


def test_idea_without_reply_stays_a_draft_with_objections_and_no_more_messages(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée seule", None)
        await service.drain()

    run(go())
    [fiche] = store.list()
    assert fiche.status == "brouillon" and fiche.raw_idea == "idée seule" and fiche.objections
    assert len(messenger.sent) == 2  # accusé + objections


def test_reply_integrates_and_sends_one_message_with_the_link(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()
        messenger.sent.clear()
        await service.on_message(OWNER, "réponse", 101)
        await service.drain()

    run(go())
    assert len(messenger.sent) == 1 and "/fiche/" in messenger.sent[0][1]


def test_ready_command_marks_the_fiche_and_confirms_with_the_link(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()
        await service.on_message(OWNER, "/prete", 101)
        await service.drain()

    run(go())
    assert store.find_by_thread(101).status == "prete"
    assert "/fiche/" in messenger.sent[-1][1]


def test_ready_outside_an_idea_thread_is_refused_politely(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "/prete", None)
        await service.drain()

    run(go())
    assert store.list() == [] and len(messenger.sent) == 1 and "fil" in messenger.sent[0][1]


def test_unavailable_challenge_keeps_draft_acks_and_explains_the_postponement(store):
    service, messenger, brain, _ = make(store)
    brain.fail_challenge = True

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()

    run(go())
    [fiche] = store.list()
    assert fiche.challenge == "echec" and fiche.status == "brouillon"
    assert len(messenger.sent) == 2 and "report" in messenger.sent[1][1].lower()


def test_reply_on_a_failed_challenge_retries_the_challenge_before_integrating(store):
    service, messenger, brain, events = make(store)
    brain.fail_challenge = True

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()
        brain.fail_challenge = False
        events.clear()
        await service.on_message(OWNER, "réponse", 101)
        await service.drain()

    run(go())
    assert [e for e in events if isinstance(e, str)] == ["challenge", "integrate"]
    assert store.find_by_thread(101).challenge == "fait"


def test_reply_during_a_running_challenge_waits_and_starts_no_second_challenge(store):
    service, messenger, brain, events = make(store)
    brain.gate = threading.Event()

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        while not brain.started.is_set():
            await asyncio.sleep(0.01)
        await service.on_message(OWNER, "réponse pressée", 101)
        brain.gate.set()
        await service.drain()

    run(go())
    fiche = store.find_by_thread(101)
    assert brain.challenge_calls == 1
    assert [e for e in events if isinstance(e, str)] == ["challenge", "integrate"]
    assert fiche.objections[0].texte == "Marché saturé ?" and fiche.objections[0].reponse == "réponse pressée"


def test_reply_in_an_unknown_thread_is_refused_without_creating_a_fiche(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "bonjour", 555)
        await service.drain()

    run(go())
    assert store.list() == [] and len(messenger.sent) == 1


def test_restart_resumes_a_challenge_left_in_progress(store):
    pending = store.create("idée interrompue", thread_id=101)
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.drain()

    run(go())
    assert store.get(pending.id).challenge == "fait" and store.get(pending.id).objections


def test_a_failed_acknowledgement_does_not_stop_the_challenge(store):
    service, messenger, brain, _ = make(store)
    original = messenger.send
    calls = []

    async def flaky(thread_id, text):
        calls.append(text)
        if len(calls) == 1:
            raise RuntimeError("telegram down")
        await original(thread_id, text)

    messenger.send = flaky

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()

    run(go())
    assert store.list()[0].challenge == "fait"


def test_integration_failure_tells_the_owner_and_keeps_the_fiche(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()
        brain.integrate_raises = BrainUnavailable("sortie illisible")
        messenger.sent.clear()
        await service.on_message(OWNER, "réponse", 101)
        await service.drain()

    run(go())
    assert "pas pu intégrer" in messenger.sent[0][1]
    assert store.find_by_thread(101).problem == ""


def test_an_unexpected_error_in_a_job_does_not_stop_the_next_job(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()
        brain.integrate_raises = ValueError("boom")
        await service.on_message(OWNER, "première réponse", 101)
        await service.drain()
        brain.integrate_raises = None
        await service.on_message(OWNER, "seconde réponse", 101)
        await service.drain()

    run(go())
    assert store.find_by_thread(101).problem == "P:seconde réponse"
