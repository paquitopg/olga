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
        self.sent, self.events, self.next_thread, self.titles = [], events, 100, []

    async def new_thread(self, title):
        if getattr(self, "no_threads", False):
            raise RuntimeError("the chat is not a forum")
        self.next_thread += 1
        self.titles.append(title)
        return self.next_thread

    async def send(self, thread_id, text):
        self.sent.append((thread_id, text))
        self.events.append(("send", thread_id))


class FakeBrain:
    def __init__(self, events, store=None):
        self.events, self.store = events, store
        self.fail_challenge = False
        self.integrate_raises = None
        self.lang = "fr"
        self.forced = None
        self.last_usage = {"five_hour": 0.2, "seven_day": 0.3, "status": "allowed"}
        self.step = 0.0  # part de la fenetre de 5 h consommee par chaque challenge
        self.unknown_usage = False
        self.explore_calls = []
        self.challenge_calls = 0
        self.gate = None  # threading.Event : bloque le challenge tant qu'il n'est pas leve
        self.started = threading.Event()

    def challenge(self, fiche, force_lang=None):
        self.events.append("challenge")
        self.forced = force_lang
        self.challenge_calls += 1
        if self.store is not None:
            assert self.store.get(fiche.id) is not None  # le brouillon existe deja
        self.started.set()
        if self.gate:
            self.gate.wait(5)
        if self.fail_challenge:
            raise BrainUnavailable("recherche indisponible")
        self.last_usage = {**self.last_usage, "five_hour": self.last_usage["five_hour"] + self.step}
        n = len(fiche.objections) + 1
        return force_lang or self.lang, [Objection(f"O{n}", f"Objection {n} ?" if n > 1 else "Marché saturé ?", ["https://a.example"])]

    def usage(self):
        return None if self.unknown_usage else dict(self.last_usage)

    def explore(self, fiches, count):
        self.explore_calls.append(count)
        return [f"idée voisine {i}" for i in range(1, count + 1)]

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


def test_a_message_in_a_thread_without_a_fiche_opens_a_new_idea_in_that_thread(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée dans un fil créé par moi", 555)
        await service.drain()

    run(go())
    [fiche] = store.list()
    assert fiche.thread_id == 555 and fiche.raw_idea == "idée dans un fil créé par moi"
    assert messenger.next_thread == 100  # aucun nouveau fil créé : on réutilise celui de l'utilisateur
    assert all(thread == 555 for thread, _ in messenger.sent)



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


def test_an_english_fiche_gets_english_messages_and_a_french_one_french_messages(store):
    for lang, expected_start in (("en", "Objections:"), ("fr", "Objections :")):
        service, messenger, brain, _ = make(store)
        brain.lang = lang

        async def go():
            service.start()
            await service.on_message(OWNER, f"idea {lang}", None)
            await service.drain()

        run(go())
        assert messenger.sent[1][1].startswith(expected_start)


def test_before_the_language_is_known_the_acknowledgement_is_bilingual(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()

    run(go())
    ack = messenger.sent[0][1]
    assert "Idée enregistrée" in ack and "Idea saved" in ack


def test_newidea_alone_opens_a_thread_and_the_next_message_there_becomes_the_idea(store):
    service, messenger, brain, _ = make(store)
    seen = {}

    async def go():
        service.start()
        await service.on_message(OWNER, "/newidea", None)
        await service.drain()
        seen["after_command"] = (list(messenger.sent), store.list())
        await service.on_message(OWNER, "mon idée", 101)
        await service.drain()

    run(go())
    sent, fiches = seen["after_command"]
    assert fiches == []  # la commande seule ne crée pas de fiche
    assert sent == [(101, "Écris ton idée dans ce fil. / Write your idea in this thread.")]
    [fiche] = store.list()
    assert fiche.thread_id == 101 and fiche.raw_idea == "mon idée"
    assert messenger.titles == ["New idea"]  # aucun second fil


def test_newidea_with_text_creates_the_fiche_with_its_own_thread(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "/newidea Une app pour les syndics", 555)
        await service.drain()

    run(go())
    [fiche] = store.list()
    assert fiche.raw_idea == "Une app pour les syndics" and fiche.thread_id == 101


def test_commands_addressed_to_the_bot_by_name_are_understood(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "/newidea@olga_bot", None)
        await service.drain()

    run(go())
    assert messenger.titles == ["New idea"]


def test_newidea_without_topics_tells_the_owner_how_to_enable_them(store):
    service, messenger, brain, _ = make(store)
    messenger.no_threads = True

    async def go():
        service.start()
        await service.on_message(OWNER, "/newidea", None)
        await service.drain()

    run(go())
    assert store.list() == [] and "Threaded mode" in messenger.sent[0][1]


def test_rechallenge_adds_new_objections_keeps_old_ones_and_their_answers(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()
        await service.on_message(OWNER, "ma réponse", 101)
        await service.drain()
        messenger.sent.clear()
        brain.lang = "en"  # le cerveau change d'avis : la langue de la fiche ne doit pas bouger
        await service.on_message(OWNER, "/rechallenge", 101)
        await service.drain()

    run(go())
    fiche = store.find_by_thread(101)
    assert [o.id for o in fiche.objections] == ["O1", "O2"]
    assert fiche.objections[0].reponse == "ma réponse" and fiche.objections[1].reponse == ""
    assert fiche.lang == "fr" and brain.forced == "fr" and fiche.challenge == "fait"
    assert "O2. Objection 2" in messenger.sent[0][1] and "O1." not in messenger.sent[0][1]


def test_a_failed_rechallenge_does_not_undo_a_successful_challenge(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()
        brain.fail_challenge = True
        messenger.sent.clear()
        await service.on_message(OWNER, "/rechallenge", 101)
        await service.drain()

    run(go())
    fiche = store.find_by_thread(101)
    assert fiche.challenge == "fait" and len(fiche.objections) == 1
    assert "report" in messenger.sent[0][1].lower()


def test_rechallenge_outside_an_idea_thread_is_refused_politely(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "/rechallenge", None)
        await service.drain()

    run(go())
    assert store.list() == [] and "/rechallenge" in messenger.sent[0][1] and brain.challenge_calls == 0


def test_lang_switches_the_fiche_language_and_later_messages_follow(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()
        messenger.sent.clear()
        await service.on_message(OWNER, "/lang en", 101)
        await service.drain()
        await service.on_message(OWNER, "/prete", 101)
        await service.drain()

    run(go())
    assert store.find_by_thread(101).lang == "en"
    assert messenger.sent[0][1].startswith("Sheet language: English")
    assert messenger.sent[1][1].startswith("Sheet ready:")


def test_lang_with_a_wrong_argument_or_outside_a_thread_explains_usage(store):
    service, messenger, brain, _ = make(store)

    async def go():
        service.start()
        await service.on_message(OWNER, "idée", None)
        await service.drain()
        messenger.sent.clear()
        await service.on_message(OWNER, "/lang de", 101)
        await service.on_message(OWNER, "/lang", 101)
        await service.on_message(OWNER, "/lang fr", None)
        await service.drain()

    run(go())
    assert store.find_by_thread(101).lang == "fr"
    assert [("Usage" in m) or ("/lang" in m) for _, m in messenger.sent] == [True, True, True]


def explore_setup(store):
    base = store.create("idée de départ", thread_id=7)
    base.challenge = "fait"  # sinon le demarrage reprend son challenge et consomme du quota
    store.save(base)
    return make(store)


def run_explore(service, command="/explore"):
    async def go():
        service.start()
        await service.on_message(OWNER, command, None)
        await service.drain()

    run(go())


def test_explore_creates_neighbouring_ideas_each_with_a_thread_a_challenge_and_a_summary(store):
    service, messenger, brain, _ = explore_setup(store)
    run_explore(service)
    new = [f for f in store.list() if f.raw_idea.startswith("idée voisine")]
    assert sorted(f.raw_idea for f in new) == ["idée voisine 1", "idée voisine 2", "idée voisine 3"]
    assert all(f.thread_id and f.challenge == "fait" and f.objections for f in new)
    assert brain.explore_calls == [3]
    assert "Exploration terminée : 3" in messenger.sent[-1][1] and "5 h 20 %" in messenger.sent[-1][1]


def test_explore_takes_the_number_of_ideas_from_the_command(store):
    service, messenger, brain, _ = explore_setup(store)
    run_explore(service, "/explore 2")
    assert brain.explore_calls == [2] and len(store.list()) == 3


def test_explore_stops_when_the_five_hour_window_is_used_up(store):
    service, messenger, brain, _ = explore_setup(store)
    brain.step = 0.5  # 0.2 -> 0.7 -> 1.2 : epuisee apres la deuxieme idee
    run_explore(service, "/explore 5")
    assert len([f for f in store.list() if f.raw_idea.startswith("idée voisine")]) == 2
    assert "Arrêt" in messenger.sent[-1][1] and "Exploration terminée : 2" in messenger.sent[-1][1]


def test_explore_may_use_the_whole_five_hour_window_but_not_a_used_up_one(store):
    service, messenger, brain, _ = explore_setup(store)
    brain.last_usage = {"five_hour": 0.99, "seven_day": 0.1, "status": "allowed"}  # 99 % : on explore encore
    run_explore(service, "/explore 1")
    assert brain.explore_calls == [1]

    service, messenger, brain, _ = explore_setup(store)
    brain.last_usage = {"five_hour": 0.5, "seven_day": 0.1, "status": "rejected"}  # refuse par Claude : on n'explore pas
    run_explore(service, "/explore 1")
    assert brain.explore_calls == [] and "Quota" in messenger.sent[-1][1]


def test_explore_does_not_start_when_the_weekly_limit_is_reached(store):
    service, messenger, brain, _ = explore_setup(store)
    brain.last_usage = {"five_hour": 0.1, "seven_day": 0.9, "status": "allowed"}
    run_explore(service)
    assert brain.explore_calls == [] and "85 %" in messenger.sent[-1][1] and "90 %" in messenger.sent[-1][1]


def test_explore_does_not_start_when_the_quota_cannot_be_read(store):
    service, messenger, brain, _ = explore_setup(store)
    brain.unknown_usage = True
    run_explore(service)
    assert brain.explore_calls == [] and "quota" in messenger.sent[-1][1].lower()


def test_explore_needs_at_least_one_fiche(store):
    service, messenger, brain, _ = make(store)
    run_explore(service)
    assert brain.explore_calls == [] and "au moins une fiche" in messenger.sent[-1][1]


def test_explore_rejects_a_bad_count(store):
    service, messenger, brain, _ = explore_setup(store)
    run_explore(service, "/explore 50")
    assert brain.explore_calls == [] and "Usage" in messenger.sent[-1][1]
