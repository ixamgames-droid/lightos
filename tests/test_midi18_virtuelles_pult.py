"""MIDI-17/18 End-to-End: Motorpult (Mackie Control) ueber den ECHTEN MIDI-Weg.

Die anderen MIDI-17/18-Tests stellen den MIDI-Manager nur. Hier laeuft alles
ueber python-rtmidi und den ALSA-Sequencer: ein virtuelles "Pult" (eigener
ALSA-Client) schickt Pitchbend und Noten, ein echter ``MidiManager`` empfaengt
sie in seiner Dispatch-Schleife, die VCCanvas mit der Vorlage
``mackie_control`` reagiert, und was LightOS an den Motor und die LEDs schickt,
kommt am virtuellen Eingang des Pults wieder an.

Geprueft:

(a) Pitchbend Kanal 3 vom Pult -> VC-Fader 3 folgt;
(b) VC-Fader 3 aendern -> Pitchbend Kanal 3 mit passendem 14-Bit-Wert am Pult;
(c) der Motor meldet seine Fahrt zurueck -> keine Rueckkopplung, kein Zittern;
(d) Beruehrung (Note 106): waehrend beruehrt nichts an den Motor, Loslassen ->
    sofort Nachtrag;
(e) Seitenwechsel faehrt den Motor auf den Wert der neuen Seite;
(f) SELECT-/MUTE-Taste: Note vom Pult schaltet die VC-Taste, die LED-Meldung
    (Note-On mit Velocity 127/0) kommt am Pult an.

Ohne python-rtmidi oder ALSA-Sequencer (CI, Windows, macOS) ueberspringt sich
die Datei.

Schutz anderer MIDI-Programme auf dem Rechner (z. B. eine laufende LightOS-
Instanz, die alle 4 s ``open_all_inputs`` macht): Der Sendeport des Pults ist
LESBAR und waere fuer sie ein neuer Eingang — ihre Show bekaeme dann unsere
Testnoten (Note 0..31 auf Kanal 1 sind beim APC mini Pad-Tasten). Deshalb
heisst der ALSA-Client des Pult-Senders wie die eigenen LightOS-Ausgaenge
(``OWN_OUTPUT_CLIENT``): jede LightOS-Instanz ueberspringt ihn
(``is_own_port``). Nur der Manager DIESES Tests darf genau diesen einen Port
oeffnen — dafuer wird ``is_own_port`` hier fuer diesen Portnamen ausgenommen.
Der Empfangsport des Pults ist nur beschreibbar, taucht also bei niemandem als
Eingang auf. Geoeffnet werden ausschliesslich die zwei Ports mit der
Lauf-Kennung; fremde Ports fasst der Test nicht an.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                            # noqa: E402

rtmidi = pytest.importorskip("rtmidi", reason="python-rtmidi fehlt")

if not sys.platform.startswith("linux"):
    pytest.skip("virtuelle MIDI-Ports nur mit ALSA (Linux) im Test",
                allow_module_level=True)
if not os.path.exists("/dev/snd/seq"):
    pytest.skip("kein ALSA-Sequencer (/dev/snd/seq fehlt)", allow_module_level=True)

from PySide6.QtWidgets import QApplication              # noqa: E402

import src.core.midi.midi_manager as mgr                # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402

_app = QApplication.instance() or QApplication([])

if not mgr.RTMIDI_OK:
    pytest.skip("MidiManager ohne python-rtmidi-Backend", allow_module_level=True)


def _pb14(v255: int) -> int:
    """VC-Wert 0..255 -> 14-Bit-Motorwert, wie ``VCSlider._motor_folgen``."""
    return int(round(v255 / 255.0 * 16383))


def _pumpen(sekunden: float) -> None:
    """Qt-Ereignisse fuer ``sekunden`` verarbeiten (Timer, MIDI-Signale)."""
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        _app.processEvents()
        time.sleep(0.002)


def _warte(bedingung, timeout: float = 1.5) -> bool:
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        _app.processEvents()
        if bedingung():
            return True
        time.sleep(0.002)
    _app.processEvents()
    return bool(bedingung())


class _Pult:
    """Virtuelles Mackie-Pult: ein Sendeport (Fader, Tasten) und ein
    Empfangsport (Motor, LEDs) im ALSA-Sequencer."""

    def __init__(self, kennung: str):
        self.kennung = kennung
        self.sende_port = f"LightOS-Test-XTouch-{kennung} OUT"
        self.empfang_port = f"LightOS-Test-XTouch-{kennung} IN"
        # Clientname wie LightOS' eigene Ausgaenge: andere LightOS-Instanzen
        # oeffnen diesen lesbaren Port nicht (s. Modul-Kopf).
        self._aus = rtmidi.MidiOut(name=mgr.OWN_OUTPUT_CLIENT)
        self._aus.open_virtual_port(self.sende_port)
        self._ein = rtmidi.MidiIn(name=f"LightOS-Test-XTouch-{kennung}")
        self._ein.open_virtual_port(self.empfang_port)
        self._lock = threading.Lock()
        self._empfangen: list[list[int]] = []
        self._ein.set_callback(self._rein)

    def _rein(self, ereignis, _daten=None):
        with self._lock:
            self._empfangen.append(list(ereignis[0]))

    # ── vom Pult senden ──
    def pitchbend(self, kanal: int, w14: int) -> None:
        self._aus.send_message([0xE0 | (kanal - 1), w14 & 0x7F, (w14 >> 7) & 0x7F])

    def note(self, nummer: int, velocity: int, kanal: int = 1) -> None:
        self._aus.send_message([0x90 | (kanal - 1), nummer & 0x7F, velocity & 0x7F])

    # ── am Pult angekommen ──
    def leeren(self) -> None:
        with self._lock:
            self._empfangen.clear()

    def alles(self) -> list[list[int]]:
        with self._lock:
            return list(self._empfangen)

    def motor(self, kanal: int) -> list[int]:
        """14-Bit-Werte aller Pitchbends auf ``kanal``, in Ankunftsfolge."""
        st = 0xE0 | (kanal - 1)
        return [m[1] | (m[2] << 7) for m in self.alles()
                if len(m) == 3 and m[0] == st]

    def leds(self, note: int, kanal: int = 1) -> list[int]:
        st = 0x90 | (kanal - 1)
        return [m[2] for m in self.alles()
                if len(m) == 3 and m[0] == st and m[1] == note]

    def schliessen(self) -> None:
        for h in (self._ein, self._aus):
            try:
                h.close_port()
            except Exception:
                pass
        try:
            self._ein.cancel_callback()
        except Exception:
            pass
        del self._ein, self._aus


def _port(namen: list[str], teil: str) -> str:
    treffer = [n for n in namen if teil in n]
    assert len(treffer) == 1, f"Port '{teil}' nicht eindeutig: {treffer}"
    return treffer[0]


@pytest.fixture(scope="module")
def strecke():
    """Pult + echter MidiManager, NUR auf die zwei Ports dieses Laufs."""
    kennung = uuid.uuid4().hex[:8]
    try:
        pult = _Pult(kennung)
    except Exception as exc:                 # Sequencer da, aber nicht nutzbar
        pytest.skip(f"ALSA-Sequencer nicht nutzbar: {exc}")
    mm = mgr.MidiManager()
    alt_eigen = mgr.is_own_port
    try:
        # Ausnahme NUR fuer den Sendeport dieses Laufs (Kennung im Namen)
        mgr.is_own_port = lambda name: (
            (pult.sende_port not in str(name)) and alt_eigen(name))
        ein = _port(mm.list_inputs(), pult.sende_port)
        aus = _port(mm.list_outputs(), pult.empfang_port)
        assert mm.open_input(ein), "Pult-Sendeport nicht geoeffnet"
        assert mm.open_output(aus, allow_hint=False), "Pult-Empfangsport nicht geoeffnet"
        assert list(mm._inputs) == [ein], "nur der Pult-Port darf offen sein"
        assert mm.current_output_name() == aus
        yield pult, mm
    finally:
        mgr.is_own_port = alt_eigen
        mm.close_all()
        pult.schliessen()
        assert not mm._rx_thread.is_alive(), "MidiDispatch-Thread haengt"


@pytest.fixture()
def pult(strecke, monkeypatch):
    """Frische VCCanvas mit der Vorlage ``mackie_control`` am echten Manager."""
    pult, mm = strecke
    from src.ui.virtualconsole import controller_templates as ct
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_slider import VCSlider
    monkeypatch.setattr(VCSlider, "soft_takeover", False)
    monkeypatch.setattr(mgr, "get_midi_manager", lambda: mm)
    c = VCCanvas()
    c.vorlage_einfuegen(ct.vorlage_bauen("mackie_control"))
    # Der Motor fuhr beim Einfuegen auf 0; was gleich danach vom Pult kommt,
    # gaelte als Bericht dieser Fahrt (Echo-Fenster). Kurz abwarten.
    _pumpen(0.35)
    pult.leeren()
    yield pult, c
    c._led_timer.stop()
    c._teardown_midi()
    for s in c.findChildren(VCSlider):
        s._motor_timer.stop()
    c.deleteLater()
    destroy_all_top_level_widgets(QApplication.instance())
    _pumpen(0.02)
    pult.leeren()


def _fader(c, kanal: int, bank: int | None = None):
    from src.ui.virtualconsole.vc_slider import VCSlider
    b = c.active_bank if bank is None else bank
    return next(w for w in c.findChildren(VCSlider)
                if w.midi_ch == kanal and w.bank == b)


def _taste(c, caption: str):
    from src.ui.virtualconsole.vc_button import VCButton
    return next(w for w in c.findChildren(VCButton)
                if w.caption == caption and w.bank == c.active_bank)


# ── (a) Pult -> LightOS ──────────────────────────────────────────────────────

def test_a_pult_bewegt_vc_fader(pult):
    p, c = pult
    f3 = _fader(c, 3)
    p.pitchbend(3, 16383)
    assert _warte(lambda: f3.value == 255), f"Fader 3 steht auf {f3.value}"
    assert _fader(c, 2).value == 0
    p.pitchbend(3, 8192)
    assert _warte(lambda: f3.value == round(8192 / 16383 * 255))


# ── (b) LightOS -> Motor ─────────────────────────────────────────────────────

def test_b_vc_wert_faehrt_motor(pult):
    p, c = pult
    f3 = _fader(c, 3)
    f3.value = 200
    assert _warte(lambda: p.motor(3)), "kein Pitchbend Kanal 3 am Pult"
    assert p.motor(3) == [_pb14(200)]
    andere = [m for m in p.alles() if m[0] & 0xF0 == 0xE0 and m[0] != 0xE2]
    assert andere == [], f"Motor auf falschem Kanal: {andere}"


# ── (c) Echo der Motorfahrt ──────────────────────────────────────────────────

def test_c_motor_echo_ohne_rueckkopplung(pult):
    """Ein echtes Pult meldet seine Motorfahrt als Pitchbend zurueck (mit
    Zwischenwerten). Das darf den VC-Fader nicht zurueckziehen und keine
    neue Motor-Sendung ausloesen."""
    p, c = pult
    f3 = _fader(c, 3)
    beantwortet = 0
    gesendet_vor = 0
    f3.value = 180
    ende = time.monotonic() + 1.2
    while time.monotonic() < ende:
        _app.processEvents()
        werte = p.motor(3)
        # jede neue Motor-Sendung "faehrt" der Motor ab und meldet zurueck
        for ziel in werte[beantwortet:]:
            start = 0 if gesendet_vor is None else gesendet_vor
            for w in (start + (ziel - start) // 3, start + 2 * (ziel - start) // 3,
                      ziel - 20, ziel):
                p.pitchbend(3, max(0, min(16383, w)))
            gesendet_vor = ziel
        beantwortet = len(werte)
        time.sleep(0.002)
    assert p.motor(3) == [_pb14(180)], f"Rueckkopplung: {p.motor(3)}"
    assert f3.value == 180, f"Echo hat den Fader verstellt: {f3.value}"


# ── (d) Beruehrung ───────────────────────────────────────────────────────────

def test_d_beruehrung_sperrt_und_loslassen_traegt_nach(pult):
    p, c = pult
    f3 = _fader(c, 3)
    p.note(106, 127)                         # Fader 3 beruehrt
    assert _warte(lambda: f3._motor._beruehrt), "Beruehrung nicht angekommen"
    f3.value = 90
    _pumpen(0.4)
    assert p.motor(3) == [], "Motor fuhr trotz Beruehrung"
    p.note(106, 0)                           # losgelassen (Mackie: Velocity 0)
    t0 = time.monotonic()
    assert _warte(lambda: p.motor(3), timeout=0.5), "kein Nachtrag nach Loslassen"
    assert time.monotonic() - t0 < 0.3, "Nachtrag kam nicht sofort"
    assert p.motor(3) == [_pb14(90)]


def test_d2_hand_waehrend_beruehrung_bewegt_fader(pult):
    """Waehrend der Beruehrung bewegt die Hand den VC-Fader; nach dem
    Loslassen steht der Motor dort, wo die Hand ihn liess."""
    p, c = pult
    f3 = _fader(c, 3)
    p.note(106, 127)
    assert _warte(lambda: f3._motor._beruehrt)
    p.pitchbend(3, 4096)
    assert _warte(lambda: f3.value == round(4096 / 16383 * 255))
    _pumpen(0.1)
    assert p.motor(3) == []
    p.note(106, 0)
    assert _warte(lambda: not f3._motor._beruehrt)
    _pumpen(0.6)
    werte = p.motor(3)
    assert len(werte) <= 1, f"Zittern nach Loslassen: {werte}"
    if werte:
        assert abs(werte[-1] - 4096) <= 64


# ── (e) Seitenwechsel ────────────────────────────────────────────────────────

def test_e_seitenwechsel_faehrt_motor(pult):
    from src.ui.virtualconsole import controller_templates as ct
    p, c = pult
    _fader(c, 3, bank=0).value = 60
    c.set_active_bank(1)
    c.vorlage_einfuegen(ct.vorlage_bauen("mackie_control"))
    _fader(c, 3, bank=1).value = 230
    assert _warte(lambda: p.motor(3) and p.motor(3)[-1] == _pb14(230))
    p.leeren()
    c.set_active_bank(0)
    assert _warte(lambda: p.motor(3)), "Motor blieb beim Wechsel auf Seite 1 stehen"
    assert p.motor(3)[-1] == _pb14(60)
    # alle Motoren der Seite fahren mit (Kanal 1..9)
    assert _warte(lambda: all(p.motor(k) for k in range(1, 10)))
    p.leeren()
    c.set_active_bank(1)
    assert _warte(lambda: p.motor(3) and p.motor(3)[-1] == _pb14(230))
    # ein Pitchbend gilt jetzt dem Fader der neuen Seite
    _pumpen(0.3)
    p.pitchbend(3, 0)
    assert _warte(lambda: _fader(c, 3, bank=1).value == 0)
    assert _fader(c, 3, bank=0).value == 60


# ── (f) Tasten mit LED ───────────────────────────────────────────────────────

def test_f_taste_schaltet_und_led_kommt_zurueck(pult):
    p, c = pult
    sel1 = _taste(c, "SELECT 1")             # Note 24
    p.note(24, 127)
    assert _warte(lambda: sel1._pressed), "SELECT 1 nicht gedrueckt"
    assert _warte(lambda: 127 in p.leds(24)), f"keine LED an: {p.alles()}"
    p.note(24, 0)
    assert _warte(lambda: not sel1._pressed)
    assert _warte(lambda: p.leds(24)[-1:] == [0]), f"LED nicht aus: {p.leds(24)}"
    assert p.leds(24).count(127) == 1, "LED-Meldung doppelt"


def test_f2_mute_taste_led(pult):
    p, c = pult
    mute2 = _taste(c, "MUTE 2")              # Note 17
    p.note(17, 127)
    assert _warte(lambda: mute2._pressed)
    assert _warte(lambda: 127 in p.leds(17))
    # andere Tasten bleiben dunkel
    assert all(v == 0 for n in range(32) if n != 17 for v in p.leds(n))
    p.note(17, 0)
    assert _warte(lambda: p.leds(17)[-1:] == [0])
