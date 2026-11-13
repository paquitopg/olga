import pytest
from fastapi.testclient import TestClient

from ideadesk.fiche import Objection
from ideadesk.web import create_app, hash_password

PASSWORD = "correct horse battery"


@pytest.fixture
def client(store):
    app = create_app(store, hash_password(PASSWORD), "session-secret")
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


@pytest.fixture
def fiches(store):
    draft = store.create("Une idée de brouillon")
    draft.title, draft.themes = "Titre du brouillon", ["SaaS"]
    store.save(draft)
    ready = store.create("Une idée prête")
    ready.title, ready.status, ready.themes = "Titre de la prête", "prete", ["immobilier"]
    ready.objections = [Objection("O1", "Marché ?", ["https://a.example/x", "javascript:alert(1)"], "Oui")]
    store.save(ready)
    return draft, ready


def login(client, password=PASSWORD, **params):
    return client.post("/login", data={"password": password}, params=params)


def test_without_login_the_list_and_a_fiche_show_nothing(client, fiches):
    for path in ("/", f"/fiche/{fiches[0].id}"):
        res = client.get(path)
        assert res.status_code == 303 and res.headers["location"] == "/login"
        assert "Titre" not in res.text


def test_wrong_password_is_refused_and_too_many_tries_are_blocked(client):
    for _ in range(5):
        assert login(client, "mauvais").status_code == 401
    assert login(client).status_code == 429


def test_good_password_gives_access_and_logout_removes_it(client, fiches):
    assert login(client).status_code == 303
    assert "Titre du brouillon" in client.get("/").text
    client.post("/logout")
    assert client.get("/").status_code == 303


def test_login_never_follows_a_requested_return_address(client):
    res = login(client, next="https://autre-site.example")
    assert res.status_code == 303 and res.headers["location"] == "/"


def test_list_filters_by_status_and_by_theme(client, fiches):
    login(client)
    drafts = client.get("/", params={"statut": "brouillon"}).text
    assert "Titre du brouillon" in drafts and "Titre de la prête" not in drafts
    ready = client.get("/", params={"statut": "prete"}).text
    assert "Titre de la prête" in ready and "Titre du brouillon" not in ready
    themed = client.get("/", params={"theme": "saas"}).text
    assert "Titre du brouillon" in themed and "Titre de la prête" not in themed


def test_fiche_text_is_inert_and_only_http_sources_become_links(client, store, fiches):
    draft, ready = fiches
    draft.problem = "<script>alert(1)</script> et [clic](javascript:alert(1))"
    store.save(draft)
    login(client)
    page = client.get(f"/fiche/{draft.id}").text
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert 'href="javascript:' not in page
    sources = client.get(f"/fiche/{ready.id}").text
    assert 'href="https://a.example/x"' in sources and 'rel="noopener noreferrer nofollow"' in sources
    assert 'href="javascript:' not in sources


def test_healthz_is_open_and_reveals_nothing_and_pages_are_not_indexable(client, fiches):
    res = client.get("/healthz")
    assert res.status_code == 200 and "Titre" not in res.text
    assert "noindex" in client.get("/login").headers["x-robots-tag"]
    assert "Disallow: /" in client.get("/robots.txt").text


def test_failed_logins_from_one_client_do_not_lock_out_another(client):
    for _ in range(5):
        client.post("/login", data={"password": "mauvais"}, headers={"X-Forwarded-For": "203.0.113.5"})
    assert client.post("/login", data={"password": PASSWORD}, headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 429
    assert client.post("/login", data={"password": PASSWORD}, headers={"X-Forwarded-For": "198.51.100.7"}).status_code == 303


def test_unknown_or_odd_fiche_ids_are_404_when_logged_in(client, fiches):
    login(client)
    for fiche_id in ("inconnue", "a.b", "..%2F..%2Fetc%2Fpasswd"):
        assert client.get(f"/fiche/{fiche_id}").status_code == 404


def test_pages_forbid_remote_resources(client):
    csp = client.get("/login").headers["content-security-policy"]
    assert "img-src 'self'" in csp and "default-src 'none'" in csp


def test_the_fiche_page_uses_the_headings_of_its_language(client, store, fiches):
    draft, ready = fiches
    login(client)
    english = client.get(f"/fiche/{draft.id}").text
    assert "<h2>Raw idea</h2>" in english and "<h2>Open questions</h2>" in english
    draft.lang = "fr"
    store.save(draft)
    assert "<h2>Idée brute</h2>" in client.get(f"/fiche/{draft.id}").text
