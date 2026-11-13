"""Une fiche = un fichier Markdown : en-tete YAML puis sections fixes."""
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

import yaml

# Titres de sections et libelles fixes, par langue de la fiche (choisie selon le sujet de l'idee).
LABELS = {
    "fr": {"raw": "Idée brute", "problem": "Problème", "target": "Cible", "idea": "Idée",
           "obj": "Objections et réponses", "questions": "Questions ouvertes", "sources": "Sources :", "answer": "Réponse :"},
    "en": {"raw": "Raw idea", "problem": "Problem", "target": "Target", "idea": "Idea",
           "obj": "Objections and answers", "questions": "Open questions", "sources": "Sources:", "answer": "Answer:"},
}
DEFAULT_LANG = "en"
LEGACY_LANG = "fr"  # les fiches ecrites avant ce choix n'ont pas de langue et sont en francais

# Valeurs ecrites dans l'en-tete des fiches (statut, puis etat du challenge).
DRAFT, READY = "brouillon", "prete"
CHALLENGE_PENDING, CHALLENGE_DONE, CHALLENGE_FAILED = "en_cours", "fait", "echec"


@dataclass
class Objection:
    id: str
    texte: str
    sources: list = field(default_factory=list)
    reponse: str = ""


@dataclass
class Fiche:
    id: str
    title: str
    raw_idea: str
    problem: str = ""
    target: str = ""
    idea: str = ""
    objections: list = field(default_factory=list)
    open_questions: list = field(default_factory=list)
    themes: list = field(default_factory=list)
    thread_id: int | None = None
    status: str = DRAFT
    challenge: str = CHALLENGE_PENDING
    lang: str = DEFAULT_LANG
    created: str = ""
    updated: str = ""

    @classmethod
    def new(cls, raw_idea, thread_id=None):
        now = datetime.now(timezone.utc)
        stamp = now.isoformat(timespec="seconds")
        return cls(
            id=f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}",
            title=title_of(raw_idea), raw_idea=raw_idea, thread_id=thread_id, created=stamp, updated=stamp,
        )


def title_of(raw_idea):
    lines = raw_idea.strip().splitlines()
    return (lines[0][:60] if lines else "") or "Idée sans titre"


def _oneline(text):
    return " ".join(text.split())


def _esc(text):
    # Une ligne qui commence par # ne doit pas etre prise pour un titre de section.
    return "\n".join("\\" + l if l.startswith("#") else l for l in text.splitlines())


def _unesc(text):
    return "\n".join(l[1:] if l.startswith("\\#") else l for l in text.splitlines())


def render(f):
    L = LABELS[f.lang]
    meta = {
        "id": f.id, "title": f.title, "status": f.status, "challenge": f.challenge, "lang": f.lang,
        "themes": f.themes, "created": f.created, "updated": f.updated, "telegram_thread_id": f.thread_id,
    }
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    raw = "\n".join(("> " + l) if l else ">" for l in f.raw_idea.splitlines())
    objs = []
    for o in f.objections:
        block = [f"### {o.id}. {_oneline(o.texte)}", "", f"**{L['sources']}**"]
        block += [f"- {u}" for u in o.sources]
        block += ["", f"**{L['answer']}** {_esc(o.reponse)}"]
        objs.append("\n".join(block))
    parts = [
        f"---\n{head}---", f"# {_oneline(f.title)}",
        f"## {L['raw']}\n{raw}",
        f"## {L['problem']}\n{_esc(f.problem)}",
        f"## {L['target']}\n{_esc(f.target)}",
        f"## {L['idea']}\n{_esc(f.idea)}",
        f"## {L['obj']}\n" + "\n\n".join(objs),
        f"## {L['questions']}\n" + "\n".join(f"- {_esc(q)}" for q in f.open_questions),
    ]
    return "\n\n".join(parts) + "\n"


def parse(text):
    _, head, body = text.split("---\n", 2)
    meta = yaml.safe_load(head)
    lang = meta.get("lang") or LEGACY_LANG
    L = LABELS[lang]
    sections, current = {}, None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    def block(name):
        return "\n".join(sections.get(name, [])).strip("\n")

    raw = "\n".join(l[2:] if l.startswith("> ") else "" for l in block(L["raw"]).splitlines())
    objections = []
    for chunk in re.split(r"(?m)^### ", block(L["obj"]))[1:]:
        heading, _, rest = chunk.partition("\n")
        oid, _, texte = heading.partition(". ")
        src_part, _, rep_part = rest.partition(f"**{L['answer']}**")
        sources = [l[2:].strip() for l in src_part.splitlines() if l.startswith("- ")]
        objections.append(Objection(oid, texte, sources, _unesc(rep_part.strip("\n ")) if rep_part.strip() else ""))
    questions = [_unesc(l[2:]) for l in block(L["questions"]).splitlines() if l.startswith("- ")]
    return Fiche(
        id=meta["id"], title=meta["title"], raw_idea=raw,
        problem=_unesc(block(L["problem"])), target=_unesc(block(L["target"])), idea=_unesc(block(L["idea"])),
        objections=objections, open_questions=questions, themes=list(meta.get("themes") or []),
        thread_id=meta.get("telegram_thread_id"), status=meta["status"], challenge=meta["challenge"], lang=lang,
        created=meta.get("created") or "", updated=meta.get("updated") or "",
    )
