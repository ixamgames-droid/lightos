"""NET-01: Persistente Einstellungen fuer die Remote-Absicherung.

Liegt wie die uebrigen UI-Prefs in ``%APPDATA%/LightOS/ui_prefs.json`` (Key
``remote``) — ueber App-Neustarts hinweg stabil, damit ein einmal am Handy
eingetipptes Token weiter gilt.

Gehaltene Werte:
  * ``token``               — pro Show/Setup persistiertes Auth-Token
                              (``secrets.token_urlsafe(6)`` = kurz & tippbar).
  * ``lan_remote_enabled``  — sichtbarer Toggle 'LAN-/Handy-Remote' (Default AN;
                              sicher, weil das Token davor sitzt). Aus -> der
                              Web-Server bindet nur an 127.0.0.1 (kein LAN).
  * ``osc_network_enabled`` — Toggle 'OSC ueber Netzwerk' (Default AUS). Aus ->
                              OSC-Server bindet 127.0.0.1 (nur lokal).

Alles offline/stdlib, keine externe Dependency."""
from __future__ import annotations
import json
import os
import secrets

_KEY = "remote"


def _prefs_dir() -> str:
    # Lazy ermittelt, damit Tests via LIGHTOS_PREFS_DIR auf ein Temp-Verzeichnis
    # umlenken koennen (kein Schreiben in die echten Nutzer-Prefs).
    override = os.environ.get("LIGHTOS_PREFS_DIR")
    if override:
        return override
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS")


def _prefs_path() -> str:
    return os.path.join(_prefs_dir(), "ui_prefs.json")

DEFAULTS: dict = {
    "token": "",
    "lan_remote_enabled": True,
    "osc_network_enabled": False,
}


def _load_all() -> dict:
    try:
        with open(_prefs_path(), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def load_settings() -> dict:
    """Liest die Remote-Einstellungen (mit Defaults aufgefuellt)."""
    raw = {}
    try:
        raw = (_load_all().get(_KEY, {}) or {})
    except Exception:
        raw = {}
    out = dict(DEFAULTS)
    for k in DEFAULTS:
        if k in raw:
            out[k] = raw[k]
    return out


def save_settings(settings: dict) -> None:
    """Schreibt die Remote-Einstellungen, ohne fremde ui_prefs-Keys zu verlieren."""
    try:
        os.makedirs(_prefs_dir(), exist_ok=True)
        all_prefs = _load_all()
        cur = dict(DEFAULTS)
        cur.update(all_prefs.get(_KEY, {}) or {})
        for k in DEFAULTS:
            if k in settings:
                cur[k] = settings[k]
        all_prefs[_KEY] = cur
        with open(_prefs_path(), "w", encoding="utf-8") as f:
            json.dump(all_prefs, f, indent=2)
    except Exception as e:
        print(f"[remote_settings] save error: {e}")


def _new_token() -> str:
    # token_urlsafe(6) -> 8 Zeichen, gut tippbar, aber genug Entropie fuers LAN.
    return secrets.token_urlsafe(6)


def get_token() -> str:
    """Liefert das persistierte Token; erzeugt+speichert eins beim ersten Aufruf."""
    s = load_settings()
    tok = s.get("token") or ""
    if not tok:
        tok = _new_token()
        s["token"] = tok
        save_settings(s)
    return tok


def regenerate_token() -> str:
    """Erzeugt ein NEUES Token, persistiert es und gibt es zurueck ('Token neu
    erzeugen'). Alte am Handy gespeicherte Links werden damit ungueltig."""
    tok = _new_token()
    save_settings({"token": tok})
    return tok


def is_lan_remote_enabled() -> bool:
    return bool(load_settings().get("lan_remote_enabled", True))


def set_lan_remote_enabled(enabled: bool) -> None:
    save_settings({"lan_remote_enabled": bool(enabled)})


def is_osc_network_enabled() -> bool:
    return bool(load_settings().get("osc_network_enabled", False))


def set_osc_network_enabled(enabled: bool) -> None:
    save_settings({"osc_network_enabled": bool(enabled)})
