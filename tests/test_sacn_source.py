"""OUT-06 (Rest): eine E1.31-Quelle je Installation — CID, Sequenz und Besitz.

Vorher lagen alle drei im ``SACNSender``: jedes Universum war fuer den Empfaenger
eine eigene Quelle, und jeder Neustart eine neue. Die Tests messen die Aussagen
getrennt — „geteilt", „ueberlebt", „Sequenz laeuft weiter", „Abschied trifft nicht
den Nachfolger" —, weil eine Umsetzung jede einzelne erfuellen kann, ohne die
anderen. Genau daran ist der erste Entwurf gescheitert: er zog die CID hoch und
liess den Zaehler unten, was den Empfaenger schlechter stellte als vorher.
"""
from __future__ import annotations

import os
import uuid

import pytest

from src.core.dmx import sacn as sacn_mod
from src.core.dmx import sacn_source as src_mod
from src.core.dmx.sacn import SACNSender, _pack_framing


# ── Empfaenger-Nachbau (E1.31-2018 §6.7.2) ───────────────────────────────────

class _CaptureSock:
    """Fake-Socket: sammelt die Pakete, statt sie zu senden."""

    def __init__(self):
        self.sent = []

    def sendto(self, pkt, dest):
        self.sent.append(bytes(pkt))

    def setsockopt(self, *a):
        pass

    def close(self):
        pass


def _empfaenger(pakete):
    """Was ein spec-konformer Empfaenger mit dieser Paketfolge macht.

    §6.7.2: Differenz zur zuletzt gesehenen Sequenznummer derselben Quelle
    (CID **und** Universum) bilden; liegt sie in ``(-20, 0]``, gilt das Paket als
    veraltet und wird VERWORFEN. Ein Test, der nur „die CID ist gleich" prueft,
    wuerde die Regression nicht sehen — sie entsteht erst aus dem Zusammenspiel.
    """
    letzte, akzeptiert, verworfen = {}, 0, 0
    for pkt in pakete:
        key = (pkt[22:38], int.from_bytes(pkt[113:115], "big"))
        seq = pkt[111]
        if key not in letzte:
            letzte[key] = seq
            akzeptiert += 1
            continue
        diff = ((seq - letzte[key] + 128) % 256) - 128
        if -20 < diff <= 0:
            verworfen += 1
        else:
            letzte[key] = seq
            akzeptiert += 1
    return akzeptiert, verworfen


@pytest.fixture
def cid_datei(tmp_path, monkeypatch):
    """Frischer CID-Ort je Test + garantiert leerer Prozess-Cache davor UND danach.

    Ohne das Aufraeumen am Ende truege der naechste Test die CID dieses Tests im
    Cache — er wuerde gruen, ohne je die Datei anzufassen.
    """
    pfad = tmp_path / "sacn_cid"
    monkeypatch.setenv("LIGHTOS_SACN_CID", str(pfad))
    src_mod.reset_for_tests()
    yield pfad
    src_mod.reset_for_tests()


# ── Form ─────────────────────────────────────────────────────────────────────

def test_cid_ist_16_byte(cid_datei):
    assert len(src_mod.sacn_cid()) == 16


def test_datei_enthaelt_die_uuid_als_text(cid_datei):
    """Lesbarer UUID-Text, nicht 16 rohe Bytes — eine Identitaet, die man im
    Supportfall vorlesen koennen muss."""
    roh = src_mod.sacn_cid()
    assert cid_datei.exists()
    text = cid_datei.read_text(encoding="utf-8").strip()
    assert uuid.UUID(text).bytes == roh


def test_env_override_bestimmt_den_ort(cid_datei):
    src_mod.sacn_cid()
    assert cid_datei.exists()
    assert src_mod.cid_file_path() == str(cid_datei)


def test_ohne_override_liegt_sie_im_app_datenordner(monkeypatch):
    """Der Default-Ort ist der App-Datenordner — ohne Env-Variable geprueft, aber
    OHNE zu schreiben (sonst faende der Test in Davids echtem Ordner statt)."""
    from src.core import paths
    monkeypatch.delenv("LIGHTOS_SACN_CID", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/wegwerf/xdg")
    assert src_mod.cid_file_path() == os.path.join(
        "/wegwerf/xdg", "LightOS", "sacn_cid")


# ── Die zwei Kernaussagen ────────────────────────────────────────────────────

def test_zwei_sender_teilen_die_cid(cid_datei):
    """E1.31: die CID identifiziert die KOMPONENTE, nicht den Stream.

    Rot, sobald die CID wieder pro Sender-Instanz entsteht — genau der Fehler,
    durch den drei sACN-Universen als drei Konsolen erschienen.
    """
    a = SACNSender(target_ip="127.0.0.1")
    b = SACNSender(target_ip="127.0.0.1")
    try:
        assert a._cid == b._cid
    finally:
        a.close()
        b.close()


def test_alle_universen_teilen_die_cid_im_echten_pfad(cid_datei):
    """Nicht ``SACNSender`` direkt, sondern die Verdrahtung, die im Betrieb laeuft.

    ``OutputManager`` legt JE UNIVERSUM einen eigenen Sender an — genau daraus kam
    der zweite, im Item nicht notierte Teil des Fehlers: vier sACN-Universen waren
    fuer den Empfaenger vier verschiedene Konsolen. Der Neuaufbau am Ende
    entspricht einem „Speichern" im Universen-Tab (``apply_output_config`` baut
    alle sACN-Sender neu) — auch dort darf die Identitaet nicht wechseln.
    """
    from src.core.dmx.output_manager import OutputManager

    om = OutputManager()
    try:
        for universe in (1, 2, 3, 7):
            om.add_sacn(universe, None)
        cids = {s._cid for s in om._sacn_outputs.values()}
        assert len(om._sacn_outputs) == 4
        assert len(cids) == 1

        om.add_sacn(2, "127.0.0.1")            # Adapter-Wechsel im Betrieb
        assert om._sacn_outputs[2]._cid == om._sacn_outputs[1]._cid
    finally:
        for sender in list(om._sacn_outputs.values()):
            sender.close()


def test_cid_ueberlebt_den_neustart(cid_datei):
    """Rot, sobald die CID nur im Speicher lebt (der Prozess-Cache wuerde jede
    zweite Messung beantworten — deshalb wird er hier ausdruecklich geleert)."""
    erste = src_mod.sacn_cid()
    src_mod.reset_for_tests()          # = Anwendung neu gestartet
    assert src_mod.sacn_cid() == erste


def test_neustart_liest_wirklich_die_datei(cid_datei):
    """Gegenprobe zum vorigen Test: eine von aussen gesetzte CID wird uebernommen.

    „Gleich nach reset" allein bewiese nur, dass irgendetwas gemerkt wurde — nicht,
    dass die DATEI die Quelle ist.
    """
    fremd = uuid.uuid4()
    cid_datei.write_text(str(fremd), encoding="utf-8")
    assert src_mod.sacn_cid() == fremd.bytes


def test_cid_steht_im_paket(cid_datei):
    """Die CID im Root-Layer (Offset 22..38) ist die persistente — sonst waere die
    ganze Persistenz folgenlos."""
    sender = SACNSender(target_ip="127.0.0.1")
    try:
        paket = _pack_framing(bytes(512), 1, 0, "LightOS", sender._cid)
        assert paket[22:38] == src_mod.sacn_cid()
    finally:
        sender.close()


# ── Fehlerfaelle: nie den Ausgang kosten ─────────────────────────────────────

@pytest.mark.parametrize("inhalt", ["", "   \n", "kein-uuid", "42",
                                    "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"])
def test_kaputte_datei_wird_ersetzt(cid_datei, inhalt):
    """Muell in der Datei -> neue gueltige CID, Datei repariert, danach stabil."""
    cid_datei.write_text(inhalt, encoding="utf-8")
    neu = src_mod.sacn_cid()
    assert len(neu) == 16
    assert uuid.UUID(cid_datei.read_text(encoding="utf-8").strip()).bytes == neu
    src_mod.reset_for_tests()
    assert src_mod.sacn_cid() == neu          # ab jetzt stabil


def test_nicht_schreibbarer_ort_liefert_trotzdem_eine_cid(tmp_path, monkeypatch):
    """Read-Only-Ort / fehlende Rechte: sACN sendet weiter, nur die
    Wiedererkennung ueber Neustarts fehlt. Ein fehlgeschlagenes Speichern darf
    keinen Live-Ausgang kosten.

    Der Ort ist unbeschreibbar, weil sein Elternteil eine DATEI ist — das haengt
    nicht an Datei-Rechten und gilt damit auch fuer einen Lauf als root.
    """
    sperre = tmp_path / "eine_datei"
    sperre.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LIGHTOS_SACN_CID", str(sperre / "sacn_cid"))
    src_mod.reset_for_tests()
    try:
        cid = src_mod.sacn_cid()
        assert len(cid) == 16
        assert src_mod.sacn_cid() == cid       # innerhalb der Sitzung stabil
        sender = SACNSender(target_ip="127.0.0.1")
        try:
            sender.send_dmx(1, bytes(512))     # darf nicht werfen
            assert sender._cid == cid
        finally:
            sender.close()
    finally:
        src_mod.reset_for_tests()


# ── Sequenz und Besitz: was die geteilte CID erst korrekt macht ──────────────

@pytest.fixture
def fake_sockets(monkeypatch):
    """Alle Sender bekommen einen mitschneidenden Fake-Socket (kein Netz noetig)."""
    socks = []

    def fabrik(*a, **k):
        s = _CaptureSock()
        socks.append(s)
        return s

    monkeypatch.setattr(sacn_mod.socket, "socket", fabrik)
    return socks


@pytest.mark.parametrize("frames_vorher", [3, 15, 19])
def test_sender_tausch_verliert_kein_frame(cid_datei, fake_sockets, frames_vorher):
    """DER Test dieser Runde.

    Beim Sender-Tausch — jedes „Speichern" im Universen-Tab — bleiben CID und
    Universum gleich. Faenge die Sequenz dabei wieder bei 0 an, verwuerfe ein
    Empfaenger bis zu 20 Frames (455 ms stehendes Licht). Gemessen mit dem
    ersten Entwurf: 15 von 45 Paketen weg. Die Parameter decken den Bereich ab,
    in dem der Rueckwaerts-Sprung-Algorithmus greift.
    """
    alt = SACNSender(target_ip="10.0.0.5")
    for _ in range(frames_vorher):
        alt.send_dmx(5, bytes(512))
    neu = SACNSender(target_ip="10.0.0.5")          # Tausch
    for _ in range(30):
        neu.send_dmx(5, bytes(512))

    pakete = fake_sockets[0].sent + fake_sockets[1].sent
    akzeptiert, verworfen = _empfaenger(pakete)
    assert verworfen == 0
    assert akzeptiert == len(pakete)


def test_abschied_des_alten_toetet_den_neuen_stream_nicht(cid_datei, fake_sockets):
    """`_swap_device` traegt den neuen Sender ein und schliesst den alten DANACH.

    Sendet der neue in diesem Fenster schon (der 44-Hz-Thread laeuft weiter), dann
    darf der Abschied des Alten keine Stream-Termination fuer dieses Universum
    mehr schicken — sie traefe unter derselben CID die Quelle, die der Neue gerade
    etabliert hat (§6.2.6: „shall enter network data loss condition").
    """
    alt = SACNSender(target_ip="10.0.0.5")
    alt.send_dmx(5, bytes(512))
    neu = SACNSender(target_ip="10.0.0.5")
    neu.send_dmx(5, bytes(512))                     # Nachfolger sendet bereits
    alt.close()

    terminierungen = [p for p in fake_sockets[0].sent if p[112] == 0x40]
    assert terminierungen == []

    # Gegenprobe: der Nachfolger selbst terminiert sein Universum sehr wohl.
    neu.close()
    assert [p for p in fake_sockets[1].sent if p[112] == 0x40]


def test_letzter_sender_terminiert_weiterhin(cid_datei, fake_sockets):
    """Der Besitz-Riegel darf die Stream-Termination nicht generell abwuergen —
    sonst waere OUT-06 Teil 1 (2026-07-12) still zurueckgenommen."""
    sender = SACNSender(target_ip="10.0.0.5")
    sender.send_dmx(1, bytes(512))
    sender.send_dmx(7, bytes(512))
    sender.close()

    term = [p for p in fake_sockets[0].sent if p[112] == 0x40]
    assert len(term) == 6                            # 2 Universen x 3 Pakete
    assert {int.from_bytes(p[113:115], "big") for p in term} == {1, 7}


def test_sequenz_laeuft_nach_der_termination_weiter(cid_datei, fake_sockets):
    """Nach einem vollstaendigen Abschied kommt spaeter wieder ein Sender fuer
    dasselbe Universum (Adapter aus und wieder an). Auch er darf nicht bei 0
    anfangen — fuer den Empfaenger ist es dieselbe Quelle."""
    erster = SACNSender(target_ip="10.0.0.5")
    for _ in range(10):
        erster.send_dmx(3, bytes(512))
    erster.close()

    zweiter = SACNSender(target_ip="10.0.0.5")
    zweiter.send_dmx(3, bytes(512))
    zweiter.close()

    letztes_daten_paket = [p for p in fake_sockets[1].sent if p[112] == 0x00][0]
    assert letztes_daten_paket[111] == 11            # 10 Daten + 1 Termination


def test_universen_haben_getrennte_zaehler(cid_datei, fake_sockets):
    """Der Zaehler ist je (Quelle, Universum) — nicht einer fuer alles."""
    sender = SACNSender(target_ip="10.0.0.5")
    for _ in range(5):
        sender.send_dmx(1, bytes(512))
    sender.send_dmx(2, bytes(512))
    sender.close()

    u2 = [p for p in fake_sockets[0].sent
          if int.from_bytes(p[113:115], "big") == 2 and p[112] == 0x00]
    assert u2[0][111] == 0


def test_kein_tmp_muell_neben_der_cid(cid_datei):
    """Atomar geschrieben heisst: keine liegengebliebene .tmp-Datei."""
    src_mod.sacn_cid()
    reste = [p.name for p in cid_datei.parent.iterdir() if p.name != "sacn_cid"]
    assert reste == []
