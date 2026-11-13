"""Le cerveau : Claude Code scripte, avec les seuls outils web. L'application ecrit seule les fichiers."""
import dataclasses
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from string import Template

from .fiche import Objection

PROMPTS = Path(__file__).parent / "prompts"
WEB_TOOLS = "WebSearch,WebFetch"
URL = re.compile(r"https?://\S+")  # une seule ligne : une source ne peut pas ajouter de sections a la fiche


class BrainUnavailable(Exception):
    """Le challenge ou l'integration n'a pas pu etre fait (recherche, quota, delai, sortie illisible)."""


class Brain:
    def __init__(self, claude_bin, model, token, api_key, timeout=600):
        self.claude_bin, self.model, self.token, self.api_key, self.timeout = claude_bin, model, token, api_key, timeout

    def _env(self):
        # Seuls PATH, HOME et le credential Claude : les autres secrets du service ne passent pas.
        env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
        if self.token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self.token
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key
        return env

    def _json(self, prompt, tools):
        cmd = [
            self.claude_bin, "-p", "--output-format", "json", "--model", self.model,
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
        try:
            envelope = json.loads(done.stdout)
        except ValueError:
            raise BrainUnavailable("sortie illisible")
        if done.returncode != 0 or not isinstance(envelope, dict) or envelope.get("is_error"):
            raise BrainUnavailable("claude a signalé une erreur")
        text = str(envelope.get("result", ""))
        start, end = text.find("{"), text.rfind("}")
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            raise BrainUnavailable("réponse sans JSON")
        if not isinstance(data, dict):
            raise BrainUnavailable("réponse inattendue")
        return data

    def challenge(self, fiche):
        prompt = Template((PROMPTS / "challenge.md").read_text()).substitute(IDEE=fiche.raw_idea)
        data = self._json(prompt, WEB_TOOLS)
        found = []
        for item in data.get("objections") or []:
            if not isinstance(item, dict):
                continue
            sources = [u for u in item.get("sources") or [] if isinstance(u, str) and URL.fullmatch(u)]
            texte = str(item.get("texte", "")).strip()
            if texte and sources:
                found.append(Objection(f"O{len(found) + 1}", texte, sources))
        if not found:
            raise BrainUnavailable("aucune objection sourcée")
        return found

    def integrate(self, fiche, answer, themes):
        state = {
            "idee_brute": fiche.raw_idea, "probleme": fiche.problem, "cible": fiche.target, "idee": fiche.idea,
            "objections": [{"id": o.id, "texte": o.texte, "reponse": o.reponse} for o in fiche.objections],
            "questions_ouvertes": fiche.open_questions,
        }
        prompt = Template((PROMPTS / "integrate.md").read_text()).substitute(
            FICHE=json.dumps(state, ensure_ascii=False), REPONSE=answer, THEMES=", ".join(themes) or "aucun")
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
