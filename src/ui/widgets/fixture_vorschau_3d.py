"""FM-64 (Teil 2): kleine 3D-Vorschau im Fixture-Editor und -Generator.

Zeigt EIN Geraet (das gewaehlte 3D-Modell) mit Lichtkegel ueber einem dunklen
Boden, Kamera fest schraeg von vorn, standardmaessig weisses Licht. Der
Abstrahlwinkel folgt dem Feld im Dialog live; bei einer Zoom-Spanne gibt es
einen Regler fuer den Zoomwert, ein Gobo aus der Gobo-Liste des Profils laesst
sich einschalten, die Farbe umstellen.

★ Keine zweite Rendering-Logik: die Vorschau laedt dieselbe Szene wie der
  Visualizer (``stage_scene.html``, Query ``vorschau=1`` blendet Buehne und
  Werkzeugleisten aus) und baut das Geraet ueber denselben Weg —
  ``addFixture`` mit einem Payload wie ``VisualizerBridge._fixture_to_dict``,
  das Licht ueber ``applyDmx`` wie der DMX-Push (VIZ-71). Das Gobo loest
  ``visualizer_service._gobo_style`` auf, dieselbe Stelle wie im Betrieb.

★ Leistung: QtWebEngine wird erst beim Klick auf „Vorschau zeigen“ gebaut —
  das Oeffnen des Dialogs bleibt so schnell wie vorher. Zuklappen und das
  Schliessen des Dialogs bauen die Ansicht wieder ab (``abbauen``).

★ Ohne WebGL (Grafiktreiber, Fernsitzung) steht ein verstaendlicher Hinweis da
  statt einer leeren Flaeche — derselbe Szenen-Start-Waechter wie im
  Visualizer (VIZ-SCENE-SELFHEAL) entscheidet, wann aufgegeben wird.
"""
from __future__ import annotations

import json
import weakref
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
    QWidget,
)

#: fid des einen Vorschau-Geraets (die Seite kennt kein anderes).
VORSCHAU_FID = 1
#: Montagehoehe in Metern — der Kegel trifft sichtbar auf den Boden.
VORSCHAU_HOEHE = 4.0
#: Hoehe der Ansicht im Dialog (px).
VORSCHAU_HOEHE_PX = 240
#: Query-Zusatz fuer ``stage_scene.html`` (s. scene_src/app.js).
VORSCHAU_QUERY = "vorschau=1"

KNOPF_ZEIGEN = "▶ Vorschau zeigen"
KNOPF_VERBERGEN = "▼ Vorschau ausblenden"
KNOPF_TOOLTIP = (
    "Kleine 3D-Ansicht dieses Geräts mit Lichtkegel. Der Abstrahlwinkel folgt "
    "dem Feld oben sofort; bei Zoom gibt es einen Regler, Gobos aus der "
    "Kanalliste lassen sich einschalten.\nDie Ansicht wird erst hier geladen "
    "— das Öffnen des Dialogs bleibt dadurch schnell.")
HINWEIS_LAEDT = "3D-Vorschau wird geladen …"
HINWEIS_KEIN_WEBGL = (
    "Die 3D-Vorschau kann hier nicht angezeigt werden: dieser Rechner stellt "
    "keine 3D-Grafik (WebGL) bereit — meist liegt es am Grafiktreiber oder an "
    "einer Fernsitzung.\nDas Profil lässt sich trotzdem ganz normal bearbeiten "
    "und speichern; der Abstrahlwinkel gilt danach im 3D-Visualizer.")
HINWEIS_KEINE_ENGINE = (
    "Die 3D-Vorschau braucht QtWebEngine, das hier nicht verfügbar ist. Das "
    "Profil lässt sich trotzdem ganz normal bearbeiten und speichern.")

#: Farbwahl der Vorschau (Name, (r, g, b)) — Weiss zuerst = Standard.
FARBEN = (
    ("Weiß", (255, 255, 255)),
    ("Warmweiß", (255, 200, 140)),
    ("Rot", (255, 0, 0)),
    ("Grün", (0, 255, 0)),
    ("Blau", (0, 0, 255)),
    ("Bernstein", (255, 140, 0)),
    ("Magenta", (255, 0, 255)),
)

#: Render-Modelle mit mehreren Lichtquellen — sie brauchen die Kopf-Zahl.
_MEHRFACH_MODELLE = ("par_bar", "spider", "mover_bar", "matrix", "pixel_head")
#: Wie lange die Seite auf ``__lightosAppReady`` gefragt wird (ms). Das
#: Aufgeben entscheidet der Szenen-Start-Waechter; das hier ist nur der Deckel,
#: damit kein Zeitgeber ewig laeuft.
_BEREIT_TAKT_MS = 150
_BEREIT_DECKEL_MS = 40_000


@dataclass
class VorschauDaten:
    """Was der Dialog gerade zeigt — die Vorschau liest nur das hier."""
    typ: str = "par"
    #: Profil-Override des 3D-Modells ("" = automatisch, wie ``viz_model``).
    viz_model: str = ""
    #: Kanal-Attribute des gezeigten Modus (fuer die Modell-Automatik).
    attribute: list = field(default_factory=list)
    #: Kanaele des gezeigten Modus als Objekte mit ``attribute`` und
    #: ``ranges`` (je ``range_from``/``range_to``/``name``).
    kanaele: list = field(default_factory=list)
    abstrahlwinkel: tuple = (0.0, 0.0)
    zoom_umgekehrt: bool = False


def kanaele_aus_dicts(kanaele) -> list:
    """Kanal-Dicts des Fixture-Editors (``attribute``, ``ranges`` als Dicts)
    als Objekte, wie sie ``_gobo_style`` erwartet."""
    out = []
    for ch in kanaele or ():
        if not isinstance(ch, dict):
            out.append(ch)
            continue
        out.append(SimpleNamespace(
            attribute=ch.get("attribute", "") or "",
            ranges=[SimpleNamespace(range_from=r.get("range_from", 0),
                                    range_to=r.get("range_to", 255),
                                    name=r.get("name", "") or "")
                    for r in (ch.get("ranges") or ()) if isinstance(r, dict)]))
    return out


def render_modell(d: VorschauDaten) -> str:
    """3D-Modell wie im Visualizer: Override gewinnt, sonst die Heuristik aus
    dem Kanal-Layout (``suggest_viz_model``), sonst der Geraetetyp."""
    if (d.viz_model or "").strip():
        return d.viz_model.strip()
    from src.core.app_state import suggest_viz_model
    return suggest_viz_model(d.typ or "", list(d.attribute or ())) or (d.typ or "par")


def hat_zoom_spanne(d: VorschauDaten) -> bool:
    from src.core import abstrahlwinkel as AW
    eng, weit = AW.normalisiere(*tuple(d.abstrahlwinkel or (0, 0)))
    return eng > 0 and weit > eng


def gobo_auswahl(kanaele) -> list[tuple[str, str]]:
    """``[(Range-Name, Stil), ...]`` des Gobo-Rads — ohne „offen“.

    Der Stil kommt aus ``visualizer_service._gobo_style``, also genau so, wie
    der Visualizer denselben DMX-Wert im Betrieb zeichnet. Leer = das Profil
    hat kein Gobo-Rad (dann bietet die Vorschau keine Gobo-Wahl an)."""
    from src.ui.visualizer.visualizer_service import _gobo_style
    kanal = None
    for ch in kanaele or ():
        if (getattr(ch, "attribute", "") or "").lower() in ("gobo_wheel", "gobo"):
            kanal = ch
            break
    if kanal is None:
        return []
    attr = (kanal.attribute or "").lower()
    out = []
    for rg in (getattr(kanal, "ranges", None) or ()):
        try:
            wert = int(rg.range_from)
        except (TypeError, ValueError):
            continue
        stil = _gobo_style({attr: wert}, [kanal])
        if stil and stil != "open":     # „offen“ steht schon als erster Eintrag da
            out.append(((getattr(rg, "name", "") or f"Gobo {len(out) + 1}"), stil))
    return out


def geraet_payload(d: VorschauDaten) -> dict:
    """Payload fuer ``addFixture`` — dieselben Felder wie
    ``VisualizerBridge._fixture_to_dict``, fuer ein ungepatchtes Profil.

    Vereinfacht gegenueber dem Betrieb: keine Rasterform/Weiss-Leiste (der
    Renderer raet sie wie bei „nicht hinterlegt“), Nullpunkte in der Mitte.
    Kopf-Zahl und Ring-Versatz (Pixel-Kopf) rechnen wie im Visualizer."""
    from src.core import abstrahlwinkel as AW
    modell = render_modell(d)
    eng, weit = AW.normalisiere(*tuple(d.abstrahlwinkel or (0, 0)))
    n_heads = 0
    pixel_base = 0
    attrs = [(a or "") for a in (d.attribute or ())]
    if modell in _MEHRFACH_MODELLE:
        n_heads = attrs.count("color_r")
    if modell == "pixel_head":
        # CDX-55/VIZ-53: derselbe Versatz wie ``pixel_ring_banks_for`` im
        # Betrieb — mit fester 0 stuende die Grundfarbe als Ring-Segment da.
        from src.core.app_state import pixel_ring_base_banks
        pixel_base = pixel_ring_base_banks(attrs)
    tilt = 180 if modell == "spider" else 270
    return {
        "fid": VORSCHAU_FID, "label": "", "type": d.typ or "par",
        "model": modell, "nHeads": n_heads, "pixelBase": pixel_base,
        "pixelOrder": "rowwise", "elementRotation": 0, "elementFlip": False,
        "gridRows": 0, "gridCols": 0, "nWhites": 0, "whiteRows": 0,
        "whiteCols": 0,
        "beamAngleMin": eng, "beamAngleMax": weit if weit else eng,
        "zoomInverted": bool(d.zoom_umgekehrt), "mirror": True,
        "x": 0.0, "y": VORSCHAU_HOEHE, "z": 0.0,
        "rotX": 0, "rotY": 0, "rotZ": 0,
        "panRange": 540, "tiltRange": tilt, "panZero": 128, "tiltZero": 128,
        "dockedTo": "",
        "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128,
    }


def licht_payload(farbe=(255, 255, 255), *, zoom: int | None = None,
                  gobo: str | None = None) -> dict:
    """Eintrag fuer ``applyDmx``: volles Licht in ``farbe``; ``zoom`` und
    ``gobo`` nur, wenn das Geraet sie hat (``None`` = Feld fehlt, wie im
    Betrieb bei einem Geraet ohne den Kanal)."""
    r, g, b = (int(max(0, min(255, c))) for c in farbe)
    d = {"fid": VORSCHAU_FID, "intensity": 255, "r": r, "g": g, "b": b,
         "pan": 128, "tilt": 128}
    if zoom is not None:
        d["zoom"] = int(max(0, min(255, zoom)))
    if gobo is not None:
        d["gobo"] = str(gobo)
    return d


class FixtureVorschau3D(QFrame):
    """Aufklappbare 3D-Vorschau. ``quelle()`` liefert die :class:`VorschauDaten`
    des Dialogs; der Dialog ruft :meth:`aktualisieren` bei jeder Aenderung und
    :meth:`abbauen` beim Schliessen."""

    def __init__(self, quelle: Callable[[], VorschauDaten], parent=None):
        super().__init__(parent)
        self._quelle = quelle
        self._view = None             # QWebEngineView — erst beim Aufklappen
        self._bereit = False          # Szene meldet __lightosAppReady
        self._bereit_seit_ms = 0
        self._guard = None
        self._gobos: list[tuple[str, str]] = []
        #: zuletzt an die Seite geschickt (Test-/Diagnose-Seam).
        self.letzter_geraet_payload: dict | None = None
        self.letzter_licht_payload: dict | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        zeile = QHBoxLayout()
        zeile.setSpacing(8)
        self.btn = QPushButton(KNOPF_ZEIGEN)
        self.btn.setCheckable(True)
        self.btn.setToolTip(KNOPF_TOOLTIP)
        self.btn.setAccessibleName("3D-Vorschau zeigen")
        self.btn.toggled.connect(self._umschalten)
        zeile.addWidget(self.btn)

        self.lbl_zoom = QLabel("Zoom:")
        self.sld_zoom = QSlider(Qt.Orientation.Horizontal)
        self.sld_zoom.setRange(0, 255)
        self.sld_zoom.setValue(128)
        self.sld_zoom.setMinimumWidth(110)
        self.sld_zoom.setAccessibleName("Zoom der Vorschau")
        self.sld_zoom.setToolTip(
            "Zoom-Kanal (DMX 0–255) der Vorschau — der Kegel läuft zwischen "
            "dem engsten und dem weitesten Abstrahlwinkel. Nur in der Vorschau, "
            "nicht am Gerät.")
        self.sld_zoom.valueChanged.connect(lambda *_: self._licht_senden())
        zeile.addWidget(self.lbl_zoom)
        zeile.addWidget(self.sld_zoom, 1)

        self.lbl_gobo = QLabel("Gobo:")
        self.cb_gobo = QComboBox()
        self.cb_gobo.setAccessibleName("Gobo der Vorschau")
        self.cb_gobo.setToolTip(
            "Ein Gobo aus der Gobo-Liste dieses Profils in den Strahl der "
            "Vorschau legen. Die Liste kommt aus den Bereichen des Gobo-Kanals.")
        self.cb_gobo.currentIndexChanged.connect(lambda *_: self._licht_senden())
        zeile.addWidget(self.lbl_gobo)
        zeile.addWidget(self.cb_gobo)

        self.lbl_farbe = QLabel("Farbe:")
        zeile.addWidget(self.lbl_farbe)
        self.cb_farbe = QComboBox()
        self.cb_farbe.setAccessibleName("Farbe der Vorschau")
        self.cb_farbe.setToolTip("Lichtfarbe der Vorschau (Standard: Weiß).")
        for name, rgb in FARBEN:
            self.cb_farbe.addItem(name, rgb)
        self.cb_farbe.currentIndexChanged.connect(lambda *_: self._licht_senden())
        zeile.addWidget(self.cb_farbe)
        zeile.addStretch(0)
        lay.addLayout(zeile)

        self.lbl_hinweis = QLabel("")
        self.lbl_hinweis.setWordWrap(True)
        self.lbl_hinweis.setStyleSheet("color: #9aa4b0; padding: 4px 2px;")
        self.lbl_hinweis.setHidden(True)
        lay.addWidget(self.lbl_hinweis)
        self._view_platz = QVBoxLayout()
        self._view_platz.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._view_platz)

        self._bereit_timer = QTimer(self)
        self._bereit_timer.setInterval(_BEREIT_TAKT_MS)
        self._bereit_timer.timeout.connect(self._nach_bereit_fragen)
        self._bedienung_nachziehen()

    # ── oeffentliche API ────────────────────────────────────────────────
    @property
    def geladen(self) -> bool:
        """Gibt es gerade eine WebEngine-Ansicht?"""
        return self._view is not None

    @property
    def view(self):
        return self._view

    def aktualisieren(self) -> None:
        """Dialog hat sich geaendert: Bedienung nachziehen und — wenn die
        Szene laeuft — Geraet neu bauen und Licht schicken."""
        self._bedienung_nachziehen()
        if self._bereit:
            self._geraet_senden()

    def zeigen(self) -> None:
        if not self.btn.isChecked():
            self.btn.setChecked(True)     # -> _umschalten(True)

    def abbauen(self) -> None:
        """WebEngine-Ansicht sauber abbauen (Zuklappen, Dialog schliesst).

        Muster wie im Visualizer: Zeitgeber stoppen, WebChannel trennen,
        Seite anhalten, ``deleteLater`` — der Rest der Vorschau bleibt
        bedienbar und kann spaeter neu laden. Mehrfach-Aufruf ist harmlos."""
        self._bereit_timer.stop()
        self._bereit = False
        view, self._view = self._view, None
        self._guard = None
        if view is None:
            return
        try:
            view.loadFinished.disconnect(self._geladen)
        except (RuntimeError, TypeError):
            pass
        try:
            view.page().setWebChannel(None)
        except Exception:                                # noqa: BLE001
            pass
        try:
            view.stop()
        except Exception:                                # noqa: BLE001
            pass
        try:
            self._view_platz.removeWidget(view)
            view.hide()
            view.setParent(None)
            view.deleteLater()
        except RuntimeError:
            pass

    # ── intern ──────────────────────────────────────────────────────────
    def _daten(self) -> VorschauDaten:
        try:
            d = self._quelle()
        except Exception:                                # noqa: BLE001
            d = None
        return d if isinstance(d, VorschauDaten) else VorschauDaten()

    def _bedienung_nachziehen(self) -> None:
        d = self._daten()
        offen = self.btn.isChecked()
        zoom = hat_zoom_spanne(d)
        for w in (self.lbl_zoom, self.sld_zoom):
            w.setVisible(offen and zoom)
        try:
            gobos = gobo_auswahl(d.kanaele)
        except Exception:                                # noqa: BLE001
            gobos = []
        if gobos != self._gobos:
            alt = self.cb_gobo.currentText()
            self._gobos = gobos
            self.cb_gobo.blockSignals(True)
            self.cb_gobo.clear()
            self.cb_gobo.addItem("offen (kein Gobo)", "")
            for name, stil in gobos:
                self.cb_gobo.addItem(name, stil)
            i = self.cb_gobo.findText(alt)
            self.cb_gobo.setCurrentIndex(i if i >= 0 else 0)
            self.cb_gobo.blockSignals(False)
        for w in (self.lbl_gobo, self.cb_gobo):
            w.setVisible(offen and bool(gobos))
        for w in (self.lbl_farbe, self.cb_farbe):
            w.setVisible(offen)

    def _umschalten(self, an: bool) -> None:
        self.btn.setText(KNOPF_VERBERGEN if an else KNOPF_ZEIGEN)
        self.btn.setAccessibleName("3D-Vorschau ausblenden" if an else "3D-Vorschau zeigen")
        if an:
            self._laden()
        else:
            self.abbauen()
            self.lbl_hinweis.setHidden(True)
        self._bedienung_nachziehen()

    def _hinweis(self, text: str) -> None:
        self.lbl_hinweis.setText(text)
        self.lbl_hinweis.setHidden(not text)

    def _baue_view(self):
        """Die WebEngine-Ansicht bauen (eigene Methode: Tests ersetzen sie,
        um den Fall „keine QtWebEngine“ zu pruefen)."""
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
        view = QWebEngineView(self)
        try:
            from src.ui.visualizer.js_konsole import installiere_js_konsole
            installiere_js_konsole(view, "vorschau")
        except Exception:                                # noqa: BLE001
            pass
        try:
            profil = view.page().profile()
            profil.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profil.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        except Exception:                                # noqa: BLE001
            pass
        s = view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        return view

    def _laden(self) -> None:
        if self._view is not None:
            return
        try:
            view = self._baue_view()
        except Exception:                                # noqa: BLE001
            self._hinweis(HINWEIS_KEINE_ENGINE)
            return
        self._view = view
        view.setMinimumHeight(VORSCHAU_HOEHE_PX)
        view.setMaximumHeight(VORSCHAU_HOEHE_PX)
        self._view_platz.addWidget(view)
        self._hinweis(HINWEIS_LAEDT)
        from src.ui.visualizer.visualizer_window import (
            install_scene_start_guard, load_stage_html)
        ich = weakref.ref(self)

        def _startet_nicht(_msg, _ich=ich):
            w = _ich()
            if w is not None:
                w._szene_startet_nicht()
        # VIZ-SCENE-SELFHEAL: einmal neu laden, danach der Hinweis.
        self._guard = install_scene_start_guard(view, status_cb=_startet_nicht)
        view.loadFinished.connect(self._geladen)
        view.show()
        vref = weakref.ref(view)

        def _jetzt_laden(_vref=vref, _ich=ich):
            # Erst laden, wenn die Ansicht im Layout steht: eine Seite, die
            # schon vor dem Einblenden startet, bekam offscreen gemessen
            # deutlich oefter keinen WebGL-Kontext.
            v, w = _vref(), _ich()
            if v is None or w is None or w._view is not v:
                return
            load_stage_html(v, VORSCHAU_QUERY)
        QTimer.singleShot(0, _jetzt_laden)

    def _geladen(self, ok: bool) -> None:
        if not ok or self._view is None:
            return
        self._bereit = False
        self._bereit_seit_ms = 0
        self._bereit_timer.start()

    def _nach_bereit_fragen(self) -> None:
        view = self._view
        if view is None:
            self._bereit_timer.stop()
            return
        self._bereit_seit_ms += _BEREIT_TAKT_MS
        if self._bereit_seit_ms > _BEREIT_DECKEL_MS:
            self._bereit_timer.stop()
            return
        from src.ui.visualizer.visualizer_window import SCENE_START_JS, lese_startstatus
        ich = weakref.ref(self)

        def _antwort(r, _ich=ich):
            w = _ich()
            if w is None or w._view is None or w._bereit:
                return
            bereit, _grund = lese_startstatus(r)
            if bereit:
                w._bereit_timer.stop()
                w._bereit = True
                w._hinweis("")
                w._geraet_senden(erzwingen=True)    # neue Seite: neu bauen
        try:
            view.page().runJavaScript(SCENE_START_JS, _antwort)
        except Exception:                                # noqa: BLE001
            pass

    def _szene_startet_nicht(self) -> None:
        """Auch der zweite Start kam nicht hoch (kein WebGL): Hinweis statt
        leerer Flaeche, Ansicht abbauen."""
        self.abbauen()
        self._hinweis(HINWEIS_KEIN_WEBGL)

    def _js(self, skript: str) -> None:
        view = self._view
        if view is None:
            return
        try:
            view.page().runJavaScript(skript)
        except Exception:                                # noqa: BLE001
            pass

    def _geraet_senden(self, erzwingen: bool = False) -> None:
        payload = geraet_payload(self._daten())
        if not erzwingen and payload == self.letzter_geraet_payload:
            # Nichts am Geraet geaendert (der Generator ruft nach jeder
            # Eingabe, auch im Namensfeld) — nicht neu bauen, nur Licht.
            self._licht_senden()
            return
        self.letzter_geraet_payload = payload
        self._js("(function(){var L=window.__lightos;return(L&&L.vorschauGeraet)?"
                 "L.vorschauGeraet(%s):-1;})()"
                 % json.dumps(payload, ensure_ascii=True))
        self._licht_senden()

    def _licht_senden(self) -> None:
        d = self._daten()
        farbe = self.cb_farbe.currentData() or (255, 255, 255)
        zoom = self.sld_zoom.value() if hat_zoom_spanne(d) else None
        gobo = (self.cb_gobo.currentData() or "") if self._gobos else None
        payload = licht_payload(farbe, zoom=zoom, gobo=gobo)
        self.letzter_licht_payload = payload
        if not self._bereit:
            return
        from src.ui.visualizer.dmx_push import push_script
        self._js(push_script([(None, payload)]))
