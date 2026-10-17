import random

import anthropic

from . import db
from .sources import fetch_items

SYSTEM = """Du schreibst LinkedIn-Posts im Namen einer realen Person. Halte dich strikt an diesen Stil:

{voice}

Regeln:
- Gib ausschließlich den fertigen Posttext aus, ohne Einleitung, Erklärung oder Anführungszeichen.
- Erfinde keine Zahlen, Zitate, Kunden oder persönlichen Erlebnisse. Wenn du eine Erfahrung brauchst, formuliere allgemein.
- Ein Artikel ist nur ein möglicher Anlass. Nutze ihn nur, wenn er klar zum Thema und zur Zielgruppe (Unternehmen, Marketing, Recruiting, Vertrieb) passt. Sonst ignoriere ihn komplett und schreibe den Post allein zum Thema.
- Konstruiere niemals Vergleiche oder Analogien zu fachfremden Themen (Technik, Wissenschaft, Sport usw.), nur um einen Artikel unterzubringen.
- Bei Bezug auf einen Artikel: eigene Einordnung statt Zusammenfassung, Quelle nicht als Link-Dump.
- Der Post muss vollständig sein: Hook, Kernaussage, konkreter Tipp, Schlussfrage, Hashtags.{bold_rule}"""

BOLD_RULE = """
- Hervorhebungen: Setze die erste Zeile (Hook) und höchstens einen weiteren Kernsatz in **doppelte Sternchen**, zum Beispiel **Das ist der Hook.** Nie Hashtags, nie ganze Absätze, insgesamt maximal zwei Stellen. Behalte vorhandene ** beim Überarbeiten bei."""


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
    return _complete(cfg, client, "\n\n".join(parts))


def _complete(cfg, client, prompt):
    system = SYSTEM.format(voice=cfg["voice"], bold_rule=BOLD_RULE if cfg.get("bold", True) else "")
    return _call(cfg, client, system, prompt)


def _call(cfg, client, system, prompt, max_tokens=4000):
    # Sonnet 5.5 denkt standardmäßig und die Denk-Tokens zählen zu max_tokens: Das hat die
    # Posts mitten im Satz abgeschnitten. "between_tools" schaltet das Denken ab (disabled gibt 400).
    msg = client.messages.create(
        model=cfg["model"],
        max_tokens=max_tokens,
        thinking={"type": "between_tools"},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    if msg.stop_reason != "end_turn":
        raise RuntimeError(f"Entwurf unvollständig (stop_reason={msg.stop_reason}, Details: {getattr(msg, 'stop_details', None)}).")
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
    return _complete(cfg, client, f"Bisheriger Post:\n{text}\n\nÜberarbeite ihn: {instruction}\nGib nur den neuen Posttext aus.")
