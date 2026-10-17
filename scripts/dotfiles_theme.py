"""Shared palette and live Textual integration for personal tools."""
import hashlib
import json
import os
from pathlib import Path

FALLBACK = {"base":"#1e1e2e", "surface":"#313244", "overlay":"#45475a", "text":"#cdd6f4", "muted":"#a6adc8", "accent":"#cba6f7", "red":"#f38ba8", "green":"#a6e3a1", "yellow":"#f9e2af", "blue":"#89b4fa", "pink":"#f5c2e7", "teal":"#94e2d5", "light":False}


def palette():
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    try:
        return {**FALLBACK, **json.loads((root / "dotfiles-theme/current/colors.json").read_text())}
    except (OSError, ValueError):
        return FALLBACK.copy()


def color(key):
    return palette()[key]


def install(app):
    """Register semantic colors once per selection, without restarting the app."""
    from textual.theme import Theme

    def update():
        p = palette()
        name = "dotfiles-" + hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:12]
        if app.theme == name:
            return
        app.register_theme(Theme(
            name=name, primary=p["accent"], secondary=p["blue"], accent=p["teal"],
            foreground=p["text"], background=p["base"], surface=p["surface"], panel=p["surface"],
            success=p["green"], warning=p["yellow"], error=p["red"], dark=not p["light"],
            variables={"foreground-muted":p["muted"], "border":p["overlay"]},
        ))
        app.theme = name

    update()
    app.set_interval(0.1, update)
