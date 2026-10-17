import feedparser


def fetch_items(feeds, limit_per_feed=10):
    """Holt aktuelle Einträge aus den RSS-Feeds. Fehlerhafte Feeds werden übersprungen."""
    items = []
    for url in feeds:
        parsed = feedparser.parse(url)
        for e in parsed.entries[:limit_per_feed]:
            items.append({
                "title": e.get("title", ""),
                "summary": e.get("summary", "")[:500],
                "url": e.get("link", ""),
            })
    return [i for i in items if i["url"]]
