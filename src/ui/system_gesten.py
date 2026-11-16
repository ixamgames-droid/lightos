"""UI-136 (4): Hinweis, wenn System-Gesten die Finger vor LightOS abfangen.

Finger-Probe am Linux-Mint-Touchscreen: Cinnamon hat eigene Touch-Gesten
(``org.cinnamon.gestures``; z. B. zwei Finger nach links/rechts = Fenster
kacheln, drei Finger tippen = Medien Play/Pause, drei Finger wischen =
Arbeitsflaeche). Sie greifen VOR dem Programm — Zwei-Finger-Bankwechsel,
Halten + Antippen oder Drei-Finger-Tippen kommen dann nicht oder nur teilweise
bei LightOS an. Unter Windows 11 schluckt das System das Drei-/Vier-Finger-
Tippen und -Wischen.

LightOS aendert KEINE Systemeinstellung. Es liest unter Linux nur nach
(``gsettings get``; Zeitlimit 2 s; fehlt ``gsettings`` oder das Schema, passiert
still nichts) und zeigt beim Start im Touch-Modus einmal einen wegklickbaren
Hinweis mit „Nicht mehr zeigen" (gemerkt in ``ui_prefs.json``). Im Kiosk nur
die Statuszeile. Im Dialog „Ansicht → Touch-Gesten…" steht derselbe Befund als
Hinweiszeile.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

PREF = "system_gesten_hinweis_aus"
SCHEMA = "org.cinnamon.gestures"
ZEITLIMIT_S = 2.0

# Belegungen, die LightOS-Gesten treffen (Schluessel -> was dann fehlt)
LINUX_SCHLUESSEL = (
    ("swipe-left-2", "zwei Finger nach links"),
    ("swipe-right-2", "zwei Finger nach rechts"),
    ("tap-3", "drei Finger tippen"),
)

WINDOWS_TEXT = ("Windows-Touchgesten: Drei- und Vier-Finger-Tippen bzw. -Wischen "
                "nimmt das System selbst.")
LINUX_ABSCHALTEN = "Abschalten: Systemeinstellungen → Gesten."
WINDOWS_ABSCHALTEN = ("Abschalten: Einstellungen → Bluetooth und Geräte → Touch → "
                      "„Drei- und Vier-Finger-Touchgesten“.")


class _Zeitlimit(Exception):
    """Ein ``gsettings``-Aufruf hing — keine weiteren Aufrufe (der Start bzw.
    der Dialog wartet hoechstens einmal ``ZEITLIMIT_S``)."""


def _lesen(argumente, lauf) -> str | None:
    """Ein ``gsettings``-Aufruf (nur lesend). ``None`` = gibt es nicht."""
    try:
        r = lauf(["gsettings", *argumente], capture_output=True, text=True,
                 encoding="utf-8", errors="replace", timeout=ZEITLIMIT_S)
    except subprocess.TimeoutExpired as e:
        raise _Zeitlimit() from e
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if getattr(r, "returncode", 1) != 0:
        return None
    return (getattr(r, "stdout", "") or "").strip()


def _belegt(wert: str | None) -> bool:
    if wert is None:
        return False
    w = wert.strip().strip("'\"").strip()
    return bool(w) and w.lower() not in ("none", "nothing", "@as []", "[]")


def _ohne_bildschirm() -> bool:
    """Ohne echten Bildschirm (offscreen: Tests, Rechenlaeufe) gibt es keine
    System-Gesten — dann auch kein ``gsettings``-Aufruf."""
    try:
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.platformName() in ("offscreen", "minimal")
    except Exception:
        return False


def pruefen(plattform: str | None = None, lauf=None) -> list[str]:
    """Aktive System-Gesten, die LightOS-Gesten abfangen (Klartext je Geste).
    Leer = nichts gefunden oder nicht pruefbar. Ohne Attrappe (``lauf``) wird
    ohne echten Bildschirm nichts aufgerufen."""
    if lauf is None and _ohne_bildschirm():
        return []
    plattform = sys.platform if plattform is None else plattform
    if plattform.startswith("win"):
        return [WINDOWS_TEXT]
    if not plattform.startswith("linux"):
        return []
    lauf = subprocess.run if lauf is None else lauf
    gefunden = []
    try:
        an = _lesen(["get", SCHEMA, "enabled"], lauf)
        if an is None or an.strip().lower() != "true":
            return []
        for schluessel, text in LINUX_SCHLUESSEL:
            wert = _lesen(["get", SCHEMA, schluessel], lauf)
            if _belegt(wert):
                gefunden.append(f"{text} ({wert.strip().strip(chr(39))})")
    except _Zeitlimit:
        # Pruefung nach Befund: vier haengende Aufrufe hielten die Oberflaeche
        # sonst bis zu 8 s an. Nach dem ersten Zeitlimit wird nicht weiter
        # gefragt; was bis dahin feststand, gilt.
        return gefunden
    return gefunden


def dialog_zeile(plattform: str | None = None, lauf=None) -> str:
    """Hinweiszeile fuer „Ansicht → Touch-Gesten…" (leer = nichts aktiv)."""
    return hinweis_text(pruefen(plattform, lauf), plattform)


def hinweis_text(gesten: list[str], plattform: str | None = None) -> str:
    if not gesten:
        return ""
    plattform = sys.platform if plattform is None else plattform
    if plattform.startswith("win"):
        return ("System-Gesten sind aktiv und fangen Fingergesten vor LightOS ab. "
                + WINDOWS_TEXT + " " + WINDOWS_ABSCHALTEN)
    return ("System-Gesten sind aktiv und fangen Zwei- und Drei-Finger-Gesten vor "
            "LightOS ab: " + ", ".join(gesten) + ". " + LINUX_ABSCHALTEN)


# ── „Nicht mehr zeigen" ──────────────────────────────────────────────────────

def _pfad() -> str:
    from src.core.paths import app_data_dir
    return os.path.join(app_data_dir(), "ui_prefs.json")


def _lies(pfad: str) -> dict | None:
    if not os.path.exists(pfad):
        return {}
    try:
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:                                    # noqa: BLE001
        return None
    return daten if isinstance(daten, dict) else None


def abgeschaltet(pfad: str | None = None) -> bool:
    return bool((_lies(pfad or _pfad()) or {}).get(PREF, False))


def abschalten(pfad: str | None = None) -> bool:
    """„Nicht mehr zeigen" merken (nur dieser Schluessel wird geschrieben)."""
    pfad = pfad or _pfad()
    try:
        daten = _lies(pfad)
        if daten is None:
            return False                # unlesbar: nichts ueberschreiben
        daten[PREF] = True
        os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
        tmp = f"{pfad}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(daten, f, indent=2, ensure_ascii=False)
        os.replace(tmp, pfad)
        return True
    except Exception as e:                               # noqa: BLE001
        print(f"[system_gesten] nicht gespeichert: {e}")
        return False


def beim_start(fenster, kiosk: bool, pfad: str | None = None, plattform: str | None = None,
               lauf=None, dialog=None) -> str:
    """Einmal beim Start im Touch-Modus. Rueckgabe: was geschah
    (``"aus"``/``"nichts"``/``"status"``/``"dialog"``) — fuer Tests.
    ``dialog`` (Attrappe im Test) bekommt den Text und liefert True, wenn
    „Nicht mehr zeigen" gewaehlt wurde."""
    if abgeschaltet(pfad):
        return "aus"
    gesten = pruefen(plattform, lauf)
    text = hinweis_text(gesten, plattform)
    if not text:
        return "nichts"
    if kiosk:
        try:
            fenster.statusBar().showMessage(text, 15000)
        except Exception:
            pass
        print(f"[system_gesten] {text}")
        return "status"
    nie_mehr = (dialog or _dialog_zeigen)(fenster, text)
    if nie_mehr:
        abschalten(pfad)
    return "dialog"


def _dialog_zeigen(fenster, text: str) -> bool:
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(fenster)
    box.setObjectName("system_gesten_hinweis")
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("System-Gesten aktiv")
    box.setText(text)
    box.setInformativeText("LightOS ändert keine Systemeinstellung. Die eigenen "
                           "LightOS-Gesten stehen unter Ansicht → Touch-Gesten….")
    ok = box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    nie = box.addButton("Nicht mehr zeigen", QMessageBox.ButtonRole.RejectRole)
    for k in (ok, nie):
        k.setMinimumHeight(44)
    box.setDefaultButton(ok)
    box.exec()
    return box.clickedButton() is nie
