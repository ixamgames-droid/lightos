"""VIZ-52-TOOLTIP — der Tooltip der „Montage-Drehung" gegen das, was die
3D-Vorschau WIRKLICH tut.

Der Satz „im 3D sieht es richtig aus, am Rig nicht" war richtig, solange die
Montage-Drehung den Renderer nie erreichte. Seit VIZ-52 (#614) kippt das
Pixelraster in der Vorschau mit — die Erklaerung sagt seither das Gegenteil
dessen, was gilt, und **eine veraltete Erklaerung ist schlimmer als keine**:
sie schickt die Fehlersuche in die falsche Richtung („die Vorschau luegt
sowieso"), obwohl die Vorschau genau die Stelle ist, an der man eine falsche
Angabe jetzt sieht.

★ Der springende Punkt dieser Datei: **ein Test, der den neuen Wortlaut sucht,
veraltet genauso wie der alte Text.** Der naechste Umbau am Renderer macht die
Aussage wieder falsch, und ein Wortlaut-Pin bliebe gruen. Deshalb steht die
ERWARTUNG hier nicht als Zeichenkette im Test, sondern wird bei jedem Lauf
GEMESSEN:

    1. Dasselbe Matrix-Panel wird ZWEIMAL durch die echte QtWebEngine-Bridge
       gebaut — einmal normal montiert, einmal auf 90 Grad. Gemessen wird die
       Laufrichtung der ersten Geraetezeile in der GEOMETRIE (die Mesh-
       Positionen von Pixel 0 und Pixel 1), nicht am Quelltext und nicht an
       einem Buchfuehrungsfeld.
    2. Aus dieser Messung folgt, WELCHE der beiden moeglichen Aussagen ueber
       die Vorschau wahr ist.
    3. Der ECHTE Tooltip des ECHTEN Dialogs wird eingeordnet und muss genau
       diese Aussage machen.

Wird VIZ-52 zurueckgedreht, kippt die Messung — und dieselbe Datei verlangt
dann den alten Satz zurueck. Genau das kann ein Wortlaut-Test nicht.

**Die Einordnung von Prosa ist der einzige Schritt, der Vokabular braucht.**
Sie ist bewusst klein gehalten und faellt SICHER aus: was sich keiner der
beiden Aussagen zuordnen laesst, gilt als „sagt nichts Nachpruefbares" und
macht den Test rot. Ein neu erfundener Falschsatz kommt also nicht durch,
indem er dem Vokabular ausweicht — er muesste die BEJAHENDE Aussage machen,
und die ist nur richtig, solange die Messung sie deckt. Dass der Klassifikator
die Aussage trifft, die er treffen soll, wird an beiden Wortlauten belegt, die
es in diesem Projekt gab (Positivkontrollen unten).
"""
from __future__ import annotations

import json
import os
import re
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                       # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView            # noqa: E402
from PySide6.QtWebEngineCore import (QWebEngineProfile,          # noqa: E402
                                     QWebEngineSettings)
from PySide6.QtWebChannel import QWebChannel                     # noqa: E402
from PySide6.QtCore import QUrl                                  # noqa: E402
from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

import pytest as _pytest_xplat15                                 # noqa: E402
from _qt_lifecycle import (destroy_all_top_level_widgets,        # noqa: E402
                           destroy_webengine_view)

# Bridge-Attrappe und Pfad der ECHTEN Produktiv-Page aus dem bestehenden
# Szenen-Test uebernehmen statt hier nachzubauen: die Liste der 22 Signale, die
# `scene_src/bridge/bridge.js#tryChannel()` verbindet, darf es nur EINMAL geben
# — eine zweite Kopie faellt beim naechsten Signal lautlos auseinander.
from test_viz13_scene_modules_smoke import (_HTML_PATH,          # noqa: E402
                                            _MockVisualizerBridge)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


_LADE_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

# Davids Geraet, ein echtes Profil aus der Bibliothek: 48 einzeln faerbbare
# Zonen. Dasselbe Geraet liefert den Dialog, in dem der Tooltip haengt, UND das
# Panel, das durch die Bridge geht — es soll nicht der Text ueber das eine und
# die Messung ueber ein anderes Geraet reden.
MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"
KANAELE = 154
ZONEN = 48


# ── Prosa -> Aussage ────────────────────────────────────────────────────────
#
# Zwei Aussagen sind ueber die Vorschau ueberhaupt moeglich, und genau eine
# davon ist wahr — welche, entscheidet die Messung weiter unten, nicht diese
# Liste. Die Vokabeln ordnen nur ein, WELCHE der beiden der Text macht.

ZEIGT_DIE_MONTAGE = "die Vorschau zeigt die Montage"
ZEIGT_SIE_NICHT = "die Vorschau zeigt die Montage NICHT"
SAGT_NICHTS = "sagt nichts Nachpruefbares ueber die Vorschau"
WIDERSPRUECHLICH = "sagt beides zugleich"

# Wendungen, die nur stimmen, wenn die Vorschau die Montage ZEIGT.
_WORTE_ZEIGT = (
    "zeigt die montage", "zeigt die drehung", "zeigt sie mit",
    "kippt", "dreht mit", "dreht sich mit", "kennt die montage",
    "beruecksichtigt die montage", "springt um", "auch dort", "genauso",
)
# Wendungen, die nur stimmen, wenn die Vorschau die Montage IGNORIERT — der
# Zustand vor VIZ-52, in dem die Vorschau ein gedreht montiertes Panel wie ein
# normal montiertes zeichnete.
_WORTE_ZEIGT_NICHT = (
    "sieht es richtig aus", "sieht richtig aus", "sieht alles richtig aus",
    "stimmt es", "ist es richtig", "bleibt unveraendert", "bleibt gleich",
    "immer gleich", "ignoriert", "nicht beachtet", "beachtet sie nicht",
    "unbeeindruckt", "faellt dort nicht auf",
)


def _norm(text: str) -> str:
    """Kleinschreibung, Umlaute aufgeloest, Zeilenumbrueche zu Leerzeichen.

    Zeilenumbrueche sind im Tooltip UMBRUECHE, keine Satzenden — der Satz ueber
    die Vorschau laeuft ueber mehrere Zeilen.
    """
    t = text.lower()
    for zeichen, ersatz in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(zeichen, ersatz)
    return re.sub(r"\s+", " ", t.replace("\n", " ")).strip()


def aussage_ueber_die_vorschau(tooltip: str) -> str:
    """Welche der beiden moeglichen Aussagen macht dieser Text?

    Betrachtet werden nur Saetze, die die 3D-Vorschau ueberhaupt erwaehnen —
    sonst wuerde eine Wendung aus einem Satz ueber etwas ganz anderes
    (Nummerierung, DMX-Adressen) mitgezaehlt.
    """
    saetze = [s for s in _norm(tooltip).split(".")
              if "3d" in s or "vorschau" in s]
    zeigt = any(w in s for s in saetze for w in _WORTE_ZEIGT)
    zeigt_nicht = any(w in s for s in saetze for w in _WORTE_ZEIGT_NICHT)
    if zeigt and zeigt_nicht:
        return WIDERSPRUECHLICH
    if zeigt:
        return ZEIGT_DIE_MONTAGE
    if zeigt_nicht:
        return ZEIGT_SIE_NICHT
    return SAGT_NICHTS


def erwartete_aussage(vorschau_zeigt_die_montage: bool) -> str:
    """Die Aussage, die der Tooltip machen MUSS — abgeleitet aus der Messung."""
    return ZEIGT_DIE_MONTAGE if vorschau_zeigt_die_montage else ZEIGT_SIE_NICHT


# Der Wortlaut, der bis zu diesem Fix im Dialog stand (Stand 873cf1cf). Er ist
# hier KEIN Pin auf Produktionscode, sondern der Pruefstein fuer den
# Klassifikator: dieser Satz ist die Aussage, die falsch geworden ist.
ALTER_WORTLAUT = (
    "Dasselbe Panel haengt mal waagerecht, mal hochkant. Ohne diese\n"
    "Angabe laeuft ein waagerechtes Lauflicht am hochkant montierten\n"
    "Geraet senkrecht — im 3D sieht es richtig aus, am Rig nicht.\n")


class KlassifikatorTest(unittest.TestCase):
    """Belegt, dass der Prosa-Schritt die Aussage trifft, die er treffen soll.

    Ohne diese Kontrollen waere die Einordnung eine Behauptung — und ein
    Klassifikator, der IMMER dasselbe liefert, machte den Kerntest wertlos.
    """

    def test_erkennt_die_alte_aussage(self):
        self.assertEqual(ZEIGT_SIE_NICHT,
                         aussage_ueber_die_vorschau(ALTER_WORTLAUT))

    def test_erkennt_die_aussage_des_heutigen_dialogs(self):
        """Der ECHTE Tooltip — nicht eine Kopie davon."""
        tip = tooltip_der_montage_drehung(self)
        self.assertEqual(
            ZEIGT_DIE_MONTAGE, aussage_ueber_die_vorschau(tip),
            f"der heutige Tooltip laesst sich nicht als bejahende Aussage "
            f"lesen: {tip!r}")

    def test_schweigen_ist_kein_freibrief(self):
        """★ Der Ausweg, den es nicht geben darf: die Aussage einfach weglassen
        und damit durchrutschen. Was nichts Nachpruefbares sagt, faellt in eine
        eigene Klasse — und die ist im Kerntest weder das eine noch das andere,
        also rot."""
        stumm = ("Wie das Panel MONTIERT ist. 180 Grad ist der Fall "
                 "„kopfueber montiert\". Aendert NUR die Zuordnung.")
        self.assertEqual(SAGT_NICHTS, aussage_ueber_die_vorschau(stumm))

    def test_meldet_widerspruch_statt_ihn_zu_schlucken(self):
        beides = (ALTER_WORTLAUT +
                  "\nDie 3D-Vorschau zeigt die Montage mit.")
        self.assertEqual(WIDERSPRUECHLICH, aussage_ueber_die_vorschau(beides))

    def test_saetze_ohne_vorschau_zaehlen_nicht(self):
        """★ Sonst schluege eine Wendung aus einem Satz an, der von etwas ganz
        anderem handelt — und der Tooltip waere fuer immer an eine Wortwahl
        gebunden, die mit der Vorschau nichts zu tun hat."""
        daneben = ("Die Pixel-Reihenfolge bleibt unveraendert. "
                   "Aendert NUR die Zuordnung, nie die DMX-Adressen.")
        self.assertEqual(SAGT_NICHTS, aussage_ueber_die_vorschau(daneben))

    def test_die_alte_aussage_passte_zum_damaligen_verhalten(self):
        """★ POSITIVKONTROLLE: die Pruefung schlaegt NICHT auf den Wortlaut an,
        sondern auf den Widerspruch zwischen Wortlaut und Verhalten.

        Zeigte die Vorschau die Montage nicht — der Zustand vor VIZ-52 —, dann
        war der alte Satz genau die richtige Auskunft und diese Datei haette
        ihn nicht beanstandet. Ohne diesen Test waere nicht zu unterscheiden,
        ob hier Verhalten gemessen oder nur ein missliebiger Satz verboten wird.
        """
        self.assertEqual(erwartete_aussage(False),
                         aussage_ueber_die_vorschau(ALTER_WORTLAUT))
        self.assertNotEqual(erwartete_aussage(True),
                            aussage_ueber_die_vorschau(ALTER_WORTLAUT))


def panel_patchen(fid: int, adresse: int, drehung: int = 0):
    """Patcht Davids Panel mit der angegebenen Montage-Drehung und liefert das
    gespeicherte Geraet zurueck (gelesen aus dem Zustand, nicht das uebergebene
    Objekt — was nicht ankommt, soll hier auffallen)."""
    from src.core.app_state import get_state
    from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
    from src.core.database.models import FixtureProfile, PatchedFixture

    QApplication.instance() or QApplication([])
    ensure_builtins()
    state = get_state()
    with Session(fdb_engine()) as s:
        pid = int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == "ZQ06121")).scalar_one())
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"Balken {fid}", fixture_profile_id=pid,
        mode_name=MODUS, universe=1, address=adresse, channel_count=KANAELE,
        manufacturer_name="U King",
        fixture_name="ZQ06121 LED-Balken 768 (stage light)",
        fixture_type="matrix", element_rotation=drehung), undoable=False)
    return next(f for f in state.get_patched_fixtures() if f.fid == fid)


def bridge_nutzlast(fx) -> dict:
    """Die Nutzlast, die der Visualizer WIRKLICH verschickt.

    Bewusst ueber die Produktionsmethode ``VisualizerBridge._fixture_to_dict``
    statt von Hand zusammengeschrieben: haende man dem Renderer eine
    handgeschriebene Nutzlast, bliebe die Messung gruen, selbst wenn die
    Montage-Drehung schon auf dem Weg zur Bridge verloren ginge — und genau
    daran ist das Feature bis VIZ-52 gescheitert.

    Die Bridge selbst braucht ein ganzes Visualizer-Fenster; gebunden wird
    deshalb nur, was ``_fixture_to_dict`` anfasst: der ECHTE Anwendungszustand
    und die ECHTE Modellwahl. Gerechnet wird nichts davon hier.
    """
    import types
    import src.ui.visualizer.visualizer_window as VW
    from src.core.app_state import get_state

    ersatz_self = types.SimpleNamespace(_state=get_state())
    ersatz_self._viz_model_for = types.MethodType(
        VW.VisualizerBridge._viz_model_for, ersatz_self)
    return VW.VisualizerBridge._fixture_to_dict(ersatz_self, fx)


def tooltip_der_montage_drehung(test: unittest.TestCase) -> str:
    """Der Hover-Text des ECHTEN Auswahlfeldes im ECHTEN Patch-Dialog.

    Kein Quelltext-Lesen: gefragt wird das gebaute Widget. Wer das Feld
    umbaut oder den Tooltip woanders hinhaengt, macht diese Datei rot.
    """
    from src.core.show.show_file import reset_show
    from src.ui.views.patch_view import PatchFixtureEditDialog
    from src.core.app_state import get_state

    reset_show()
    fx = panel_patchen(1, 1)
    dlg = PatchFixtureEditDialog(get_state(), fx)
    test.addCleanup(dlg.deleteLater)
    test.assertIsNotNone(dlg._combo_rotation,
                         "das Panel hat kein Auswahlfeld „Montage-Drehung"
                         "“ mehr — dann gibt es auch nichts zu erklaeren")
    return dlg._combo_rotation.toolTip()


class AussageGegenVerhaltenTest(unittest.TestCase):
    """★★ Der Kerntest: gemessene Vorschau gegen den Text im Dialog."""

    def setUp(self):
        self.assertTrue(os.path.isfile(_HTML_PATH),
                        f"stage_scene.html fehlt: {_HTML_PATH}")
        self._app = QApplication.instance() or QApplication([])
        self._view = QWebEngineView()
        # Identische Konfiguration zur Produktiv-Page (visualizer_window.py):
        # NoCache-Profil + file://-Modul-Importe erlaubt.
        try:
            profil = self._view.page().profile()
            profil.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profil.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        self._bridge = _MockVisualizerBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        self._geladen = []
        self._view.loadFinished.connect(self._geladen.append)

    def tearDown(self):
        # XPLAT-09: `deleteLater()` allein raeumt hier nichts ab; der View
        # ueberlebte mitsamt Page und Renderer, waehrend die parentlose Bridge
        # mit der TestCase-Instanz stirbt -> dangling QObject -> SIGSEGV.
        destroy_webengine_view(self._view, self._pump)
        self._view = None

    # ── Bridge-Werkzeug ────────────────────────────────────────────────────
    def _pump(self, sekunden):
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            self._app.processEvents()
            time.sleep(_POLL_INTERVAL_S)

    def _laden(self):
        self._geladen.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        ende = time.monotonic() + _LADE_TIMEOUT_S
        while not self._geladen and time.monotonic() < ende:
            self._app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._geladen, "loadFinished nie ausgeloest (Timeout)")
        self.assertTrue(self._geladen[-1],
                        "stage_scene.html konnte nicht geladen werden")

    def _eval(self, js):
        kasten = []
        self._view.page().runJavaScript(js, kasten.append)
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while not kasten and time.monotonic() < ende:
            self._app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(kasten, f"kein Ergebnis fuer: {js}")
        return kasten[0]

    def _emit_bis(self, emit_fn, js, timeout_s=_POLL_TIMEOUT_S):
        """Wiederholt den Emit, bis der Ausdruck truthy wird — der
        WebChannel-Connect baut sich asynchron auf, ein einzelner Emit davor
        ginge verloren. Der Fixture-Aufbau ist gegenueber Wiederholung mit
        derselben Nutzlast idempotent."""
        ende = time.monotonic() + timeout_s
        letzt = None
        while time.monotonic() < ende:
            emit_fn()
            letzt = self._eval(js)
            if letzt:
                return letzt
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf '{js}' (zuletzt: {letzt!r})")

    def _panel_bauen(self, fid, adresse, drehung):
        """Patcht das Panel, laesst die PRODUKTION die Nutzlast bauen und
        schickt sie durch die ECHTE Bridge; zurueck kommt ein JS-Abfrager auf
        das gebaute Fixture.

        Damit haengt die ganze Kette am Test: Geraet -> gespeicherte Drehung ->
        Bridge-Nutzlast -> fixtures.js -> Panel-Bauer -> Geometrie. Faellt die
        Drehung an irgendeiner dieser Stellen heraus, sieht die Vorschau die
        Montage nicht mehr — und dieser Test verlangt dann eine andere Auskunft
        im Dialog.
        """
        fx = panel_patchen(fid, adresse, drehung)
        self.assertEqual(
            drehung, int(getattr(fx, "element_rotation", 0) or 0),
            "die Montage-Drehung kam schon im Patch nicht an")
        nutzlast = json.dumps([bridge_nutzlast(fx)])
        gebaut = self._emit_bis(
            lambda: self._bridge.allFixtures.emit(nutzlast),
            f"(function(){{const f=window.__lightos.fixtures['{fid}'];"
            f" return !!(f && f.pixels && f.pixels.length==={ZONEN}"
            f"          && f.pixels[0].mesh && f.pixels[1].mesh);}})()",
            timeout_s=8.0)
        self.assertTrue(gebaut, f"Panel {fid} wurde nicht gebaut")

        def _js(ausdruck):
            # Einzelwerte statt Array: eine Liste kommt ueber die Bridge nicht
            # zuverlaessig zurueck (die Falle aus VIZ-51).
            return self._eval(
                f"(function(){{const f=window.__lightos.fixtures['{fid}'];"
                f" return {ausdruck};}})()")
        return _js

    def _laufrichtung(self, js) -> str:
        """Wohin laeuft die erste Zeile des GERAETS in der Vorschau?

        Pixel 0 und Pixel 1 sind auf dem Geraet direkte Nachbarn derselben
        DMX-Zeile. Gemessen wird ihr Abstand in der GEOMETRIE (Mesh-Position),
        nicht im r/c-Buchfuehrungsfeld: eine Drehung, die nur die Buchfuehrung
        erreicht, sieht der Benutzer nicht.
        """
        dx = js("f.pixels[1].mesh.position.x - f.pixels[0].mesh.position.x")
        dy = js("f.pixels[1].mesh.position.y - f.pixels[0].mesh.position.y")
        # JS-Zahlen kommen je nach Wert als int oder float zurueck; `None`
        # hiesse, die Abfrage ist ins Leere gelaufen — das darf nicht als
        # „kein Unterschied" durchgehen.
        for name, wert in (("dx", dx), ("dy", dy)):
            self.assertIsInstance(
                wert, (int, float),
                f"{name} kam nicht als Zahl zurueck ({wert!r}) — die "
                f"Mesh-Position wurde gar nicht gemessen")
        self.assertGreater(
            max(abs(dx), abs(dy)), 1e-6,
            "Pixel 0 und Pixel 1 sitzen an derselben Stelle — dann misst "
            "dieser Test gar keine Laufrichtung mehr")
        return "waagerecht" if abs(dx) > abs(dy) else "senkrecht"

    def _zeigt_die_vorschau_die_montage(self) -> bool:
        """Die Messung, aus der die Erwartung an den Text folgt.

        Dasselbe Panel zweimal: normal montiert und auf 90 Grad. Zeigt die
        Vorschau die Montage, laeuft die Geraetezeile im zweiten Fall quer.
        """
        from src.core.show.show_file import reset_show
        reset_show()
        self._laden()
        gerade = self._panel_bauen(1, 1, 0)
        hochkant = self._panel_bauen(2, 200, 90)
        richtung_gerade = self._laufrichtung(gerade)
        # Verankerung der Messung: ein normal montiertes Panel MUSS seine
        # DMX-Zeile waagerecht zeigen. Ohne diese Klammer koennte die Messung
        # kaputt sein (beide Richtungen gleich, weil gar nichts ankommt) und
        # der Test bekaeme trotzdem ein sauber aussehendes „False".
        self.assertEqual(
            "waagerecht", richtung_gerade,
            "schon das normal montierte Panel zeigt seine DMX-Zeile nicht "
            "waagerecht — dann misst dieser Test nicht, was er misst")
        return richtung_gerade != self._laufrichtung(hochkant)

    def test_der_tooltip_sagt_ueber_die_vorschau_was_die_vorschau_tut(self):
        """★★ Aussage gegen Verhalten — nicht gegen Wortlaut.

        Beides wird in diesem Lauf frisch geholt: die Aussage aus dem echten
        Dialog, das Verhalten aus dem echten 3D-Modell. Kippt eines von
        beiden, kippt der Test.
        """
        zeigt = self._zeigt_die_vorschau_die_montage()
        tip = tooltip_der_montage_drehung(self)
        self.assertEqual(
            erwartete_aussage(zeigt), aussage_ueber_die_vorschau(tip),
            f"Gemessen: die 3D-Vorschau zeigt die Montage "
            f"{'' if zeigt else 'NICHT '}— der Tooltip sagt etwas anderes.\n"
            f"Tooltip:\n{tip}")

    def test_die_messung_sieht_eine_echte_drehung(self):
        """★ Kontrolle zur Messung selbst: „quer" darf nicht schon durch
        irgendeine Abweichung entstehen.

        Eine Drehung um 90 Grad im Uhrzeigersinn schiebt die oberste ZEILE des
        Geraets in die rechte SPALTE: Pixel 0 wandert von der linken oberen
        Ecke in die rechte obere, Pixel 1 rueckt darunter. Waeren die Pixel
        bloss durchmischt (oder nur gespiegelt — dann bliebe Pixel 1 NEBEN
        Pixel 0), traefe die Laufrichtung zufaellig zu und die Auskunft „die
        Vorschau zeigt die Montage" waere trotz gruener Messung falsch.

        48 Zonen ergeben ein 7x7-Raster, die Ecke liegt also in Spalte 6.
        """
        from src.core.show.show_file import reset_show
        reset_show()
        self._laden()
        gerade = self._panel_bauen(1, 1, 0)
        hochkant = self._panel_bauen(2, 200, 90)

        for name, js, erwartet in (("normal montiert", gerade, (0, 0)),
                                   ("auf 90 Grad", hochkant, (0, 6))):
            self.assertEqual(
                erwartet, (js("f.pixels[0].r"), js("f.pixels[0].c")),
                f"{name}: Pixel 0 sitzt nicht in Zeile/Spalte {erwartet}")
        self.assertEqual(
            (1, 6), (hochkant("f.pixels[1].r"), hochkant("f.pixels[1].c")),
            "bei 90 Grad muss Pixel 1 UNTER Pixel 0 rutschen — bliebe es "
            "daneben, waere das eine Spiegelung, keine Drehung")

        # Und zwar in der Geometrie, nicht nur in den Buchfuehrungs-Feldern:
        # Pixel 0 wechselt von der linken auf die rechte Panel-Haelfte.
        self.assertLess(gerade("f.pixels[0].mesh.position.x"), 0.0,
                        "normal montiert sitzt Pixel 0 links der Panel-Mitte")
        self.assertGreater(hochkant("f.pixels[0].mesh.position.x"), 0.0,
                           "gedreht sitzt Pixel 0 rechts der Panel-Mitte")


if __name__ == "__main__":
    unittest.main()
