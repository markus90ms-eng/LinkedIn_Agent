import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from linkedin_agent import db, drafts, linkedin
from linkedin_agent.web import make_handler


@pytest.fixture
def app(tmp_path, monkeypatch):
    cfg = {"db_path": str(tmp_path / "t.db"), "model": "m", "voice": "v", "topics": ["A"], "feeds": [], "drafts_per_run": 2}
    conn = db.connect(cfg["db_path"])
    db.add_draft(conn, "Erster <b>Post</b>", "A")
    db.add_draft(conn, "Zweiter Post", "A")
    published = []
    monkeypatch.setattr(linkedin, "publish", lambda text, *a: published.append(text) or "urn:li:share:1")
    monkeypatch.setattr(drafts, "generate_text", lambda cfg, topic, **kw: "Neu generiert")
    monkeypatch.setattr(drafts, "revise", lambda cfg, text, ins: text + " | " + ins)
    server = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = server.server_address[1]
    server.RequestHandlerClass = make_handler(cfg, "tok", port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", cfg, published
    server.shutdown()


def post(base, path, **form):
    data = urllib.parse.urlencode({"token": "tok", **form}).encode()
    return urllib.request.urlopen(urllib.request.Request(base + path, data=data)).read().decode()


def test_shows_next_post_escaped(app):
    page = urllib.request.urlopen(app[0] + "/").read().decode()
    assert "Erster &lt;b&gt;Post&lt;/b&gt;" in page and "1 weitere" in page


def test_post_publishes_once_and_advances(app):
    base, cfg, published = app
    page = post(base, "/post", id="1", text="Endtext")
    assert published == ["Endtext"] and "Zweiter Post" in page
    again = post(base, "/post", id="1", text="Endtext")
    assert published == ["Endtext"] and "nicht mehr offen" in again


def test_regenerate_revise_reject(app):
    base, cfg, _ = app
    assert "Neu generiert" in post(base, "/regenerate", id="1")
    assert "Neu generiert | kürzer" in post(base, "/revise", id="1", instruction="kürzer")
    assert "Zweiter Post" in post(base, "/reject", id="1")


def test_rejects_bad_token(app):
    data = urllib.parse.urlencode({"token": "x", "id": "1"}).encode()
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(urllib.request.Request(app[0] + "/reject", data=data))
    assert e.value.code == 403
