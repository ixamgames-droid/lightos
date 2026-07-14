"""VIZ-MASTER-FEEDBACK — WYSIWYG-Anzeige-Snapshot (POST Grand-Master/Blackout).

Prueft die Logik hinter ``OutputManager.get_display_frame``: der Snapshot haelt
GENAU die gesendeten Bytes (nach Grand-Master/Blackout), waehrend der rohe
Universe-Puffer die Pre-Master-Werte behaelt. Konsumenten (DMX-Monitor,
Output-Monitor, 3D-Visualizer) fallen ohne Snapshot sauber auf den Rohpuffer
zurueck. Headless — keine echten Ausgabe-Geraete noetig; ``_send_all`` laeuft
mit leerer Geraeteliste (send-Loop no-op).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.output_manager import OutputManager


def _om_with_universe(num: int = 1):
    om = OutputManager()
    u = om.add_universe(num)
    return om, u


def test_blackout_snapshot_all_zero_buffer_keeps_pre_master():
    om, u = _om_with_universe(1)
    u.set_channel(1, 200)
    u.set_channel(5, 255)
    om.set_blackout(True)
    om._send_all()

    frame = om.get_display_frame(1)
    assert frame is not None
    assert len(frame) == 512
    # Snapshot zeigt Blackout: alles 0.
    assert all(b == 0 for b in frame)
    # Rohpuffer bleibt unberuehrt (Pre-Master).
    assert u.get_channel(1) == 200
    assert u.get_channel(5) == 255


def test_grand_master_scales_snapshot_not_buffer():
    om, u = _om_with_universe(1)
    u.set_channel(1, 200)
    # Ohne Adressmaske -> globales Dimmen (rohes Universum).
    om.set_grand_master(0.5)
    om._send_all()

    frame = om.get_display_frame(1)
    assert frame is not None
    assert frame[0] == 100          # 200 * 0.5 (POST-Master)
    assert u.get_channel(1) == 200  # Puffer haelt Pre-Master-Wert


def test_gm_address_mask_only_scales_masked_addresses():
    om, u = _om_with_universe(1)
    u.set_channel(1, 200)   # Intensitaet/Farbe -> in der Maske
    u.set_channel(2, 200)   # Pan/Tilt -> NICHT in der Maske
    om.set_gm_address_mask({1: frozenset({1})})
    om.set_grand_master(0.5)
    om._send_all()

    frame = om.get_display_frame(1)
    assert frame is not None
    assert frame[0] == 100   # maskierte Adresse skaliert
    assert frame[1] == 200   # unmaskierte Adresse unberuehrt
    # Puffer bleibt in beiden Faellen Pre-Master.
    assert u.get_channel(1) == 200
    assert u.get_channel(2) == 200


def test_full_grand_master_snapshot_equals_sent_buffer():
    om, u = _om_with_universe(1)
    u.set_channel(1, 123)
    u.set_channel(2, 45)
    # GM = 1.0, kein Blackout -> Snapshot == gesendete (rohe) Bytes.
    om._send_all()

    frame = om.get_display_frame(1)
    assert frame is not None
    assert frame[0] == 123
    assert frame[1] == 45


def test_no_snapshot_before_first_send_returns_none():
    om, u = _om_with_universe(1)
    u.set_channel(1, 77)
    # Noch kein _send_all() -> kein Snapshot vorhanden.
    assert om.get_display_frame(1) is None
    assert om.get_display_frame(99) is None


def test_consumer_fallback_to_raw_buffer_without_snapshot():
    # Repliziert die Konsumenten-Fallback-Logik (DMX-/Output-Monitor):
    # ohne Snapshot wird der Rohpuffer angezeigt.
    om, u = _om_with_universe(1)
    u.set_channel(1, 123)

    data = om.get_display_frame(1)
    if data is None:
        data = u.get_all()
    assert data[0] == 123


def test_display_snapshot_returns_independent_copy():
    om, u = _om_with_universe(1)
    u.set_channel(1, 10)
    om._send_all()
    snap = om.display_snapshot()
    assert snap[1][0] == 10
    # Kopie: Aendern des zurueckgegebenen dicts beruehrt den internen Snapshot nicht.
    snap.clear()
    assert om.get_display_frame(1) is not None


def test_blackout_then_release_updates_snapshot():
    om, u = _om_with_universe(1)
    u.set_channel(1, 200)
    om.set_blackout(True)
    om._send_all()
    assert om.get_display_frame(1)[0] == 0

    # Blackout aufheben -> naechster Frame zeigt wieder den echten Output.
    om.set_blackout(False)
    om._send_all()
    assert om.get_display_frame(1)[0] == 200
