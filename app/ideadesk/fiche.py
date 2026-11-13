"""Une fiche = un fichier Markdown : en-tete YAML puis sections fixes."""
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

import yaml

S_RAW, S_PROBLEM, S_TARGET, S_IDEA = "Idée brute", "Problème", "Cible", "Idée"
S_OBJ, S_QUESTIONS = "Objections et réponses", "Questions ouvertes"


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
    status: str = "brouillon"
    challenge: str = "en_cours"
    created: str = ""
    updated: str = ""

    @classmethod
    def new(cls, raw_idea, thread_id=None):
        now = datetime.now(timezone.utc)
        first_line = raw_idea.strip().splitlines()[0] if raw_idea.strip() else ""
        title = first_line[:60] or "Idée sans titre"
        stamp = now.isoformat(timespec="seconds")
        return cls(
            id=f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}",
            title=title, raw_idea=raw_idea, thread_id=thread_id, created=stamp, updated=stamp,
        )


def _esc(text):
    # Une ligne qui commence par # ne doit pas etre prise pour un titre de section.
    return "\n".join("\\" + l if l.startswith("#") else l for l in text.splitlines())


def _unesc(text):
    return "\n".join(l[1:] if l.startswith("\\#") else l for l in text.splitlines())


def render(f):
    meta = {
        "id": f.id, "title": f.title, "status": f.status, "challenge": f.challenge,
        "themes": f.themes, "created": f.created, "updated": f.updated, "telegram_thread_id": f.thread_id,
    }
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    raw = "\n".join(("> " + l) if l else ">" for l in f.raw_idea.splitlines())
    objs = []
    for o in f.objections:
        block = [f"### {o.id}. {' '.join(o.texte.split())}", "", "**Sources :**"]
        block += [f"- {u}" for u in o.sources]
        block += ["", f"**Réponse :** {_esc(o.reponse)}"]
        objs.append("\n".join(block))
    parts = [
        f"---\n{head}---", f"# {' '.join(f.title.split())}",
        f"## {S_RAW}\n{raw}",
        f"## {S_PROBLEM}\n{_esc(f.problem)}",
        f"## {S_TARGET}\n{_esc(f.target)}",
        f"## {S_IDEA}\n{_esc(f.idea)}",
        f"## {S_OBJ}\n" + "\n\n".join(objs),
        f"## {S_QUESTIONS}\n" + "\n".join(f"- {_esc(q)}" for q in f.open_questions),
    ]
    return "\n\n".join(parts) + "\n"


def parse(text):
    _, head, body = text.split("---\n", 2)
    meta = yaml.safe_load(head)
    sections, current = {}, None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    def block(name):
        return "\n".join(sections.get(name, [])).strip("\n")

    raw = "\n".join(l[2:] if l.startswith("> ") else "" for l in block(S_RAW).splitlines())
    objections = []
    for chunk in re.split(r"(?m)^### ", block(S_OBJ))[1:]:
        heading, _, rest = chunk.partition("\n")
        oid, _, texte = heading.partition(". ")
        src_part, _, rep_part = rest.partition("**Réponse :**")
        sources = [l[2:].strip() for l in src_part.splitlines() if l.startswith("- ")]
        objections.append(Objection(oid, texte, sources, _unesc(rep_part.strip("\n ")) if rep_part.strip() else ""))
    questions = [_unesc(l[2:]) for l in block(S_QUESTIONS).splitlines() if l.startswith("- ")]
    return Fiche(
        id=meta["id"], title=meta["title"], raw_idea=raw,
        problem=_unesc(block(S_PROBLEM)), target=_unesc(block(S_TARGET)), idea=_unesc(block(S_IDEA)),
        objections=objections, open_questions=questions, themes=list(meta.get("themes") or []),
        thread_id=meta.get("telegram_thread_id"), status=meta["status"], challenge=meta["challenge"],
        created=meta.get("created") or "", updated=meta.get("updated") or "",
    )
