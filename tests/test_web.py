import os
import threading
from types import SimpleNamespace
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


def _png_data_url():
    import base64, io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (40, 30), "#3366cc").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _jpg_data_url():
    import base64, io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (40, 30), "#cc6633").save(buf, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def test_upload_preview_post_and_remove(app, monkeypatch):
    base, cfg, published = app
    sent = []
    monkeypatch.setattr(linkedin, "publish", lambda text, image=None, alt=None: sent.append((text, image, alt)) or "urn:li:share:2")
    page = post(base, "/upload", id="1", text="Text", upload=_jpg_data_url(), alt="Ein oranges Bild")
    assert "Bild hochgeladen" in page and 'src="/img/1.jpg' in page and 'data-kind="file"' in page and "Eigenes Bild" in page
    assert urllib.request.urlopen(base + "/img/1.jpg").read(3) == b"\xff\xd8\xff"
    post(base, "/post", id="1", text="Text", with_image="1")
    assert sent[0][0] == "Text" and sent[0][1].endswith("1.upload.jpg") and sent[0][2] == "Ein oranges Bild"


def test_upload_rejects_wrong_files_and_remove_deletes(app):
    base, cfg, _ = app
    assert "Fehler" in post(base, "/upload", id="1", text="T", upload="data:image/png;base64,AAAA")
    assert "Fehler" in post(base, "/upload", id="1", text="T", upload="data:text/html;base64,PHNjcmlwdD4=")
    post(base, "/upload", id="1", text="T", upload=_png_data_url())
    path = os.path.join(os.path.dirname(cfg["db_path"]), "images", "1.upload.png")
    assert os.path.exists(path)
    post(base, "/imageremove", id="1", text="T")
    assert not os.path.exists(path)


def test_post_without_image_checkbox_sends_text_only(app, monkeypatch):
    base, cfg, _ = app
    sent = []
    monkeypatch.setattr(linkedin, "publish", lambda text, image=None, alt=None: sent.append(image) or "urn:li:share:3")
    post(base, "/upload", id="1", text="T", upload=_png_data_url())
    post(base, "/post", id="1", text="T")
    assert sent == [None]


def test_image_prompt_is_separate_and_never_posted(app, monkeypatch):
    base, cfg, published = app
    from linkedin_agent import images
    calls = []
    monkeypatch.setattr(images, "make_prompt", lambda cfg, text, previous=None, instruction=None, client=None:
                        calls.append((text, previous, instruction)) or ("Neuer Bildwunsch" if not previous else previous + " + " + instruction))
    page = post(base, "/promptnew", id="1", text="Aktueller Text im Feld", prompt_text="", instruction="wird ignoriert")
    assert "Neuer Bildwunsch" in page and "NICHT mitgepostet" in page
    assert calls[0] == ("Aktueller Text im Feld", None, None)              # Text aus dem Feld, Anweisung bei „neu“ ignoriert
    assert "Aktueller Text im Feld" in page                                # Text wurde mitgespeichert, nichts geht verloren
    page = post(base, "/prompt", id="1", text="Aktueller Text im Feld", prompt_text="Neuer Bildwunsch", instruction="ohne Personen")
    assert "Neuer Bildwunsch + ohne Personen" in page and calls[1][1:] == ("Neuer Bildwunsch", "ohne Personen")
    assert "Fehler" in post(base, "/prompt", id="1", text="x", prompt_text="", instruction="egal")   # Anpassen ohne Wunsch
    post(base, "/promptsave", id="1", text="x", prompt_text="Von Hand geändert")
    assert "Von Hand geändert" in urllib.request.urlopen(base + "/").read().decode()
    post(base, "/post", id="1", text="Nur der Posttext")
    assert published == ["Nur der Posttext"]                              # der Bildwunsch ist nicht im Post


def test_make_prompt_uses_style_and_cleans_output():
    from linkedin_agent import images
    seen = {}

    class C:
        messages = SimpleNamespace(create=lambda **kw: seen.update(kw) or SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text='"Erstelle ein quadratisches Bild (1:1): ein Büro."')]))
    out = images.make_prompt({"model": "m", "image_prompt_style": "Aquarell"}, "**Hook**\n\nText", client=C())
    assert out == "Erstelle ein quadratisches Bild (1:1): ein Büro." and "Aquarell" in seen["system"] and "**" not in seen["messages"][0]["content"]
    images.make_prompt({"model": "m"}, "Text", previous="alt", instruction="heller", client=C())
    assert "Bisheriger Bildwunsch:\nalt" in seen["messages"][0]["content"] and "heller" in seen["messages"][0]["content"]
