from types import SimpleNamespace

from linkedin_agent import db, drafts
from linkedin_agent.linkedin import build_payload, escape_commentary

CFG = {"model": "m", "voice": "kurz", "topics": ["A", "B"], "feeds": [], "drafts_per_run": 2}


class FakeClient:
    def __init__(self):
        self.messages = self

    def create(self, **kw):
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Hallo Welt #vertrieb")])


def test_escape_keeps_hashtags_and_escapes_reserved():
    assert escape_commentary("Tipp (neu) #vertrieb_x") == r"Tipp \(neu\) #vertrieb\_x"


def test_payload():
    p = build_payload("urn:li:person:1", "x")
    assert p["lifecycleState"] == "PUBLISHED" and p["author"] == "urn:li:person:1"


def test_create_drafts_skips_used_urls_and_stores(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.add_draft(conn, "alt", "A", "http://old")
    items = [{"title": "t", "summary": "s", "url": "http://old"}, {"title": "t2", "summary": "s", "url": "http://new"}]
    ids = drafts.create_drafts(CFG, conn, client=FakeClient(), items=items)
    assert len(ids) == 2
    urls = [r["source_url"] for r in db.list_posts(conn, "draft") if r["id"] in ids]
    assert "http://old" not in urls and "http://new" in urls


def test_status_flow(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    i = db.add_draft(conn, "x")
    db.set_status(conn, i, "approved")
    db.mark_published(conn, i, "urn:li:share:1")
    assert db.list_posts(conn, "published")[0]["linkedin_id"] == "urn:li:share:1"
