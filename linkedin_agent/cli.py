import argparse
import os

from . import db, drafts, linkedin
from .config import load_config, load_env


def _show(p):
    print(f"\n--- #{p['id']} [{p['status']}] Thema: {p['topic']} ---")
    print(p["text"])
    if p["source_url"]:
        print(f"\nQuelle: {p['source_url']}")


def cmd_draft(cfg, conn, args):
    if args.notes:
        ids = [drafts.draft_from_notes(cfg, conn, args.topic or cfg["topics"][0], args.notes)]
    else:
        ids = drafts.create_drafts(cfg, conn)
    print(f"{len(ids)} Entwurf/Entwürfe erstellt: {ids}. Weiter mit `review`.")


def cmd_review(cfg, conn, args):
    for p in db.list_posts(conn, "draft"):
        _show(p)
        while True:
            a = input("[a]pprove / [e]dit per Anweisung / [r]eject / [s]kip / [q]uit: ").strip().lower()
            if a == "a":
                db.set_status(conn, p["id"], "approved")
                break
            if a == "r":
                db.set_status(conn, p["id"], "rejected")
                break
            if a == "e":
                new = drafts.revise(cfg, p["text"], input("Anweisung: "))
                db.update_text(conn, p["id"], new)
                p = conn.execute("SELECT * FROM posts WHERE id=?", (p["id"],)).fetchone()
                _show(p)
                continue
            if a == "s":
                break
            if a == "q":
                return


def cmd_publish(cfg, conn, args):
    for p in db.list_posts(conn, "approved"):
        _show(p)
        if not args.yes and input("Jetzt auf LinkedIn veröffentlichen? [j/N] ").strip().lower() != "j":
            continue
        img = p["image_path"] or ""
        img = img.replace(".svg", ".png") if img.endswith(".svg") else img  # erzeugtes Bild: PNG liegt erst nach dem Posten über die Weboberfläche vor
        pid = linkedin.publish(p["text"], img if img and os.path.exists(img) else None, p["image_alt"])
        db.mark_published(conn, p["id"], pid)
        print("Veröffentlicht:", pid)


def cmd_list(cfg, conn, args):
    for p in db.list_posts(conn, args.status):
        print(f"#{p['id']:<4}{p['status']:<10}{p['topic'] or '':<30}{p['text'][:60]!r}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="linkedin_agent")
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft", help="Entwürfe erzeugen (RSS+Themen oder aus eigenen Stichpunkten)")
    d.add_argument("--topic")
    d.add_argument("--notes", help="Eigene Stichpunkte als Grundlage")
    sub.add_parser("review", help="Entwürfe freigeben, überarbeiten oder verwerfen")
    pu = sub.add_parser("publish", help="Freigegebene Posts veröffentlichen")
    pu.add_argument("--yes", action="store_true", help="Ohne Rückfrage (z. B. für Cron)")
    ls = sub.add_parser("list")
    ls.add_argument("--status")
    sub.add_parser("auth", help="Einmalig bei LinkedIn anmelden")
    sub.add_parser("web", help="Weboberfläche starten (nächsten Post ansehen, posten, neu generieren)")
    args = ap.parse_args(argv)

    load_env()
    if args.cmd == "auth":
        return linkedin.authorize()
    cfg = load_config(args.config)
    if args.cmd == "web":
        from .web import serve
        return serve(cfg)
    conn = db.connect(cfg["db_path"])
    {"draft": cmd_draft, "review": cmd_review, "publish": cmd_publish, "list": cmd_list}[args.cmd](cfg, conn, args)
