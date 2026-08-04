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
from src.core.paths import app_data_dir

_KEY = "remote"


def _prefs_dir() -> str:
    # Lazy ermittelt, damit Tests via LIGHTOS_PREFS_DIR auf ein Temp-Verzeichnis
    # umlenken koennen (kein Schreiben in die echten Nutzer-Prefs).
    override = os.environ.get("LIGHTOS_PREFS_DIR")
    if override:
        return override
    return app_data_dir()


def _prefs_path() -> str:
    return os.path.join(_prefs_dir(), "ui_prefs.json")

DEFAULTS: dict = {
    "token": "",
    "lan_remote_enabled": True,
    "osc_network_enabled": False,
    # Auth-Epoche: wird bei jeder Token-Rotation erhoeht. Die Web-Session speichert
    # die Epoche zum Auth-Zeitpunkt; der Gate weist Sessions mit veralteter Epoche ab
    # -> ein 'Token neu erzeugen' wirft bestehende Sessions SOFORT raus (Security-
    # Review). Im Cookie steht nur die Zahl, nichts Token-Ableitbares.
    "auth_epoch": 0,
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
        # CDX-24: ATOMAR schreiben (tmp + os.replace). Vorher truncate+dump: der
        # Auth-Gate liest diese Datei bei JEDER HTTP-Anfrage aus dem Web-Thread,
        # waehrend der Qt-Thread beim Rotieren schreibt. Im Schreibfenster sah der
        # Gate eine leere/halbe Datei, fiel auf die DEFAULTS zurueck und damit auf
        # `auth_epoch: 0` — ausgerechnet waehrend der Rotation waere er also
        # fail-OPEN fuer jede Session der Epoche 0 gewesen. `os.replace` ist auf
        # Windows wie POSIX atomar, es gibt kein Fenster mit Teil-Inhalt mehr.
        path = _prefs_path()
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(all_prefs, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception as e:
        print(f"[remote_settings] save error: {e}")


def _new_token() -> str:
    # token_urlsafe(6) -> 8 Zeichen, gut tippbar, aber genug Entropie fuers LAN.
    return secrets.token_urlsafe(6)


_token_cache: str = ""


def get_token() -> str:
    """Liefert das persistierte Token; erzeugt+speichert eins beim ersten Aufruf.

    **NET-10 (2026-08-03): mit Prozess-Cache.** ``save_settings`` schluckt jeden
    Schreibfehler und loggt nur (read-only Profil, gesperrte Datei, volle
    Platte). Ohne Cache gab diese Funktion dann bei JEDEM Aufruf ein neues,
    nirgends gespeichertes Token zurueck — dreimal gerufen, dreimal ein anderes.

    Praktisch heisst das: das Web-Remote waere in dieser Lage unbenutzbar. Der
    QR-Code/Link zeigt Token A, der Handshake erwartet inzwischen Token B, und
    niemand sieht warum — der einzige Hinweis steht als geschluckte
    Log-Zeile im Terminal.

    Mit Cache ist das Token wenigstens **fuer die Sitzung** stabil; ueber
    Neustarts hinweg braucht es weiterhin eine schreibbare Datei. Dieselbe
    Haltung wie bei der sACN-CID (``src/core/dmx/sacn_source.py``): ein
    fehlgeschlagenes Speichern darf die laufende Sitzung nicht unbrauchbar
    machen.
    """
    global _token_cache
    if _token_cache:
        return _token_cache
    s = load_settings()
    tok = s.get("token") or ""
    if not tok:
        tok = _new_token()
        s["token"] = tok
        save_settings(s)          # scheitert leise -> der Cache traegt die Sitzung
    _token_cache = tok
    return tok


def _token_cache_leeren() -> None:
    """Verwirft den Prozess-Cache — nach Rotation und in Tests.

    Ohne das lieferte ``get_token()`` nach ``regenerate_token()`` weiter das
    ALTE Token, und die Rotation waere aus Sicht der Anwendung wirkungslos.
    """
    global _token_cache
    _token_cache = ""


def get_auth_epoch() -> int:
    """Aktuelle Auth-Epoche (steigt bei jeder Token-Rotation)."""
    try:
        return int(load_settings().get("auth_epoch", 0) or 0)
    except Exception:
        return 0


def regenerate_token() -> str:
    """Erzeugt ein NEUES Token, persistiert es und gibt es zurueck ('Token neu
    erzeugen').

    Die mit-erhoehte ``auth_epoch`` macht alle bestehenden authentisierten
    Web-Sessions sofort ungueltig (das Gate vergleicht die Session-Epoche gegen
    die aktuelle) — das wirkt allein durch das Persistieren.

    ⚠️ Fuer das TOKEN selbst gilt das NICHT automatisch: der Handshake liest es aus
    ``app.config['LIGHTOS_REMOTE_TOKEN']``, und dort landet es nur beim
    ``create_app``. Ein laufender Server akzeptiert also weiter den ALTEN
    ``?k=``-Link, bis jemand ``src.web.app.refresh_running_token()`` ruft. Die UI
    (Ausgabe → „Web-Remote: Verbindung & Token…") tut beides zusammen; wer die
    Rotation programmatisch ausloest, muss es ebenfalls tun.
    (Der frueher hier stehende Satz „wirkt SOFORT am laufenden Server" war falsch —
    CDX-24.)"""
    global _token_cache
    tok = _new_token()
    # Das Token, das die laufende Sitzung TRAEGT — der Flask-Server hat genau
    # dieses beim `create_app` in `app.config` gelegt. Es zu verlieren heisst,
    # den laufenden Server unerreichbar zu machen; s. den Restore unten.
    bisher = _token_cache
    save_settings({"token": tok, "auth_epoch": get_auth_epoch() + 1})
    # NET-10: den Prozess-Cache VOR der Gegenprobe leeren. Sonst liefert
    # `get_token()` das ALTE Token, die Pruefung unten schlaegt fehl und meldet
    # eine gescheiterte Rotation, obwohl das Speichern geklappt hat — der Cache
    # haette die Sicherung, die er nicht ausloesen soll, selbst ausgeloest.
    _token_cache_leeren()
    # CDX-24: GEGENPROBE. `save_settings` schluckt jeden Schreibfehler (Datei
    # gesperrt, Profil read-only, Platte voll) und loggt nur — ohne diese Pruefung
    # gaebe die Funktion das neue Token zurueck, obwohl gar nichts rotiert wurde,
    # und die UI meldete „alte Links sind ungueltig", waehrend sie es nicht sind.
    if get_token() != tok:
        # ⚠️ **NET-10 hob sich hier selbst auf.** Bei unschreibbarem Profil lebt
        # das gueltige Token NUR im Cache. Der `_token_cache_leeren()`-Aufruf
        # oben warf es weg, und das `get_token()` in dieser Zeile hat daraufhin
        # ein DRITTES Zufallstoken erzeugt und gecacht — der laufende Server
        # erwartete weiter das erste, jeder neu erzeugte Link/QR-Code zeigte das
        # dritte. Genau der unbrauchbare Zustand, gegen den NET-10 gebaut wurde,
        # ausgeloest vom Reparaturversuch selbst.
        #
        # Also den Sitzungs-Stand zurueckdrehen: die Rotation ist gescheitert,
        # und eine gescheiterte Rotation darf nichts veraendert haben. Nur wenn
        # es vorher gar keinen Cache gab, bleibt der eben erzeugte stehen — dann
        # gibt es kein besseres Token, und die Sitzung braucht eines.
        if bisher:
            _token_cache = bisher
        raise RuntimeError(
            "Token-Rotation fehlgeschlagen: die Einstellungen liessen sich nicht "
            "speichern. Die bisherigen Links bleiben gueltig.")
    return tok


def is_lan_remote_enabled() -> bool:
    return bool(load_settings().get("lan_remote_enabled", True))


def set_lan_remote_enabled(enabled: bool) -> None:
    save_settings({"lan_remote_enabled": bool(enabled)})


def is_osc_network_enabled() -> bool:
    return bool(load_settings().get("osc_network_enabled", False))


def set_osc_network_enabled(enabled: bool) -> None:
    save_settings({"osc_network_enabled": bool(enabled)})
