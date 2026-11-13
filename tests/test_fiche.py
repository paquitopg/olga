from ideadesk.fiche import Fiche, Objection, parse, render

RAW = "Une app pour les copropriétés.\n## Un titre dans l'idée\nVoir https://exemple.fr/é?a=1&b=2"


def sample():
    return Fiche(
        id="20261113-120000-ab12",
        title="Copropriétés",
        raw_idea=RAW,
        problem="Les syndics sont opaques.\n# pas un vrai titre",
        target="Copropriétaires",
        idea="Un tableau de bord partagé.",
        objections=[
            Objection(id="O1", texte="Marché saturé ?", sources=["https://a.example/x", "https://b.example/y"], reponse="Non : niche des petites copropriétés.\nSur deux lignes."),
            Objection(id="O2", texte="Réglementation ?", sources=["https://c.example/z"], reponse=""),
        ],
        open_questions=["Quel prix ?", "Quel canal ?"],
        themes=["immobilier", "SaaS"],
        thread_id=77,
    )


def test_roundtrip_keeps_accents_links_and_headings_in_text():
    original = sample()
    again = parse(render(original))
    assert again == original


def test_new_fiche_is_a_draft_with_challenge_in_progress_and_empty_sections():
    fiche = Fiche.new(raw_idea="Mon idée", thread_id=5)
    assert fiche.status == "brouillon"
    assert fiche.challenge == "en_cours"
    assert fiche.raw_idea == "Mon idée"
    assert fiche.problem == fiche.target == fiche.idea == ""
    assert fiche.objections == [] and fiche.open_questions == []


def test_marking_ready_changes_only_the_status():
    fiche = sample()
    ready = parse(render(fiche))
    ready.status = "prete"
    reread = parse(render(ready))
    assert reread.status == "prete"
    assert (reread.raw_idea, reread.problem, reread.objections) == (fiche.raw_idea, fiche.problem, fiche.objections)


def test_two_new_fiches_get_distinct_ids():
    assert Fiche.new("a").id != Fiche.new("b").id


def test_english_headings_roundtrip_and_a_fiche_without_language_is_french():
    english = sample()
    english.lang = "en"
    text = render(english)
    assert "## Raw idea" in text and "## Objections and answers" in text and "**Answer:**" in text
    assert parse(text) == english

    french = sample()
    french.lang = "fr"
    legacy = render(french).replace("lang: fr\n", "")
    assert "## Idée brute" in legacy and parse(legacy).lang == "fr"
