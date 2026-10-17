import json
from types import SimpleNamespace

import pytest

from linkedin_agent import db, images, linkedin


def test_parse_spec_strips_codeblock_and_limits():
    spec = images.parse_spec('```json\n{"kicker":"K","headline":"Kern","points":["a","b","c","d"]}\n```')
    assert spec["headline"] == "Kern" and spec["points"] == ["a", "b", "c"]
    with pytest.raises(RuntimeError):
        images.parse_spec('{"headline": ""}')


def test_make_card_writes_png_with_alt(tmp_path):
    class Client:
        messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text='{"kicker":"Tipp","headline":"Erst die Aussage","points":["Drei Sätze"]}')]))
    cfg = {"model": "m", "db_path": str(tmp_path / "t.db"), "image_footer": "Name"}
    path, alt = images.make_card(cfg, "Text mit **Fett**", 7, client=Client())
    assert path.endswith("7.png") and open(path, "rb").read(4) == b"\x89PNG"
    assert alt == "Erst die Aussage Drei Sätze"


def test_db_migrates_old_database(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE posts (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT NOT NULL DEFAULT 'draft', text TEXT NOT NULL, topic TEXT, source_url TEXT, created_at TEXT NOT NULL, published_at TEXT, linkedin_id TEXT)")
    c.commit(); c.close()
    conn = db.connect(p)
    i = db.add_draft(conn, "x")
    db.set_image(conn, i, "a.png", "alt")
    assert conn.execute("SELECT image_path FROM posts").fetchone()[0] == "a.png"


def test_publish_with_image_uploads_then_posts(tmp_path, monkeypatch):
    img = tmp_path / "c.png"; img.write_bytes(b"png")
    tok = tmp_path / "tok.json"
    tok.write_text(json.dumps({"access_token": "t", "author": "urn:li:person:1", "version": "202610"}))
    monkeypatch.setattr(linkedin, "TOKEN_FILE", tok)
    calls = []

    def fake_request(method, url, **kw):
        calls.append((method, url, kw.get("json")))
        if "initializeUpload" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"value": {"uploadUrl": "https://up", "image": "urn:li:image:9"}})
        return SimpleNamespace(status_code=201, headers={"x-restli-id": "urn:li:share:5"}, text="")
    monkeypatch.setattr(linkedin.requests, "request", fake_request)
    monkeypatch.setattr(linkedin.requests, "put", lambda url, **kw: SimpleNamespace(status_code=201, text=""))
    assert linkedin.publish("Text", str(img), "Alt") == "urn:li:share:5"
    assert calls[-1][2]["content"]["media"] == {"id": "urn:li:image:9", "altText": "Alt"}
