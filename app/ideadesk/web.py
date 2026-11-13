"""Le site prive : connexion unique, liste filtrable, fiche. Lecture seule sur les fiches."""
import getpass
import hashlib
import hmac
import os
import sys
import time
from collections import deque
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from starlette.middleware.sessions import SessionMiddleware

from .fiche import DRAFT, READY
from .store import themes_of

TEMPLATES = Path(__file__).parent / "templates"
MAX_FAILURES, WINDOW = 5, 300
SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def _check(password, stored):
    try:
        _, salt, digest = stored.split("$")
        expected = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT)
    except ValueError:
        return False
    return hmac.compare_digest(expected.hex(), digest)


def create_app(store, password_hash, session_secret):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=session_secret, https_only=True, same_site="lax", max_age=30 * 86400)
    templates = Jinja2Templates(directory=str(TEMPLATES))
    markdown = MarkdownIt("commonmark", {"html": False})  # HTML brut desactive : le contenu vient en partie du web
    templates.env.filters["md"] = lambda text: markdown.render(text or "")
    failures = deque()  # shortcut: compteur en memoire, un seul utilisateur ; a revoir si le site en servait plusieurs.

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Cache-Control"] = "no-store"
        return response

    def need_login(request: Request):
        if not request.session.get("ok"):
            raise HTTPException(status_code=303, headers={"Location": "/login"})

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz():
        return "ok"

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots():
        return "User-agent: *\nDisallow: /\n"

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return templates.TemplateResponse(request, "login.html", {"error": False})

    @app.post("/login")
    def login(request: Request, password: str = Form("")):
        now = time.time()
        while failures and now - failures[0] > WINDOW:
            failures.popleft()
        if len(failures) >= MAX_FAILURES:
            return templates.TemplateResponse(request, "login.html", {"error": True}, status_code=429)
        if not _check(password, password_hash):
            failures.append(now)
            return templates.TemplateResponse(request, "login.html", {"error": True}, status_code=401)
        failures.clear()
        request.session["ok"] = True
        return RedirectResponse("/", status_code=303)

    @app.post("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(need_login)])
    def index(request: Request, statut: str = "", theme: str = ""):
        all_fiches = store.list()
        fiches = all_fiches
        if statut in (DRAFT, READY):
            fiches = [f for f in fiches if f.status == statut]
        if theme:
            fiches = [f for f in fiches if theme.lower() in (t.lower() for t in f.themes)]
        return templates.TemplateResponse(
            request, "index.html", {"fiches": fiches, "themes": themes_of(all_fiches), "statut": statut, "theme": theme})

    @app.get("/fiche/{fiche_id}", response_class=HTMLResponse, dependencies=[Depends(need_login)])
    def fiche_page(request: Request, fiche_id: str):
        fiche = store.get(fiche_id) if fiche_id.replace("-", "").isalnum() else None
        if fiche is None:
            raise HTTPException(status_code=404)
        return templates.TemplateResponse(request, "fiche.html", {"fiche": fiche})

    return app


if __name__ == "__main__" and sys.argv[1:] == ["hash"]:
    # Usage : python -m ideadesk.web hash  (le mot de passe est saisi sans echo)
    print(hash_password(getpass.getpass("Mot de passe du site : ")))
