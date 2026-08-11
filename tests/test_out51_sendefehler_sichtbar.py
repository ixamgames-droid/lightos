"""OUT-51 — Sendefehler werden gezaehlt und gemeldet, und die Statusanzeige
fragt den echten Portstatus.

★ **Worum es geht.** Der Ausgabepfad hatte drei blanke ``except Exception:
pass`` um ``send_dmx`` und zwei weitere um Tick-Callbacks und Channel-Modifier.
Ein Geraet konnte mitten in der Show ausfallen, ohne dass irgendwo etwas
erschien. Gleichzeitig faerbte die Statusleiste gruen, sobald ein Adapter
REGISTRIERT war — nicht, wenn er sendet. Am 2026-08-05 hat genau diese Anzeige
bei der Fehlersuche aktiv in die Irre gefuehrt: sie meldete „aktiv", waehrend
das Rig dunkel blieb.

★ **Was diese Tests deshalb pruefen — und was nicht.** Nicht, dass irgendwo ein
``print`` steht. Sondern die drei Eigenschaften, die den Unterschied machen:

1. ein ANHALTENDER Ausfall wird sichtbar, ein einzelner Hickup nicht,
2. die Meldung ist gedrosselt — sonst begraebt eine 44-Hz-Log-Flut genau das,
   was sie zeigen soll,
3. die Anzeige unterscheidet *sendet* von *registriert* von *weiss es nicht*.
"""
import io
import types
import unittest
from contextlib import redirect_stderr
from unittest import mock

from src.core.dmx.output_manager import (
    OutputManager, SENDE_FEHLER_SCHWELLE, geraet_zustand, geraet_verbunden,
    ZUSTAND_SENDET, ZUSTAND_TOT, ZUSTAND_VERBINDET, ZUSTAND_UNBEKANNT)


class _KaputterAdapter:
    """Ausgabegeraet, das bei jedem Frame wirft (abgezogenes Kabel)."""

    def __init__(self, fehler=OSError("Network is unreachable")):
        self.fehler = fehler
        self.versuche = 0
        self.port = "/dev/ttyTEST"

    def send_dmx(self, *args):
        self.versuche += 1
        if self.fehler is not None:
            raise self.fehler


def _manager_mit(weg: str, dev, universum: int = 1) -> OutputManager:
    """Einen OutputManager mit genau einem registrierten Ausgang bauen."""
    om = OutputManager()
    om.add_universe(universum)
    {"Enttec": om._enttec_outputs,
     "Art-Net": om._artnet_outputs,
     "sACN": om._sacn_outputs}[weg][universum] = dev
    return om


def _frames(om: OutputManager, n: int):
    """``n`` Frames senden — wie es der Output-Thread taete, nur ohne Thread."""
    for _ in range(n):
        om._send_all()


class AnhaltenderAusfallWirdSichtbarTest(unittest.TestCase):
    """Der Kern des Items: ein Ausfall darf nicht spurlos bleiben."""

    def test_enttec_ausfall_erscheint_in_sende_probleme(self):
        om = _manager_mit("Enttec", _KaputterAdapter())
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        probleme = om.sende_probleme()
        self.assertEqual(1, len(probleme))
        self.assertEqual("Enttec", probleme[0]["weg"])
        self.assertEqual(1, probleme[0]["universum"])
        self.assertIn("Network is unreachable", probleme[0]["text"])

    def test_alle_drei_ausgabewege_werden_erfasst(self):
        """Der Fehler stand dreimal im selben Block — also auch dreimal geprueft."""
        for weg in ("Enttec", "Art-Net", "sACN"):
            with self.subTest(weg=weg):
                om = _manager_mit(weg, _KaputterAdapter())
                with redirect_stderr(io.StringIO()):
                    _frames(om, SENDE_FEHLER_SCHWELLE)
                self.assertEqual([weg], [p["weg"] for p in om.sende_probleme()])

    def test_ein_einzelner_hickup_meldet_nichts(self):
        """Ein verpasstes UDP-Paket ist kein Ausfall. Meldete es, waere die
        Anzeige nach einer Woche Betrieb ein Rauschen, das niemand mehr liest."""
        om = _manager_mit("sACN", _KaputterAdapter())
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _frames(om, SENDE_FEHLER_SCHWELLE - 1)
        self.assertEqual([], om.sende_probleme())
        self.assertEqual("", stderr.getvalue())

    def test_erfolg_beendet_die_serie(self):
        """Nur AUFEINANDERFOLGENDE Fehler zaehlen — sonst wuerde ein Geraet, das
        einmal pro Minute zuckt, nach einer Stunde als tot gemeldet."""
        dev = _KaputterAdapter()
        om = _manager_mit("Enttec", dev)
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE - 1)
            dev.fehler = None            # Geraet erholt sich
            _frames(om, 1)
            dev.fehler = OSError("wieder weg")
            _frames(om, SENDE_FEHLER_SCHWELLE - 1)
        self.assertEqual([], om.sende_probleme(),
                         "die Serie haette beim erfolgreichen Frame reissen muessen")

    def test_gesamtzahl_bleibt_auch_nach_erholung_stehen(self):
        """``fehler`` faellt auf 0 zurueck, ``gesamt`` nicht — sonst waere
        hinterher nicht mehr zu sehen, dass es geruckelt hat."""
        dev = _KaputterAdapter()
        om = _manager_mit("Enttec", dev)
        with redirect_stderr(io.StringIO()):
            _frames(om, 5)
            dev.fehler = None
            _frames(om, 1)
        stat = om.sende_statistik()[("Enttec", 1)]
        self.assertEqual(0, stat["fehler"])
        self.assertEqual(5, stat["gesamt"])


class MeldungIstGedrosseltTest(unittest.TestCase):
    """★ Die Eigenschaft, an der ein naiver Fix scheitert: dieser Pfad laeuft
    44 Mal pro Sekunde. Ein ``print`` je Fehlversuch waere bei abgezogenem
    Adapter eine Log-Flut, die den Befund begraebt."""

    def test_hundert_kaputte_frames_ergeben_genau_eine_meldung(self):
        om = _manager_mit("Enttec", _KaputterAdapter())
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _frames(om, 100)
        zeilen = [z for z in stderr.getvalue().splitlines() if z.strip()]
        self.assertEqual(1, len(zeilen),
                         f"erwartet genau eine Meldung, bekam: {zeilen}")
        self.assertIn("Enttec", zeilen[0])
        self.assertIn("Universum 1", zeilen[0])

    def test_die_erholung_wird_gemeldet(self):
        """Wer nur den Ausfall sieht, sucht weiter an einem Problem, das sich
        selbst behoben hat."""
        dev = _KaputterAdapter()
        om = _manager_mit("Enttec", dev)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _frames(om, SENDE_FEHLER_SCHWELLE)
            dev.fehler = None
            _frames(om, 1)
        self.assertIn("sendet wieder", stderr.getvalue())

    def test_eine_zweite_serie_meldet_erneut(self):
        """Die Drossel darf den NAECHSTEN Ausfall nicht verschlucken."""
        dev = _KaputterAdapter()
        om = _manager_mit("Enttec", dev)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _frames(om, SENDE_FEHLER_SCHWELLE)
            dev.fehler = None
            _frames(om, 1)
            dev.fehler = OSError("und wieder weg")
            _frames(om, SENDE_FEHLER_SCHWELLE)
        ausfaelle = [z for z in stderr.getvalue().splitlines()
                     if "in Folge nicht gesendet" in z]
        self.assertEqual(2, len(ausfaelle), stderr.getvalue())


class TickUndModifierTest(unittest.TestCase):
    """Die beiden anderen Stellen, an denen der Frame-Pfad still schluckte."""

    def test_werfender_tick_callback_wird_gemeldet(self):
        """Ein dauerhaft werfender Tick heisst: Funktionen und Chaser laufen
        nicht weiter. Die Show steht, ohne dass etwas dunkel wird."""
        om = OutputManager()
        om.add_universe(1)

        def kaputt(_dt):
            raise RuntimeError("Chaser gestolpert")

        om.add_tick_callback(kaputt)
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        probleme = om.sende_probleme()
        self.assertEqual(["Tick"], [p["weg"] for p in probleme])
        self.assertIn("kaputt", probleme[0]["text"],
                      "der Name des schuldigen Callbacks gehoert in die Meldung")

    def test_ein_gesunder_tick_verdeckt_den_kranken_nicht(self):
        """★ Regression auf einen Fehler in genau diesem Fix.

        Erste Fassung buchte Erfolg und Fehler JE CALLBACK. Alle Ticks teilen
        sich aber einen Zaehler — der gesunde setzte die Serie des kranken bei
        jedem Frame wieder auf 0, der Zaehler pendelte zwischen 0 und 1 und
        erreichte die Meldeschwelle nie. Der Fehler blieb also genauso
        unsichtbar wie vorher, nur mit mehr Code.
        """
        om = OutputManager()
        om.add_universe(1)
        om.add_tick_callback(lambda _dt: None)              # gesund
        om.add_tick_callback(lambda _dt: 1 / 0)             # krank
        om.add_tick_callback(lambda _dt: None)              # gesund
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        self.assertEqual(["Tick"], [p["weg"] for p in om.sende_probleme()])

    def test_ein_frame_ist_genau_ein_fehler(self):
        """★ Von der Mutationsmessung erzwungen: eine Fassung, die den Fehler
        ZUSAETZLICH je Callback bucht, kam ohne diesen Test durch. Die Zahl
        landet als „N Fehler in Folge" im Tooltip — zaehlt sie doppelt, ist die
        Anzeige falsch, und bei zwei kranken Ticks waere sie dreifach falsch.
        """
        om = OutputManager()
        om.add_universe(1)
        om.add_tick_callback(lambda _dt: 1 / 0)
        om.add_tick_callback(lambda _dt: 1 / 0)
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        self.assertEqual(SENDE_FEHLER_SCHWELLE,
                         om.sende_statistik()[("Tick", 0)]["gesamt"],
                         "zwei kranke Ticks in einem Frame bleiben EIN Fehler")

    def test_scheiternder_channel_modifier_wird_gemeldet(self):
        """Faellt der Modifier-Pass aus, gehen INVERSE und Range-Lock verloren:
        das Licht bleibt an, sieht aber falsch aus — von einer schlecht
        programmierten Szene ohne Meldung nicht zu unterscheiden."""
        om = OutputManager()
        om.add_universe(1)
        with mock.patch("src.core.engine.channel_modifier.get_modifier_manager",
                        side_effect=RuntimeError("Modifier kaputt")):
            with redirect_stderr(io.StringIO()):
                _frames(om, SENDE_FEHLER_SCHWELLE)
        self.assertEqual(["Modifier"], [p["weg"] for p in om.sende_probleme()])


class GeraetZustandTest(unittest.TestCase):
    """★ Der eigentliche OUT-51-Befund: `is_connected()` (SERIAL-01) war seit
    Monaten dokumentiert und hatte KEINEN einzigen Konsumenten in der UI."""

    def test_lebender_prozess_mit_totem_port_ist_TOT(self):
        """Der Fall, der gruen angezeigt wurde: der Worker-Prozess laeuft
        (``is_open`` True), aber der Port ist zu — es geht kein DMX raus."""
        dev = types.SimpleNamespace(
            is_open=lambda: True, is_connected=lambda: False,
            is_disabled=lambda: True, status=lambda: 2)
        self.assertEqual(ZUSTAND_TOT, geraet_zustand(dev))
        self.assertIs(False, geraet_verbunden(dev))

    def test_sendender_adapter(self):
        dev = types.SimpleNamespace(
            is_open=lambda: True, is_connected=lambda: True,
            is_disabled=lambda: False, status=lambda: 1)
        self.assertEqual(ZUSTAND_SENDET, geraet_zustand(dev))
        self.assertIs(True, geraet_verbunden(dev))

    def test_anlaufphase_ist_weder_gut_noch_schlecht(self):
        """Ohne diesen Zustand faerbte die Statusleiste nach jedem „Verbinden"
        erst einmal rot — eine Warnung fuer einen Vorgang, der normal laeuft."""
        from src.core.dmx.serial_process import ST_CONNECTING
        dev = types.SimpleNamespace(
            is_open=lambda: True, is_connected=lambda: False,
            is_disabled=lambda: False, status=lambda: ST_CONNECTING)
        self.assertEqual(ZUSTAND_VERBINDET, geraet_zustand(dev))
        self.assertIsNone(geraet_verbunden(dev))

    def test_geraet_ohne_auskunft_ist_UNBEKANNT_nicht_kaputt(self):
        """Ein Art-Net-Socket KANN nicht wissen, ob jemand zuhoert (UDP).
        Daraus „tot" zu machen waere eine neue Luege in die Gegenrichtung."""
        self.assertEqual(ZUSTAND_UNBEKANNT, geraet_zustand(object()))
        self.assertIsNone(geraet_verbunden(object()))

    def test_werfende_auskunft_stuerzt_nicht_ab(self):
        def bumm():
            raise RuntimeError("Shared Memory weg")
        self.assertEqual(ZUSTAND_UNBEKANNT,
                         geraet_zustand(types.SimpleNamespace(is_connected=bumm)))


class AusgabeStatusTest(unittest.TestCase):

    def test_listet_jeden_weg_mit_universum_und_ziel(self):
        om = OutputManager()
        om.add_universe(1)
        om.add_universe(2)
        om._enttec_outputs[1] = types.SimpleNamespace(
            port="/dev/ttyUSB0", is_connected=lambda: True)
        om._sacn_outputs[2] = types.SimpleNamespace(_target_ip="10.0.0.5")
        status = om.ausgabe_status()
        self.assertEqual([(1, "Enttec"), (2, "sACN")],
                         [(s["universum"], s["weg"]) for s in status])
        self.assertEqual("/dev/ttyUSB0", status[0]["ziel"])
        self.assertIs(True, status[0]["verbunden"])
        self.assertIsNone(status[1]["verbunden"], "UDP kann das nicht wissen")

    def test_jeder_sendertyp_nennt_sein_ziel_anders(self):
        """Enttec `port`, Art-Net `target_ip`, sACN `_target_ip` — wer nur zwei
        davon liest, zeigt beim dritten stumm ein leeres Ziel an."""
        om = OutputManager()
        for u in (1, 2, 3):
            om.add_universe(u)
        om._enttec_outputs[1] = types.SimpleNamespace(port="/dev/ttyUSB0")
        om._artnet_outputs[2] = types.SimpleNamespace(target_ip="10.0.0.9")
        om._sacn_outputs[3] = types.SimpleNamespace(_target_ip="10.0.0.5")
        self.assertEqual(["/dev/ttyUSB0", "10.0.0.9", "10.0.0.5"],
                         [s["ziel"] for s in om.ausgabe_status()])

    def test_laufende_fehlerserie_schlaegt_die_selbstauskunft(self):
        """★ Ein UDP-Socket meldet sich nie als kaputt. Wenn aber 20 ``sendto``
        hintereinander geworfen haben, geht nichts raus — dann ist die Antwort
        „weiss nicht" falsch."""
        om = _manager_mit("sACN", _KaputterAdapter())
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        eintrag = om.ausgabe_status()[0]
        self.assertIs(False, eintrag["verbunden"])
        self.assertIn("Network is unreachable", eintrag["problem"])


class ZaehlerUeberlebenAdapterNichtTest(unittest.TestCase):
    """Ohne Aufraeumen meldete die Anzeige ewig einen Ausfall fuer einen
    Adapter, den es nicht mehr gibt — und ein neuer erbte die Fehlerserie
    seines Vorgaengers, waere also „kaputt", ohne je gesendet zu haben."""

    def test_remove_output_vergisst_die_fehler(self):
        om = _manager_mit("Enttec", _KaputterAdapter())
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        self.assertTrue(om.sende_probleme())
        om.remove_output(1)
        self.assertEqual([], om.sende_probleme())

    def test_neuer_adapter_startet_bei_null(self):
        om = _manager_mit("Enttec", _KaputterAdapter())
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        om.remove_output(1)
        om._enttec_outputs[1] = _KaputterAdapter(fehler=None)   # gesundes Geraet
        _frames(om, 1)
        self.assertEqual([], om.sende_probleme())

    def test_tick_fehler_ueberleben_einen_adapter_wechsel(self):
        """Tick-Callbacks haengen an keinem Adapter — ``remove_output`` darf
        ihre Serie deshalb NICHT loeschen (Schluessel-Universum 0)."""
        om = OutputManager()
        om.add_universe(1)
        om.add_tick_callback(lambda _dt: 1 / 0)
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        om.remove_output(0)
        om.remove_output(1)
        self.assertEqual(["Tick"], [p["weg"] for p in om.sende_probleme()])


class SacnReichtFehlerDurchTest(unittest.TestCase):
    """``sacn.py`` schluckte ``OSError`` selbst — LightOS sendete 44 Mal pro
    Sekunde ins Leere und meldete nichts."""

    def test_sendto_fehler_kommt_beim_manager_an(self):
        from src.core.dmx.sacn import SACNSender
        sender = SACNSender.__new__(SACNSender)      # ohne echten Socket
        sender._target_ip = "10.0.0.5"
        sender._source_name = "LightOS"
        sender._universes = set()
        from src.core.dmx.sacn_source import sacn_source
        sender._source = sacn_source()
        sender._cid = sender._source.cid
        sender._token = sender._source.new_token()

        class _ToterSocket:
            def sendto(self, *_):
                raise OSError("Network is unreachable")

        sender._sock = _ToterSocket()
        with self.assertRaises(OSError):
            sender.send_dmx(1, bytes(512))


class OutputThreadStirbtNichtTest(unittest.TestCase):
    """Die Eigenschaft, die beim Sichtbarmachen nicht verloren gehen darf:
    eine Exception aus einem Geraet beendet den Output-Thread NIE — sonst waere
    aus einem stillen Ausfall EINES Ausgangs ein lauter Ausfall ALLER."""

    def test_ein_kaputter_ausgang_stoppt_die_anderen_nicht(self):
        gesund = _KaputterAdapter(fehler=None)
        om = OutputManager()
        om.add_universe(1)
        om.add_universe(2)
        om._enttec_outputs[1] = _KaputterAdapter()
        om._enttec_outputs[2] = gesund
        with redirect_stderr(io.StringIO()):
            _frames(om, 30)
        self.assertEqual(30, gesund.versuche,
                         "das gesunde Geraet muss jedes Frame bekommen haben")


class _Label:
    """Minimal-Ersatz fuer das QLabel im Statusbalken (wie in test_hw5b)."""

    def __init__(self):
        self.text, self.style, self.tip = "", "", ""

    def setText(self, t):
        self.text = t

    def setStyleSheet(self, s):
        self.style = s

    def setToolTip(self, t):
        self.tip = t


def _statusbalken(offene, om=None):
    """``_check_hardware`` gegen einen Stub fahren -> (Enttec-Label, Ausgabe-Label)."""
    from src.ui import main_window as mw
    lbl, lbl_univ = _Label(), _Label()
    stub = types.SimpleNamespace(_lbl_enttec=lbl, _lbl_universe=lbl_univ)
    stub._update_ausgabe_label = types.MethodType(
        mw.MainWindow._update_ausgabe_label, stub)
    stub._PORTSUCHE_ALLE_S = mw.MainWindow._PORTSUCHE_ALLE_S
    stub._enttec_port_gesucht = types.MethodType(
        mw.MainWindow._enttec_port_gesucht, stub)
    manager = om if om is not None else types.SimpleNamespace(
        _enttec_outputs=offene)
    stub._state = types.SimpleNamespace(output_manager=manager,
                                        enttec_port_notes={})
    with mock.patch.object(mw, "find_enttec_port", lambda: "/dev/ttyUSB0"):
        mw.MainWindow._check_hardware(stub)
    return lbl, lbl_univ


class StatusbalkenSagtDieWahrheitTest(unittest.TestCase):
    """★ Der Befund aus dem Item: „``main_window.py`` faerbt gruen, sobald ein
    Adapter REGISTRIERT ist — nicht, wenn er sendet." Diese Anzeige hat bei der
    Fehlersuche am 2026-08-05 aktiv in die Irre gefuehrt."""

    def test_registrierter_aber_toter_adapter_ist_NICHT_gruen(self):
        tot = types.SimpleNamespace(
            port="/dev/ttyUSB0", is_open=lambda: True,
            is_connected=lambda: False, is_disabled=lambda: True)
        lbl, _ = _statusbalken({3: tot})
        self.assertNotIn("9DFF52", lbl.style,
                         "ein Adapter, der nicht sendet, darf nicht gruen sein")
        self.assertIn("sendet NICHT", lbl.text)
        self.assertIn("3", lbl.text, "welches Universum betroffen ist, gehoert hin")

    def test_sendender_adapter_bleibt_gruen(self):
        gut = types.SimpleNamespace(
            port="/dev/ttyUSB0", is_open=lambda: True,
            is_connected=lambda: True, is_disabled=lambda: False)
        lbl, _ = _statusbalken({3: gut})
        self.assertIn("9DFF52", lbl.style)
        self.assertIn("aktiv", lbl.text)

    def test_anlaufphase_warnt_statt_zu_alarmieren(self):
        from src.core.dmx.serial_process import ST_CONNECTING
        neu = types.SimpleNamespace(
            port="/dev/ttyUSB0", is_open=lambda: True,
            is_connected=lambda: False, is_disabled=lambda: False,
            status=lambda: ST_CONNECTING)
        lbl, _ = _statusbalken({3: neu})
        self.assertIn("verbindet", lbl.text)
        self.assertNotIn("9DFF52", lbl.style)

    def test_geraet_ohne_auskunft_wird_nicht_als_stoerung_gezeigt(self):
        """``unbekannt`` ist kein Befund — gelb blinken ohne Anlass macht die
        naechste echte Warnung wertlos."""
        lbl, _ = _statusbalken({3: types.SimpleNamespace(port="/dev/ttyUSB0")})
        self.assertIn("aktiv", lbl.text)
        self.assertIn("9DFF52", lbl.style)


class AusgabeLabelTest(unittest.TestCase):
    """``_lbl_universe`` stand fest auf „Universe 1" und wurde NIE aktualisiert
    — zwei Vorkommen im ganzen Baum, das zweite war seine Erzeugung."""

    def test_zeigt_die_tatsaechlich_sendenden_universen(self):
        om = OutputManager()
        om.add_universe(1)
        om.add_universe(2)
        om._enttec_outputs[1] = types.SimpleNamespace(
            port="/dev/ttyUSB0", is_connected=lambda: True)
        om._artnet_outputs[2] = types.SimpleNamespace(target_ip="10.0.0.9")
        _, lbl = _statusbalken({}, om=om)
        self.assertIn("U1 Enttec", lbl.text)
        self.assertIn("U2 Art-Net", lbl.text)
        self.assertNotIn("⚠", lbl.text)

    def test_ohne_jeden_ausgang_behauptet_es_keine_ausgabe_mehr(self):
        om = OutputManager()
        _, lbl = _statusbalken({}, om=om)
        self.assertNotIn("Universe 1", lbl.text,
                         "das war die alte, immer gleiche Behauptung")
        self.assertIn("—", lbl.text)

    def test_ausfall_schlaegt_die_aufzaehlung(self):
        om = _manager_mit("Art-Net", _KaputterAdapter())
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        _, lbl = _statusbalken({}, om=om)
        self.assertIn("⚠", lbl.text)
        self.assertIn("ff4444", lbl.style)
        self.assertIn("sendet nicht", lbl.tip)

    def test_der_kaputte_ausgang_bleibt_sichtbar_wenn_gekuerzt_wird(self):
        """★ Aus der Selbstpruefung: der Text zeigt nur drei Ausgaenge. Wer
        stumpf die ersten drei nimmt, blendet bei einem groesseren Rig
        ausgerechnet den ausgefallenen aus — mit Warnfarbe und einem Text, in
        dem nur funktionierende Universen stehen."""
        om = OutputManager()
        for u in (1, 2, 3, 4, 5):
            om.add_universe(u)
            om._artnet_outputs[u] = _KaputterAdapter(fehler=None)
        om._artnet_outputs[5] = _KaputterAdapter()      # nur der letzte kaputt
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        _, lbl = _statusbalken({}, om=om)
        self.assertIn("U5", lbl.text, f"der kaputte fehlt: {lbl.text!r}")
        self.assertIn("+2", lbl.text, "die Kuerzung soll erhalten bleiben")

    def test_portsuche_wird_im_sekundentakt_gedrosselt(self):
        """★ Zweiter Fund der Selbstpruefung: `find_enttec_port()` zaehlt die
        seriellen Ports des Systems auf. Ohne Drossel liefe das bei einem Rig
        ohne Enttec alle 2 s im UI-Thread."""
        from src.ui import main_window as mw
        stub = types.SimpleNamespace(
            _PORTSUCHE_ALLE_S=mw.MainWindow._PORTSUCHE_ALLE_S)
        stub._enttec_port_gesucht = types.MethodType(
            mw.MainWindow._enttec_port_gesucht, stub)
        rufe = []
        with mock.patch.object(mw, "find_enttec_port",
                               lambda: rufe.append(1) or "/dev/ttyUSB0"):
            for _ in range(10):
                self.assertEqual("/dev/ttyUSB0", stub._enttec_port_gesucht())
        self.assertEqual(1, len(rufe),
                         "zehn Takte duerfen nicht zehn Portsuchen ausloesen")

    def test_tick_stoerung_erscheint_obwohl_sie_an_keinem_ausgang_haengt(self):
        """Tick- und Modifier-Fehler haben kein Universum — ohne den eigenen
        Zweig fielen sie aus der Anzeige heraus."""
        om = _manager_mit("Enttec", _KaputterAdapter(fehler=None))
        om.add_tick_callback(lambda _dt: 1 / 0)
        with redirect_stderr(io.StringIO()):
            _frames(om, SENDE_FEHLER_SCHWELLE)
        _, lbl = _statusbalken({}, om=om)
        self.assertIn("⚠", lbl.text)
        self.assertIn("Tick", lbl.tip)


class VerbindenMeldetKeinenUngeprueftenErfolgTest(unittest.TestCase):
    """„Verbinden" meldete Erfolg, obwohl der Port tot sein kann: `add_enttec`
    startet nur den Worker — mehr weiss dieser Moment nicht."""

    def _dialog_stub(self, dev):
        from src.ui.widgets import output_config as oc
        stub = types.SimpleNamespace(
            _lbl_enttec_status=_Label(), _enttec_pruef_univ=3,
            _enttec_pruef_versuche=0,
            _MAX_PRUEF_VERSUCHE=oc.OutputConfigDialog._MAX_PRUEF_VERSUCHE,
            nochmal=0)

        def spaeter(*_a, **_k):
            stub.nochmal += 1

        stub._enttec_status_pruefen_spaeter = spaeter
        stub._enttec_status_nachtragen = types.MethodType(
            oc.OutputConfigDialog._enttec_status_nachtragen, stub)
        om = types.SimpleNamespace(_enttec_outputs={3: dev} if dev else {})
        return stub, mock.patch.object(
            oc, "get_state", lambda: types.SimpleNamespace(output_manager=om))

    def test_toter_port_meldet_kein_verbunden(self):
        dev = types.SimpleNamespace(port="/dev/ttyUSB0", is_open=lambda: True,
                                    is_connected=lambda: False,
                                    is_disabled=lambda: True)
        stub, patch = self._dialog_stub(dev)
        with patch:
            stub._enttec_status_nachtragen()
        self.assertNotIn("Verbunden", stub._lbl_enttec_status.text)
        self.assertIn("kein DMX", stub._lbl_enttec_status.text)

    def test_offener_port_meldet_verbunden(self):
        dev = types.SimpleNamespace(port="/dev/ttyUSB0", is_open=lambda: True,
                                    is_connected=lambda: True,
                                    is_disabled=lambda: False)
        stub, patch = self._dialog_stub(dev)
        with patch:
            stub._enttec_status_nachtragen()
        self.assertIn("Verbunden", stub._lbl_enttec_status.text)

    def test_waehrend_des_verbindens_wird_nachgefragt_statt_geurteilt(self):
        from src.core.dmx.serial_process import ST_CONNECTING
        dev = types.SimpleNamespace(port="/dev/ttyUSB0", is_open=lambda: True,
                                    is_connected=lambda: False,
                                    is_disabled=lambda: False,
                                    status=lambda: ST_CONNECTING)
        stub, patch = self._dialog_stub(dev)
        with patch:
            stub._enttec_status_nachtragen()
        self.assertEqual(1, stub.nochmal, "es haette nachfragen muessen")
        self.assertEqual("", stub._lbl_enttec_status.text,
                         "mitten im Verbinden ist JEDE Endaussage falsch")

    def test_nach_der_anlaufzeit_wird_nicht_ewig_weitergefragt(self):
        from src.core.dmx.serial_process import ST_CONNECTING
        dev = types.SimpleNamespace(port="/dev/ttyUSB0", is_open=lambda: True,
                                    is_connected=lambda: False,
                                    is_disabled=lambda: False,
                                    status=lambda: ST_CONNECTING)
        stub, patch = self._dialog_stub(dev)
        stub._enttec_pruef_versuche = stub._MAX_PRUEF_VERSUCHE - 1
        with patch:
            stub._enttec_status_nachtragen()
        self.assertEqual(0, stub.nochmal)
        self.assertIn("antwortet nicht", stub._lbl_enttec_status.text)

    def test_verschwundener_adapter_erzeugt_keine_meldung(self):
        stub, patch = self._dialog_stub(None)
        with patch:
            stub._enttec_status_nachtragen()
        self.assertEqual("", stub._lbl_enttec_status.text)


if __name__ == "__main__":
    unittest.main()
