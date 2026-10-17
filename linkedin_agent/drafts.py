import random

import anthropic

from . import db
from .sources import fetch_items

SYSTEM = """Du schreibst LinkedIn-Posts im Namen einer realen Person. Halte dich strikt an diesen Stil:

{voice}

Regeln:
- Gib ausschließlich den fertigen Posttext aus, ohne Einleitung, Erklärung oder Anführungszeichen.
- Erfinde keine Zahlen, Zitate, Kunden oder persönlichen Erlebnisse. Wenn du eine Erfahrung brauchst, formuliere allgemein.
- Bei Bezug auf einen Artikel: eigene Einordnung statt Zusammenfassung, Quelle nicht als Link-Dump."""


def _client():
    return anthropic.Anthropic()


def generate_text(cfg, topic, article=None, notes=None, client=None):
    client = client or _client()
    parts = [f"Thema: {topic}"]
    if article:
        parts.append(f"Anlass (Artikel): {article['title']}\n{article['summary']}\n{article['url']}")
    if notes:
        parts.append(f"Stichpunkte des Autors:\n{notes}")
    parts.append("Schreibe jetzt den Post.")
    msg = client.messages.create(
        model=cfg["model"],
        max_tokens=1200,
        system=SYSTEM.format(voice=cfg["voice"]),
        messages=[{"role": "user", "content": "\n\n".join(parts)}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def create_drafts(cfg, conn, client=None, items=None):
    """Erzeugt Entwürfe aus RSS-Anlässen und Themen. Liefert die neuen Post-IDs."""
    seen = db.used_urls(conn)
    items = items if items is not None else fetch_items(cfg["feeds"])
    fresh = [i for i in items if i["url"] not in seen]
    random.shuffle(fresh)
    ids = []
    for n in range(cfg["drafts_per_run"]):
        topic = cfg["topics"][n % len(cfg["topics"])] if cfg["topics"] else "Vertrieb"
        article = fresh.pop() if fresh else None
        text = generate_text(cfg, topic, article=article, client=client)
        ids.append(db.add_draft(conn, text, topic, article["url"] if article else None))
    return ids


def draft_from_notes(cfg, conn, topic, notes, client=None):
    text = generate_text(cfg, topic, notes=notes, client=client)
    return db.add_draft(conn, text, topic)


def revise(cfg, text, instruction, client=None):
    client = client or _client()
    msg = client.messages.create(
        model=cfg["model"],
        max_tokens=1200,
        system=SYSTEM.format(voice=cfg["voice"]),
        messages=[{"role": "user", "content": f"Bisheriger Post:\n{text}\n\nÜberarbeite ihn: {instruction}\nGib nur den neuen Posttext aus."}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()
