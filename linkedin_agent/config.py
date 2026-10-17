import os
from pathlib import Path

import yaml


def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("model", "claude-sonnet-5-5")
    cfg.setdefault("drafts_per_run", 3)
    cfg.setdefault("db_path", "data/posts.db")
    cfg.setdefault("topics", [])
    cfg.setdefault("feeds", [])
    return cfg


def load_env(path=".env"):
    """Liest eine einfache .env, ohne bestehende Umgebungsvariablen zu überschreiben."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
