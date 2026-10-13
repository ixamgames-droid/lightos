"""VCB-45 (Schritt 1): das Popout der Virtual Console merkt sich Bildschirm,
Lage, Groesse und Zustand.

Zwei Teile, bewusst getrennt:

* **Rechnung ohne Qt-Fenster.** ``ziel_lage`` bekommt eine Liste von
  Bildschirm-Rechtecken, das Gemerkte und den Bildschirm des Hauptfensters und
  liefert, wo das Popout aufgehen soll. Sie braucht keinen Bildschirm und ist
  deshalb vollstaendig testbar.
* **Kleber zum Fenster.** ``LageMerker`` liest Lage und Zustand des echten
  Fensters und schreibt sie entprellt in ``ui_prefs.json`` — derselbe Weg wie
  die uebrigen geraetegebundenen Fenster-Einstellungen
  (``programmer_view._load_prefs`` / ``_save_prefs``).

Gemerkt werden nur der Anschlussname des Bildschirms (``QScreen.name()``, etwa
``HDMI-1``) und seine Geometrie als Rueckfall — **keine** Seriennummer, kein
Hersteller, kein Modell.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer

PREF_SCHLUESSEL = "vc_popout_lage"

NORMAL = "normal"
MAXIMIERT = "maximized"
VOLLBILD = "fullscreen"
_ZUSTAENDE = (NORMAL, MAXIMIERT, VOLLBILD)

# Groesse des Popout ohne Gemerktes (unveraendert seit jeher).
STANDARD_GROESSE = (1280, 800)
# Kleiner wird ein wiederhergestelltes Fenster nie (unbrauchbare Altwerte).
_MIN_BREITE = 320
_MIN_HOEHE = 200
# Bewegen/Ziehen feuert je Mausbewegung; geschrieben wird erst nach Stillstand.
_SPEICHER_VERZUG_MS = 300
# So lange nach dem Oeffnen gilt eine Lage noch als „vom Programm gesetzt".
_SCHARF_NACH_MS = 500


# ── Rechnung (ohne Qt) ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Rechteck:
    x: int
    y: int
    w: int
    h: int

    def als_liste(self) -> list[int]:
        return [int(self.x), int(self.y), int(self.w), int(self.h)]

    def schnittflaeche(self, anderes: "Rechteck") -> int:
        b = min(self.x + self.w, anderes.x + anderes.w) - max(self.x, anderes.x)
        h = min(self.y + self.h, anderes.y + anderes.h) - max(self.y, anderes.y)
        return b * h if b > 0 and h > 0 else 0


@dataclass(frozen=True)
class Bildschirm:
    """Ein angeschlossener Bildschirm: Anschlussname, ganze Flaeche und der
    Bereich, der nicht von Leisten des Betriebssystems belegt ist."""
    name: str
    flaeche: Rechteck
    frei: Rechteck | None = None

    @property
    def nutzbar(self) -> Rechteck:
        f = self.frei
        if f is None or f.w <= 0 or f.h <= 0:
            return self.flaeche
        return f


@dataclass(frozen=True)
class Lage:
    """Ergebnis der Rechnung.

    ``rechteck`` ist die Lage im Normalzustand (bei maximiert/Vollbild die, auf
    die das Fenster beim Verkleinern zurueckgeht). ``rechteck is None`` heisst:
    nichts vorgeben, das Fenster oeffnet wie bisher.
    ``rueckfall`` ist True, wenn Gemerktes vorlag, aber nicht anwendbar war —
    dann darf die Ersatz-Lage das Gemerkte nicht von selbst ueberschreiben.
    """
    rechteck: Rechteck | None
    zustand: str = NORMAL
    bildschirm: int = 0
    rueckfall: bool = False


def _als_rechteck(wert) -> Rechteck | None:
    try:
        x, y, w, h = (int(v) for v in wert)
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return Rechteck(x, y, w, h)


def lies_gemerkt(wert) -> dict | None:
    """Rohwert aus den Einstellungen pruefen; ``None`` bei allem Unbrauchbaren."""
    if not isinstance(wert, dict):
        return None
    fenster = _als_rechteck(wert.get("fenster"))
    if fenster is None:
        return None
    zustand = wert.get("zustand")
    if zustand not in _ZUSTAENDE:
        zustand = NORMAL
    name = wert.get("bildschirm")
    return {
        "bildschirm": name if isinstance(name, str) else "",
        "bildschirm_flaeche": _als_rechteck(wert.get("bildschirm_flaeche")),
        "fenster": fenster,
        "zustand": zustand,
    }


def finde_bildschirm(bildschirme, name: str, flaeche: Rechteck | None) -> int | None:
    """Index des gemerkten Bildschirms: erst ueber den Namen (bei mehreren
    gleichnamigen entscheidet die Geometrie), sonst ueber die Geometrie."""
    if name:
        treffer = [i for i, b in enumerate(bildschirme) if b.name == name]
        if len(treffer) == 1:
            return treffer[0]
        for i in treffer:
            if bildschirme[i].flaeche == flaeche:
                return i
        if treffer:
            return treffer[0]
    if flaeche is not None:
        for i, b in enumerate(bildschirme):
            if b.flaeche == flaeche:
                return i
    return None


def einpassen(fenster: Rechteck, bereich: Rechteck) -> Rechteck:
    """Fenster ganz in ``bereich`` legen: erst Groesse begrenzen, dann schieben."""
    w = max(min(fenster.w, bereich.w), min(_MIN_BREITE, bereich.w))
    h = max(min(fenster.h, bereich.h), min(_MIN_HOEHE, bereich.h))
    x = min(max(fenster.x, bereich.x), bereich.x + bereich.w - w)
    y = min(max(fenster.y, bereich.y), bereich.y + bereich.h - h)
    return Rechteck(x, y, w, h)


def mittig(groesse, bereich: Rechteck) -> Rechteck:
    w = min(int(groesse[0]), bereich.w)
    h = min(int(groesse[1]), bereich.h)
    return Rechteck(bereich.x + (bereich.w - w) // 2,
                    bereich.y + (bereich.h - h) // 2, w, h)


def ziel_lage(bildschirme, gemerkt=None, haupt: int = 0,
              standard=STANDARD_GROESSE) -> Lage:
    """Wo soll das Popout aufgehen?

    ``bildschirme``: Liste von ``Bildschirm``. ``gemerkt``: Rohwert aus den
    Einstellungen (oder ``None``). ``haupt``: Index des Bildschirms, auf dem
    das Hauptfenster liegt.

    1. Gemerkter Bildschirm ist da und das Fenster laege (zumindest teilweise)
       auf ihm -> dorthin, ganz in den freien Bereich eingepasst. Hat der
       Bildschirm inzwischen eine andere Lage im Verbund, wandert das Fenster
       mit ihm mit.
    2. Gemerkter Bildschirm fehlt oder das Fenster laege ausserhalb -> sichtbar
       auf den Bildschirm des Hauptfensters, als normales Fenster.
    3. Nichts gemerkt, mehrere Bildschirme -> maximiert auf den anderen
       Bildschirm als das Hauptfenster.
    4. Nichts gemerkt, ein Bildschirm -> nichts vorgeben (wie bisher).
    """
    bildschirme = list(bildschirme or [])
    if not bildschirme:
        return Lage(None)
    if not 0 <= haupt < len(bildschirme):
        haupt = 0

    daten = lies_gemerkt(gemerkt)
    if daten is not None:
        fenster = daten["fenster"]
        idx = finde_bildschirm(bildschirme, daten["bildschirm"],
                               daten["bildschirm_flaeche"])
        if idx is not None:
            ziel = bildschirme[idx]
            alt = daten["bildschirm_flaeche"]
            if alt is not None:
                # Lage relativ zum Bildschirm halten (Anordnung geaendert).
                fenster = Rechteck(fenster.x - alt.x + ziel.flaeche.x,
                                   fenster.y - alt.y + ziel.flaeche.y,
                                   fenster.w, fenster.h)
            if fenster.schnittflaeche(ziel.flaeche) > 0:
                return Lage(einpassen(fenster, ziel.nutzbar),
                            daten["zustand"], idx)
            if daten["zustand"] != NORMAL:
                # Maximiert/Vollbild fuellt den Bildschirm ohnehin; nur die
                # Lage fuers spaetere Verkleinern liegt daneben -> mittig.
                return Lage(mittig((fenster.w, fenster.h), ziel.nutzbar),
                            daten["zustand"], idx)
        # Bildschirm weg oder Fenster ausserhalb: sichtbar zum Hauptfenster.
        # Bewusst als normales Fenster — maximiert laege es ueber dem Hauptfenster.
        bereich = bildschirme[haupt].nutzbar
        return Lage(mittig((fenster.w, fenster.h), bereich), NORMAL, haupt,
                    rueckfall=True)

    if len(bildschirme) > 1:
        idx = next(i for i in range(len(bildschirme)) if i != haupt)
        return Lage(mittig(standard, bildschirme[idx].nutzbar), MAXIMIERT, idx)
    return Lage(None, NORMAL, haupt)


def als_gemerkt(bildschirm: Bildschirm, fenster: Rechteck, zustand: str) -> dict:
    """Das, was in den Einstellungen landet — nur Name, Rechtecke, Zustand."""
    return {
        "bildschirm": str(bildschirm.name or ""),
        "bildschirm_flaeche": bildschirm.flaeche.als_liste(),
        "fenster": fenster.als_liste(),
        "zustand": zustand if zustand in _ZUSTAENDE else NORMAL,
    }


def bildschirm_von(bildschirme, fenster: Rechteck, vorgabe: int = 0) -> int:
    """Index des Bildschirms, auf dem das Fenster ueberwiegend liegt."""
    beste, flaeche = vorgabe, 0
    for i, b in enumerate(bildschirme):
        f = fenster.schnittflaeche(b.flaeche)
        if f > flaeche:
            beste, flaeche = i, f
    return beste


# ── Einstellungs-Ablage ──────────────────────────────────────────────────────

def lade_gemerkt():
    try:
        from src.ui.views.programmer_view import _load_prefs
        return (_load_prefs() or {}).get(PREF_SCHLUESSEL)
    except Exception:
        return None


def speichere_gemerkt(wert: dict) -> None:
    try:
        from src.ui.views.programmer_view import _save_prefs
        _save_prefs({PREF_SCHLUESSEL: wert})
    except Exception as e:
        print(f"[VC] Popout-Lage nicht gespeichert: {e}")


# ── Kleber zu Qt ─────────────────────────────────────────────────────────────

def lies_bildschirme():
    """Alle angeschlossenen Bildschirme als ``(Bildschirm, QScreen)``-Paare."""
    from PySide6.QtGui import QGuiApplication
    paare = []
    for s in QGuiApplication.screens():
        g, a = s.geometry(), s.availableGeometry()
        paare.append((Bildschirm(s.name(),
                                 Rechteck(g.x(), g.y(), g.width(), g.height()),
                                 Rechteck(a.x(), a.y(), a.width(), a.height())),
                      s))
    return paare


def haupt_index(paare, widget) -> int:
    """Index des Bildschirms, auf dem das Fenster von ``widget`` liegt."""
    try:
        s = widget.window().screen()
    except Exception:
        s = None
    if s is not None:
        for i, (_, qs) in enumerate(paare):
            if qs is s:
                return i
        try:
            name = s.name()
            for i, (b, _) in enumerate(paare):
                if b.name == name:
                    return i
        except Exception:
            pass
    return 0


def _zustand_von(fenster) -> str:
    if fenster.isFullScreen():
        return VOLLBILD
    if fenster.isMaximized():
        return MAXIMIERT
    return NORMAL


def oeffne(fenster, lage: Lage, qscreen=None) -> None:
    """Fenster nach ``lage`` anzeigen (ersetzt das nackte ``show()``)."""
    r = lage.rechteck
    if r is None:
        fenster.show()
        return
    if qscreen is not None:
        try:
            fenster.setScreen(qscreen)
        except Exception:
            pass
    fenster.resize(r.w, r.h)
    fenster.move(r.x, r.y)
    if lage.zustand == VOLLBILD:
        fenster.showFullScreen()
    elif lage.zustand == MAXIMIERT:
        fenster.showMaximized()
    else:
        fenster.show()


class LageMerker(QObject):
    """Merkt Lage/Groesse/Zustand eines Fensters, entprellt.

    Das Fenster ruft ``angestossen()`` aus Move-/Resize-/Zustands-Ereignis
    und ``sichern()`` beim Schliessen. Der Merker selbst haengt als Kind am
    Fenster und stirbt mit ihm.
    """

    def __init__(self, fenster, lage: Lage):
        super().__init__(fenster)
        r = lage.rechteck
        # Lage im Normalzustand; bei maximiert/Vollbild bleibt sie stehen.
        self._normal = r
        # Rueckfall-Lage: erst merken, wenn der Bediener sie veraendert —
        # sonst ginge der Platz auf dem (gerade abgezogenen) Bildschirm
        # beim ersten Oeffnen ohne ihn verloren.
        self._gesperrt = bool(lage.rueckfall)
        self._ausgang = None
        self._zuletzt = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_SPEICHER_VERZUG_MS)
        self._timer.timeout.connect(self.sichern)
        if self._gesperrt:
            QTimer.singleShot(_SCHARF_NACH_MS, self, self._scharf_stellen)

    def _ist(self):
        # Kein eigener Verweis aufs Fenster (kein Python-Zyklus Fenster <-> Merker).
        f = self.parent()
        return (f.x(), f.y(), f.width(), f.height(), _zustand_von(f))

    def _scharf_stellen(self):
        try:
            self._ausgang = self._ist()
        except RuntimeError:
            pass

    def angestossen(self) -> None:
        try:
            self._timer.start()
        except RuntimeError:
            pass

    def sichern(self) -> None:
        """Aktuellen Stand sofort schreiben (sofern er sich geaendert hat)."""
        try:
            self._timer.stop()
            f = self.parent()
            if f is None or f.isMinimized():
                return
            ist = self._ist()
        except RuntimeError:
            return
        if self._gesperrt:
            if self._ausgang is None or ist == self._ausgang:
                return
            self._gesperrt = False
        zustand = ist[4]
        if zustand == NORMAL:
            self._normal = Rechteck(*ist[:4])
        fenster = self._normal
        if fenster is None:
            # Maximiert geoeffnet ohne bekannte Normal-Lage.
            fenster = Rechteck(*ist[:4])
        try:
            paare = lies_bildschirme()
        except Exception as e:
            print(f"[VC] Popout-Lage nicht gemerkt: {e}")
            return
        if not paare:
            return
        bildschirme = [b for b, _ in paare]
        # Maximiert/Vollbild: der Bildschirm, den das Fenster gerade fuellt.
        idx = bildschirm_von(bildschirme, Rechteck(*ist[:4]))
        wert = als_gemerkt(bildschirme[idx], fenster, zustand)
        if wert == self._zuletzt:
            return
        self._zuletzt = wert
        speichere_gemerkt(wert)


def baue_merker(fenster, lage: Lage):
    return LageMerker(fenster, lage)
