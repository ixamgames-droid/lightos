"""VCB-45 (Schritt 1): das Popout der Virtual Console merkt sich Bildschirm,
Lage, Groesse und Zustand — und behaelt den Platz, wenn sein Bildschirm
zwischendurch wegfaellt.

Zwei Teile, bewusst getrennt:

* **Rechnung ohne Qt-Fenster.** ``ziel_lage`` bekommt eine Liste von
  Bildschirm-Rechtecken, das Gemerkte und den Bildschirm des Hauptfensters und
  liefert, wo das Popout aufgehen soll. Sie braucht keinen Bildschirm und ist
  deshalb vollstaendig testbar.
* **Kleber zum Fenster.** ``LageMerker`` liest Lage und Zustand des echten
  Fensters und schreibt sie entprellt in ``ui_prefs.json`` — derselbe Weg wie
  die uebrigen geraetegebundenen Fenster-Einstellungen
  (``programmer_view._load_prefs`` / ``_save_prefs``).

**Bildschirm faellt weg, waehrend das Popout offen ist** (Touch-Bildschirm
ausgeschaltet oder abgezogen): Das System schiebt das Fenster auf einen
verbleibenden Bildschirm. Der gemerkte Platz bleibt der alte; der Merker ist
dann „im Ersatz" und schreibt nichts. Kommt der Bildschirm wieder, springt das
Fenster von selbst zurueck. Hat der Bediener das Ersatz-Fenster inzwischen
selbst verschoben oder in der Groesse geaendert, gilt das als neue Wahl: der
Platz wird gemerkt, zurueckgesprungen wird nicht.

Wie Bediener und System auseinandergehalten werden: Ein Fenster meldet nicht,
*wer* es bewegt hat. Deshalb gilt nach jedem Bildschirm-Ereignis eine
Beruhigungszeit, in der jede Bewegung dem System zugeschrieben wird. Erst an
ihrem Ende wird der Stand als Ausgang festgehalten; nur was danach von diesem
Ausgang abweicht, ist eine Bewegung des Bedieners. Das ist unabhaengig davon,
ob der Fenstermanager das Fenster vor oder nach dem Qt-Signal verschiebt.

Gemerkt werden nur der Anschlussname des Bildschirms (``QScreen.name()``, etwa
``HDMI-1``) und seine Geometrie als Rueckfall — **keine** Seriennummer, kein
Hersteller, kein Modell.
"""
from __future__ import annotations

import weakref
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
# Beruhigungszeit nach einem Bildschirm-Ereignis: was sich in dieser Zeit am
# Fenster bewegt, kommt vom System (Fenstermanager raeumt um), nicht vom Bediener.
_BERUHIGUNG_MS = 1200
# Mehrere „Bildschirm dazu"-Meldungen kurz hintereinander zaehlen als eine;
# erst nach dieser Ruhe wird geprueft, ob zurueckgesprungen wird.
_RUECKKEHR_VERZUG_MS = 400


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
    except (TypeError, ValueError, OverflowError):
        # OverflowError: ``Infinity`` in einer von Hand bearbeiteten Datei.
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
    """Wie ``_ziel_lage``, aber nie mit leerem Rechteck: meldet das System
    einen Bildschirm ohne Flaeche (Platzhalter, solange keiner angeschlossen
    ist), wird nichts vorgegeben und das Fenster oeffnet wie bisher."""
    lage = _ziel_lage(bildschirme, gemerkt, haupt, standard)
    r = lage.rechteck
    if r is not None and (r.w <= 0 or r.h <= 0):
        return Lage(None)
    return lage


def _ziel_lage(bildschirme, gemerkt, haupt, standard) -> Lage:
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


def rueckkehr_lage(bildschirme, gemerkt, haupt: int = 0) -> Lage | None:
    """Wohin springt ein Popout zurueck, das am Ersatzplatz liegt?

    ``None``, solange der gemerkte Bildschirm nicht (wieder) da ist oder das
    Fenster dort nicht laege — ein fremder neuer Bildschirm loest also nichts
    aus. Wiedererkannt wird der Bildschirm wie beim Oeffnen: ueber den Namen,
    sonst ueber die Geometrie."""
    if lies_gemerkt(gemerkt) is None:
        return None
    lage = ziel_lage(bildschirme, gemerkt, haupt)
    if lage.rueckfall or lage.rechteck is None:
        return None
    return lage


def ueberwiegend_sichtbar(bildschirme, fenster: Rechteck) -> bool:
    """Liegt mindestens die Haelfte des Fensters auf den Bildschirmen?"""
    flaeche = sum(fenster.schnittflaeche(b.flaeche) for b in bildschirme)
    return 2 * flaeche >= fenster.w * fenster.h


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


def versetze(fenster, lage: Lage, qscreen=None) -> None:
    """Ein schon sichtbares Fenster nach ``lage`` bringen — samt Zustand.

    Ein maximiertes oder Vollbild-Fenster laesst sich nicht verschieben; es
    wird deshalb erst normal, dann versetzt, dann wieder in seinen Zustand
    gebracht. Das Fenster wird dabei nicht nach vorn geholt."""
    r = lage.rechteck
    if r is None:
        return
    if fenster.isFullScreen() or fenster.isMaximized():
        fenster.showNormal()
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


def _als_bildschirm(wert) -> Bildschirm | None:
    """``QScreen`` (aus dem Qt-Signal) oder ``Bildschirm`` (Test) annehmen."""
    if wert is None or isinstance(wert, Bildschirm):
        return wert
    try:
        g = wert.geometry()
        return Bildschirm(wert.name(),
                          Rechteck(g.x(), g.y(), g.width(), g.height()))
    except Exception:
        return None


class LageMerker(QObject):
    """Merkt Lage/Groesse/Zustand eines Fensters, entprellt, und haelt den
    gemerkten Platz fest, solange dessen Bildschirm fehlt.

    Das Fenster ruft ``angestossen()`` aus Move-/Resize-/Zustands-Ereignis
    und ``sichern()`` beim Schliessen. ``bildschirm_weg`` / ``bildschirm_dazu``
    haengen an ``QGuiApplication.screenRemoved`` / ``screenAdded``; Tests rufen
    sie direkt. Der Merker selbst haengt als Kind am Fenster und stirbt mit ihm.

    Drei Zustaende:

    * **normal** — jede Aenderung wird (entprellt) gemerkt.
    * **im Ersatz** (``_gesperrt``) — der gemerkte Bildschirm fehlt, das
      Fenster liegt woanders. Gemerkt wird erst, wenn der Bediener das Fenster
      gegenueber dem Ausgang (``_ausgang``, nach der Beruhigungszeit
      festgehalten) veraendert; das beendet den Ersatz.
    * **im Sprung** (``_sprung``) — das Fenster wird gerade an den gemerkten
      Platz zurueckgebracht; bis es dort angekommen ist, wird nichts gemerkt.
    """

    def __init__(self, fenster, lage: Lage, haupt=None):
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
        self._sprung = None
        # Rechteck des letzten Ruecksprungs (fuer genau einen neuen Versuch,
        # wenn der Bildschirm danach noch an eine andere Stelle rueckt).
        self._versucht = None
        # Beim Oeffnen hat ``ziel_lage`` schon sichtbar platziert.
        self._platziert = True
        # Ohne Rueckfall wird der Platz kurz nach dem Oeffnen einmal gemerkt:
        # faellt der Bildschirm weg, bevor das Fenster je angefasst wurde,
        # gaebe es sonst nichts, wohin es zurueckspringen koennte.
        self._erst = not self._gesperrt
        self._haupt = None
        if haupt is not None:
            try:
                self._haupt = weakref.ref(haupt)
            except TypeError:
                self._haupt = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_SPEICHER_VERZUG_MS)
        self._timer.timeout.connect(self.sichern)
        self._ruhe = QTimer(self)
        self._ruhe.setSingleShot(True)
        self._ruhe.timeout.connect(self._nach_ruhe)
        self._rueck = QTimer(self)
        self._rueck.setSingleShot(True)
        self._rueck.setInterval(_RUECKKEHR_VERZUG_MS)
        self._rueck.timeout.connect(self._rueckkehr_pruefen)
        self._ruhe.start(_SCHARF_NACH_MS)
        try:
            from PySide6.QtGui import QGuiApplication
            app = QGuiApplication.instance()
            if app is not None:
                app.screenRemoved.connect(self.bildschirm_weg)
                app.screenAdded.connect(self.bildschirm_dazu)
        except Exception as e:
            print(f"[VC] Popout folgt Bildschirmwechseln nicht: {e}")

    # ── Lesen ────────────────────────────────────────────────────────────────

    def im_ersatz(self) -> bool:
        return self._gesperrt

    def _ist(self):
        # Kein eigener Verweis aufs Fenster (kein Python-Zyklus Fenster <-> Merker).
        f = self.parent()
        return (f.x(), f.y(), f.width(), f.height(), _zustand_von(f))

    def _offen(self):
        """Das Fenster, sofern es sichtbar ist — sonst ``None``."""
        f = self.parent()
        if f is None or not f.isVisible():
            return None
        return f

    def _gemerkt(self):
        return self._zuletzt or lade_gemerkt()

    def _haupt_index(self, paare) -> int:
        widget = self._haupt() if self._haupt is not None else None
        try:
            return haupt_index(paare, widget)
        except Exception:
            return 0

    def _gemerkter_bildschirm_fehlt(self, weg: Bildschirm | None = None) -> bool:
        daten = lies_gemerkt(self._gemerkt())
        if daten is None:
            return False
        name, flaeche = daten["bildschirm"], daten["bildschirm_flaeche"]
        bildschirme = [b for b, _ in lies_bildschirme()]
        if bildschirme:
            # Die Liste entscheidet: ein weggefallener Bildschirm mit gleicher
            # Flaeche (gespiegelt) ist nicht der gemerkte, solange dieser
            # unter seinem Namen noch da ist.
            return finde_bildschirm(bildschirme, name, flaeche) is None
        return (weg is not None
                and finde_bildschirm([weg], name, flaeche) is not None)

    # ── Ausgang / Beruhigung ─────────────────────────────────────────────────

    def _scharf_stellen(self):
        try:
            self._ausgang = self._ist()
        except RuntimeError:
            pass

    def _beruhigen(self):
        """Ab jetzt gilt eine Weile jede Bewegung als vom System ausgeloest."""
        self._timer.stop()
        self._ausgang = None
        self._ruhe.start(_BERUHIGUNG_MS)

    def _in_ersatz(self):
        self._gesperrt = True
        self._erst = False
        self._platziert = False
        self._beruhigen()

    def _nach_ruhe(self):
        try:
            if self._sprung is not None:
                self._sprung_abschliessen()
            elif self._gesperrt:
                if not self._platziert:
                    self._platziert = True
                    if self._hole_sichtbar():
                        # Die eigene Verschiebung erst setzen lassen.
                        self._ruhe.start(_BERUHIGUNG_MS)
                        return
                self._ausgang = self._ist()
            elif self._erst:
                self._erst = False
                self.sichern()
        except RuntimeError:
            pass
        except Exception as e:
            print(f"[VC] Popout-Lage: {e}")

    def _hole_sichtbar(self) -> bool:
        """Hat das System das Fenster nicht (ganz) auf einen verbleibenden
        Bildschirm geholt, kommt es sichtbar zum Hauptfenster. True, wenn
        dafuer verschoben wurde."""
        f = self._offen()
        if f is None:
            return False
        paare = lies_bildschirme()
        bildschirme = [b for b, _ in paare]
        if not bildschirme:
            return False
        ist = self._ist()
        fenster = Rechteck(*ist[:4])
        if ueberwiegend_sichtbar(bildschirme, fenster):
            return False
        haupt = self._haupt_index(paare)
        if not 0 <= haupt < len(paare):
            haupt = 0
        ziel = mittig((fenster.w, fenster.h), bildschirme[haupt].nutzbar)
        if ziel.w <= 0 or ziel.h <= 0:
            return False
        versetze(f, Lage(ziel, NORMAL, haupt), paare[haupt][1])
        return True

    # ── Bildschirm-Ereignisse ────────────────────────────────────────────────

    def bildschirm_weg(self, weg=None) -> None:
        """Ein Bildschirm ist weggefallen (``screenRemoved``)."""
        try:
            if self._offen() is None:
                return
            if self._sprung is not None:
                if self._gemerkter_bildschirm_fehlt(_als_bildschirm(weg)):
                    # Der Bildschirm ist mitten im Ruecksprung wieder weg
                    # (Wackeln beim Einschalten): Sprung abbrechen und wie bei
                    # einem frischen Wegfall behandeln — sonst bliebe eine
                    # gleich folgende „wieder da"-Meldung ohne Wirkung.
                    self._sprung = None
                    self._in_ersatz()
                else:
                    self._beruhigen()
                return
            if self._gesperrt:
                # Das System raeumt womoeglich wieder um.
                self._beruhigen()
                return
            if self._gemerkter_bildschirm_fehlt(_als_bildschirm(weg)):
                self._in_ersatz()
        except RuntimeError:
            pass
        except Exception as e:
            print(f"[VC] Popout-Lage: {e}")

    def bildschirm_dazu(self, _neu=None) -> None:
        """Ein Bildschirm ist dazugekommen (``screenAdded``).

        Entschieden wird erst nach kurzer Ruhe und ueber die ganze
        Bildschirmliste — Name und Geometrie eines frisch gemeldeten
        Bildschirms sind nicht auf jedem System sofort endgueltig."""
        try:
            if self._offen() is None or not self._gesperrt:
                return
            if self._ausgang is not None and self._ist() != self._ausgang:
                # Der Bediener hat das Ersatz-Fenster schon angefasst (das
                # Schreiben stand nur noch aus): seine Wahl gilt.
                self.sichern()
                return
            self._timer.stop()
            self._ruhe.stop()
            self._ausgang = None
            self._rueck.start()
        except RuntimeError:
            pass
        except Exception as e:
            print(f"[VC] Popout-Lage: {e}")

    def _rueckkehr_pruefen(self):
        try:
            f = self._offen()
            if f is None or not self._gesperrt:
                return
            paare = lies_bildschirme()
            bildschirme = [b for b, _ in paare]
            lage = rueckkehr_lage(bildschirme, self._gemerkt(),
                                  self._haupt_index(paare))
            if lage is None:
                # Fremder Bildschirm: nichts tun, nur den Ausgang neu nehmen.
                self._beruhigen()
                return
            self._gesperrt = False
            self._sprung = bildschirme[lage.bildschirm]
            self._normal = lage.rechteck
            self._versucht = lage.rechteck
            versetze(f, lage, paare[lage.bildschirm][1])
            self._timer.stop()
            self._ruhe.start(_BERUHIGUNG_MS)
        except RuntimeError:
            pass
        except Exception as e:
            print(f"[VC] Popout springt nicht zurueck: {e}")
            self._sprung = None
            self._gesperrt = True
            self._beruhigen()

    def _sprung_abschliessen(self):
        """Nach dem Sprung: liegt das Fenster wirklich auf dem gemerkten
        Bildschirm? Sonst (System hat nicht mitgemacht) bleibt es im Ersatz —
        ohne neuen Versuch, bis wieder ein Bildschirm dazukommt."""
        ziel, self._sprung = self._sprung, None
        self._timer.stop()
        bildschirme = [b for b, _ in lies_bildschirme()]
        idx = finde_bildschirm(bildschirme, ziel.name, ziel.flaeche)
        ist = self._ist()
        if idx is not None and bildschirm_von(
                bildschirme, Rechteck(*ist[:4]), vorgabe=-1) == idx:
            return
        self._gesperrt = True
        self._ausgang = ist
        # Nicht angekommen. Liegt das Ziel inzwischen woanders (der Bildschirm
        # wurde erst an vorlaeufiger Stelle gemeldet und ist dann an seinen
        # Platz gerueckt), folgt ein neuer Versuch. Bei unveraendertem Ziel
        # nicht — dann macht das System nicht mit, und es gaebe eine Schleife.
        paare = lies_bildschirme()
        lage = rueckkehr_lage(bildschirme, self._gemerkt(),
                              self._haupt_index(paare))
        if lage is not None and lage.rechteck != self._versucht:
            self._ausgang = None
            self._rueck.start()

    # ── Merken ───────────────────────────────────────────────────────────────

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
        if self._sprung is not None:
            return
        if self._gesperrt:
            if self._ausgang is None or ist == self._ausgang:
                return
            # Liegt das Fenster auf keinem bekannten Bildschirm, hat es das
            # System schon auf den zurueckkehrenden gelegt, bevor dieser
            # gemeldet ist — keine Wahl des Bedieners, also nichts merken.
            try:
                bekannt = [b for b, _ in lies_bildschirme()]
            except Exception:
                bekannt = []
            if bekannt and not ueberwiegend_sichtbar(bekannt, Rechteck(*ist[:4])):
                return
            self._gesperrt = False
        else:
            # Der gemerkte Bildschirm ist weg, ohne dass das Signal schon da
            # war (der Fenstermanager war schneller): nicht den Ersatzplatz
            # merken, sondern in den Ersatz gehen.
            try:
                fehlt = self._gemerkter_bildschirm_fehlt()
            except Exception:
                fehlt = False
            if fehlt:
                self._in_ersatz()
                return
        self._erst = False
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


def baue_merker(fenster, lage: Lage, haupt=None):
    """``haupt``: ein Widget des Hauptfensters — bestimmt, auf welchen
    Bildschirm das Popout ausweicht."""
    return LageMerker(fenster, lage, haupt)
