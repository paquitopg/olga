"""Le cerveau : Claude Code scripte, avec les seuls outils web. L'application ecrit seule les fichiers."""
import dataclasses
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from string import Template

from .fiche import DEFAULT_LANG, LABELS, Objection

PROMPTS = Path(__file__).parent / "prompts"
WEB_TOOLS = "WebSearch,WebFetch"
URL = re.compile(r"https?://\S+")  # une seule ligne : une source ne peut pas ajouter de sections a la fiche


LANG_NAME = {"fr": "French", "en": "English"}
LANG_AUTO = 'Choose the output language from the SUBJECT of the idea, not from the language it was written in: "fr" (French) when the subject concerns France (the French market, French law or institutions, a French-speaking audience), otherwise "en" (English). Write every objection in that language.'


class BrainUnavailable(Exception):
    """Le challenge ou l'integration n'a pas pu etre fait (recherche, quota, delai, sortie illisible)."""


class Brain:
    def __init__(self, claude_bin, model, token, api_key, timeout=600):
        self.claude_bin, self.model, self.token, self.api_key, self.timeout = claude_bin, model, token, api_key, timeout
        self.last_usage = None  # {"five_hour": 0..1, "seven_day": 0..1, "status": "allowed"|...} lu dans le dernier appel

    def _env(self):
        # Seuls PATH, HOME et le credential Claude : les autres secrets du service ne passent pas.
        env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
        if self.token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self.token
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key
        return env

    def _note_usage(self, info):
        windows = (info or {}).get("unifiedWindows") or {}

        def share(name):
            value = (windows.get(name) or {}).get("utilization")
            return float(value) if isinstance(value, (int, float)) else None

        self.last_usage = {"five_hour": share("five_hour"), "seven_day": share("seven_day"), "status": (info or {}).get("status")}

    def _run(self, prompt, tools):
        cmd = [
            self.claude_bin, "-p", "--output-format", "stream-json", "--verbose", "--model", self.model,
            "--tools", tools, "--permission-mode", "dontAsk", "--safe-mode", "--no-session-persistence",
        ]
        if tools:
            cmd += ["--allowedTools", tools]
        with tempfile.TemporaryDirectory() as cwd:
            try:
                done = subprocess.run(cmd, input=prompt, cwd=cwd, env=self._env(), capture_output=True, text=True, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                raise BrainUnavailable("délai dépassé")
            except OSError as err:
                raise BrainUnavailable(f"claude introuvable ({err.strerror})")
        envelope = None
        for line in done.stdout.splitlines():  # un evenement JSON par ligne : le quota, puis le resultat
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "rate_limit_event":
                self._note_usage(event.get("rate_limit_info"))
            elif isinstance(event, dict) and event.get("type") == "result":
                envelope = event
        if envelope is None:
            raise BrainUnavailable("sortie illisible")
        if done.returncode != 0 or envelope.get("is_error"):
            raise BrainUnavailable("claude a signalé une erreur")
        return str(envelope.get("result", ""))

    def usage(self):
        """Quota restant d'apres un appel minimal ; None si Claude ne l'a pas indique."""
        self.last_usage = None
        try:
            self._run("Reply with the single word ok.", "")
        except BrainUnavailable:
            pass  # quota epuise : l'evenement de limite arrive quand meme avant l'erreur
        return self.last_usage

    def _json(self, prompt, tools):
        text = self._run(prompt, tools)
        start, end = text.find("{"), text.rfind("}")
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            raise BrainUnavailable("réponse sans JSON")
        if not isinstance(data, dict):
            raise BrainUnavailable("réponse inattendue")
        return data

    def explore(self, fiches, count):
        """Renvoie jusqu'a `count` idees voisines de celles des fiches, sous forme de textes d'idee bruts."""
        lines = []
        for f in fiches:
            gist = (f.idea or f.problem or f.raw_idea).strip().replace("\n", " ")[:160]
            lines.append(f"- {f.title} [{', '.join(f.themes) or '-'}]: {gist}")
        prompt = Template((PROMPTS / "explore.md").read_text()).substitute(COUNT=count, FICHES="\n".join(lines))
        data = self._json(prompt, "")
        try:
            ideas = [str(i["idee"]).strip() for i in data["ideas"] if isinstance(i, dict) and str(i.get("idee", "")).strip()]
        except (KeyError, TypeError):
            raise BrainUnavailable("réponse incomplète")
        if not ideas:
            raise BrainUnavailable("aucune idée proposée")
        return ideas[:count]

    def challenge(self, fiche, force_lang=None):
        """Renvoie (langue, objections). Sans `force_lang`, le cerveau choisit la langue (fr ou en) selon le sujet.

        Les nouvelles objections continuent la numerotation de celles deja posees, qu'il ne doit pas repeter."""
        rule = LANG_AUTO if not force_lang else f"Write every objection in {LANG_NAME[force_lang]}."
        deja = " | ".join(o.texte for o in fiche.objections) or "none"
        prompt = Template((PROMPTS / "challenge.md").read_text()).substitute(IDEE=fiche.raw_idea, LANGUE_RULE=rule, DEJA=deja)
        data = self._json(prompt, WEB_TOOLS)
        lang = force_lang or (data.get("langue") if data.get("langue") in LABELS else DEFAULT_LANG)
        found = []
        for item in data.get("objections") or []:
            if not isinstance(item, dict):
                continue
            sources = [u for u in item.get("sources") or [] if isinstance(u, str) and URL.fullmatch(u)]
            texte = str(item.get("texte", "")).strip()
            if texte and sources:
                found.append(Objection(f"O{len(fiche.objections) + len(found) + 1}", texte, sources))
        if not found:
            raise BrainUnavailable("aucune objection sourcée")
        return lang, found

    def integrate(self, fiche, answer, themes):
        state = {
            "idee_brute": fiche.raw_idea, "probleme": fiche.problem, "cible": fiche.target, "idee": fiche.idea,
            "objections": [{"id": o.id, "texte": o.texte, "reponse": o.reponse} for o in fiche.objections],
            "questions_ouvertes": fiche.open_questions,
        }
        prompt = Template((PROMPTS / "integrate.md").read_text()).substitute(
            FICHE=json.dumps(state, ensure_ascii=False), REPONSE=answer, THEMES=", ".join(themes) or "none",
            LANGUE=LANG_NAME[fiche.lang])
        data = self._json(prompt, "")
        needed = ("probleme", "cible", "idee", "reponses", "questions_ouvertes", "themes")
        if any(k not in data for k in needed):
            raise BrainUnavailable("réponse incomplète")
        try:
            answers = {r.get("objection_id"): str(r.get("reponse", "")) for r in data["reponses"] if isinstance(r, dict)}
            questions = [str(q) for q in data["questions_ouvertes"]]
            themes = [str(t).strip() for t in data["themes"] if str(t).strip()][:3]
        except TypeError:  # une liste attendue valait null
            raise BrainUnavailable("réponse incomplète")
        # Une réponse vide ne doit pas effacer la réponse précédente.
        objections = [dataclasses.replace(o, reponse=answers.get(o.id) or o.reponse) for o in fiche.objections]
        return dataclasses.replace(
            fiche, problem=str(data["probleme"]), target=str(data["cible"]), idea=str(data["idee"]),
            objections=objections, open_questions=questions, themes=themes,
        )
