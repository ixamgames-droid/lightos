"""Show file manager - saves/loads .lshow ZIP archives."""
from __future__ import annotations
import contextlib
import json
import zipfile
import os
import tempfile

from src.core.strict import strict_mode
from src.core.stage.coords import normalize_rotation

SHOW_VERSION = "1.2"

# Fremdformat-Gate (s. load_show): Top-Level-Bloecke, an denen eine show.json als
# LightOS-Show erkennbar ist. Bewusst ein KLEINER, stabiler Kern aus dem
# save_show-Schema (nicht die vollstaendige Liste) — jede von save_show
# geschriebene Datei enthaelt mehrere davon, waehrend ein Fremdformat keinen
# einzigen hat. Erweitern ist harmlos, Weglassen ebenfalls (nur die Erkennung
# wird grober) -> kein Wartungszwang bei jedem neuen additiven Block.
_KNOWN_SHOW_BLOCKS = frozenset({
    "patch", "programmer", "base_levels", "functions", "virtual_console",
    "cue_stacks", "executors", "palettes", "curves", "visualizer", "live_view",
    "scene_graph", "library", "snapshots", "fixture_groups", "channel_groups",
    "efx", "rgb_matrix", "efx_paths", "tempo_buses", "laser_figures",
})
# Nur fuer die Fehlermeldung: Marker, die auf einen bekannten Fremd-Entwurf
# zeigen (der nie implementierte 1.0-Entwurf mit patch.json/sequences/-Eintraegen).
_FOREIGN_MARKERS = frozenset({"format_version", "universes", "software_version"})


def _replace_scene(state, scene) -> None:
    """Review-Fix (state._scene-Ersetzung desynct lebende Views): einzige
    Stelle in show_file.py, die ``state._scene`` durch ein NEUES SceneGraph-
    Objekt ersetzt. Nutzt ``state.set_scene()`` (haengt lebende Registry-Views
    auf den neuen Graphen um + resynct), falls vorhanden -- echter AppState
    UND tests/test_show_file.py::_SceneAwareFakeState (die den echten
    Adapter-Vertrag nachbildet) haben das. Fake-States ohne Adapter (z. B.
    ``_FakeState`` ohne ``_scene``) erreichen diese Funktion gar nicht erst
    (Aufrufer prueft ``hasattr(state, "_scene")`` vorher). Fallback auf
    direkte Zuweisung nur fuer den unwahrscheinlichen Fall eines State-Objekts
    mit ``_scene``, aber ohne ``set_scene``-Methode."""
    set_scene = getattr(state, "set_scene", None)
    if callable(set_scene):
        set_scene(scene)
    else:
        state._scene = scene


def _prune_ghost_placeholder_nodes(scene) -> None:
    """Review-Fix (Geister-Platzhalter-Nodes): entfernt Platzhalter-Stage-
    Nodes, die ``_DockView._ensure_parent_node`` (scene_adapters.py) bei
    einem Dock auf eine (damals) unbekannte Stage-Element-ID angelegt hat --
    minimale ``SceneNode(id=sid, kind=PLATFORM)`` OHNE Geometrie-Facette
    (``size_m``/``color``/``name`` alle ``None``) UND ohne fixture_id. Ein
    solcher Node ist nur dann ein reiner Ueberrest (kein echtes Buehnen-
    Element), wenn er zusaetzlich KEINE Kinder (mehr) hat -- ein noch
    gedocktes Fixture haengt daran und darf nicht mitgerissen werden (der
    Stale-Dock-Filter vor diesem Aufruf reparent'et solche Faelle bereits auf
    ``None``, keep_world=True, s. Aufrufer)."""
    from src.core.stage.scene_graph import NodeKind

    ghost_ids = [
        n.id for n in scene._nodes.values()
        if n.kind == NodeKind.PLATFORM
        and n.fixture_id is None
        and n.size_m is None
        and n.color is None
        and n.name is None
        and not scene.children_of(n.id)
    ]
    for nid in ghost_ids:
        scene.remove(nid)


# ★ QA-50: Was der tolerante Loader unterwegs verworfen hat.
#
# Der Toleranz-Default ist richtig — eine Show mit einem kaputten Block soll
# sich oeffnen lassen, statt gar nicht. Falsch war nur, dass davon **nichts
# uebrig blieb**: `load_show` meldete „geladen", und das naechste Speichern
# schrieb den unvollstaendigen Stand zurueck. Der Verlust entstand also nicht
# beim Laden, sondern beim nachfolgenden Speichern — und war bis dahin fuer
# niemanden sichtbar.
#
# Modul-global statt Rueckgabewert: `_lenient` wird an 31 Stellen gerufen,
# quer durch den Loader. Ein durchgereichter Sammler haette jede davon
# angefasst; hier reicht ein Ort. `load_show` leert die Liste am Anfang.
_ladeprobleme: list[str] = []


#: STAB-24 (c): Was ``save_show`` beim Einsammeln NICHT in die Datei bekam.
#: Die Speichern-Aktion der Oberflaeche haengt es an ihre Lueckenliste
#: („Unvollstaendig gespeichert") — derselbe Dialog, kein zweiter Kanal.
_speicherprobleme: list[str] = []


def letzte_speicherprobleme() -> list[str]:
    """Die beim letzten :func:`save_show` ausgelassenen Eintraege (STAB-24)."""
    return list(_speicherprobleme)


def _eintrags_hinweis(eintrag, *felder) -> str:
    """Namenszusatz fuer die Meldung ueber einen uebersprungenen Eintrag:
    ``"'Truss-Bars' "`` bzw. ``""``. Der Nutzer soll WIEDERERKENNEN, was fehlt —
    eine Positionsnummer allein sagt ihm nichts ueber sein Rig."""
    if isinstance(eintrag, dict):
        for feld in felder:
            wert = eintrag.get(feld)
            if isinstance(wert, (str, int, float)) and not isinstance(wert, bool) \
                    and str(wert):
                return f"'{wert}' "
    return ""


def _liste_im_block(data: dict, schluessel: str, was: str) -> list:
    """Einen Listen-Block der show.json lesen (STAB-24/25).

    Fehlt der Schluessel: ``[]`` ohne Meldung (Alt-/Teil-Show). Ist er DA, aber
    keine Liste — auch ``null`` —, wird das gemeldet und ``[]`` geliefert.
    Frueher machte ``data.get(...) or []`` einen ``null``-Block stumm zu
    ``[]``: gemessen 4 Gruppen in der Datei -> 0 geladen, keine Meldung."""
    if schluessel not in data:
        return []
    wert = data.get(schluessel)
    if isinstance(wert, list):
        return wert
    _lenient(f"{was}-Block übersprungen",
             TypeError(f"'{schluessel}' ist {type(wert).__name__}, erwartet Liste"))
    return []


def _kegel_fid(wert) -> int:
    """Ein ``beams_off``-Eintrag: Geraete-Nummer als Zahl (auch als Text "3"),
    nie ``None``/Wahrheitswert."""
    if wert is None or isinstance(wert, bool):
        raise TypeError(f"keine Geräte-Nummer: {wert!r}")
    return _als_ganzzahl(wert, "fid", 0, -_SQLITE_INT_MAX, _SQLITE_INT_MAX)


def _je_eintrag(eintraege, bauen, was: str, *namensfelder) -> list:
    """Jeden Eintrag EINZELN uebersetzen (STAB-24): ein kaputter kostet nur
    sich selbst und wird mit Nummer UND Namen ueber ``_lenient`` gemeldet.
    Vorher lagen ganze Bloecke in EINEM try — ein Punkt ``"x": "links"``
    kostete gemessen 0 von 4 Laser-Figuren."""
    out = []
    for nr, e in enumerate(eintraege, start=1):
        try:
            out.append(bauen(e))
        except Exception as ex:
            _lenient(f"{was} {nr} {_eintrags_hinweis(e, *namensfelder)}übersprungen", ex)
    return out


#: Groesste Ganzzahl, die SQLite binden kann. Groessere ueberstanden die
#: Uebersetzung je Eintrag und scheiterten erst beim COMMIT — dann kosteten sie
#: wieder ALLE Eintraege (Review STAB-24: ``cols = 10**20`` -> 0 von 4 Gruppen).
_SQLITE_INT_MAX = 2 ** 63 - 1


def _als_ganzzahl(wert, feld: str, default: int, lo: int = 0,
                  hi: int = _SQLITE_INT_MAX) -> int:
    """Ganzzahlfeld eines Show-Eintrags: fehlt -> Default; sonst ``int()`` und
    Bereichspruefung — ausserhalb wirft es und kostet nur SEINEN Eintrag."""
    if wert is None:
        return default
    zahl = int(wert)
    if not lo <= zahl <= hi:
        raise ValueError(f"'{feld}' = {zahl} liegt ausserhalb {lo}..{hi}")
    return zahl


def _raster_mass(g: dict, feld: str) -> int:
    """``cols``/``rows`` einer Gruppe. Ausserhalb 1..4096 wird BEGRENZT und
    gemeldet statt verworfen — Name und Belegung der Gruppe bleiben erhalten.
    (cols 0/-1 liessen den Gruppen-Editor haengen; 10**20 scheiterte erst beim
    COMMIT und kostete dann alle Gruppen.)"""
    zahl = int(g.get(feld, 8) if g.get(feld) is not None else 8)
    begrenzt = min(4096, max(1, zahl))
    if begrenzt != zahl:
        _ladeprobleme.append(
            f"Fixture-Gruppe {_eintrags_hinweis(g, 'name')}: '{feld}' = {zahl} "
            f"auf {begrenzt} begrenzt")
    return begrenzt


def _als_text(wert, feld: str, default: str) -> str:
    """Textfeld eines Show-Eintrags (STAB-24 a): Zahlen/Wahrheitswerte als Text
    durchlassen — wie ``_patched_fixture_from_data`` —, ``None`` -> Default.
    Nur Liste/Objekt sind wirklich unlesbar: die bindet SQLite nicht und
    risse sonst erst beim COMMIT alle uebrigen Eintraege mit."""
    if wert is None:
        return default
    if isinstance(wert, (list, dict, set, tuple)):
        raise TypeError(f"'{feld}' ist kein Text, sondern {type(wert).__name__}")
    return str(wert)


def letzte_ladeprobleme() -> list[str]:
    """Die beim letzten :func:`load_show` verworfenen Teile (QA-50).

    Leere Liste = alles gelesen. Die UI haengt ihre Warnung daran; wer nur
    ``(ok, msg)`` auswertet, bekommt die Kurzfassung schon im Text.
    """
    return list(_ladeprobleme)


def _lenient(msg: str, exc: Exception) -> None:
    """Strukturelle Schluck-Punkte im Lade-Pfad: druckt wie bisher und laesst den
    Loader weitermachen (toleranter Default) — AUSSER im Strict-Modus
    (LIGHTOS_STRICT), dann re-raised es den Fehler laut an der exakten Stelle.
    Phase 6, siehe src/core/strict.py + SecondBrain entry_show_validation.

    QA-50: merkt sich den Vorfall zusaetzlich in ``_ladeprobleme``."""
    print(f"[show_file] {msg}: {exc}")
    _ladeprobleme.append(f"{msg}: {exc}")
    if strict_mode():
        raise exc


def _to_offset(value) -> float:
    """Einmess-Versatz (VIZ-55) — dieselbe Normalisierung wie ``update_fixture``."""
    from src.core.stage.einmessen import normiere_versatz
    return normiere_versatz(value)


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


# FM-HEADLAYOUT: gueltige Mehrkopf-Programmiermodi. Unbekanntes/fehlendes ->
# "auto" (Bestandsverhalten) -> Alt-Shows OHNE den Key laden unveraendert.
# Kanonische Quelle ist das abhaengigkeitsfreie Leaf-Modul core.head_mode, damit
# Show-Persistenz, Live-Schreibpfad (update_fixture) und Undo nicht driften —
# und der Import auch dann traegt, wenn Tests `database.models` ausstubben.
from src.core.pixel_order import (              # noqa: E402  (Leaf-Import)
    normalize_element_rotation as _to_rotation,
    normalize_pixel_order as _to_pixel_order,
)
from src.core.head_mode import (                # noqa: E402  (Leaf-Import)
    HEAD_MODES, normalize_head_mode as _to_head_mode,
)


def _fixture_to_dict(pf) -> dict:
    """Normalize patched fixture object/dict to persistent JSON schema."""
    if isinstance(pf, dict):
        return {
            "fid": _to_int(pf.get("fid", pf.get("id", 0)), 0),
            # Symmetrie zum Loader (s. u.): der leere Label wird schon beim
            # Dump auf denselben Platzhalter kanonisiert, den der Loader
            # ohnehin einsetzt. Sonst aendert der ERSTE save->load->save eine
            # Show-Datei still ('' -> 'Fixture 7') = Diff-Rauschen in Git.
            "label": str(pf.get("label", pf.get("name", "")) or f"Fixture {_to_int(pf.get('fid', pf.get('id', 0)), 0)}"),
            "fixture_profile_id": _to_int(
                pf.get("fixture_profile_id", pf.get("profile_id", 0)), 0
            ),
            "mode_name": str(pf.get("mode_name", pf.get("mode", "")) or ""),
            # STAB-10: symmetrisch zu _patched_fixture_from_data klemmen, sonst
            # driftet ein Fixture mit address/channel_count>512 beim Save->Load->Save
            # (Dump klemmte frueher nur nach unten, Load auf [1,512]).
            "universe": max(1, _to_int(pf.get("universe", 1), 1)),
            "address": min(512, max(1, _to_int(pf.get("address", 1), 1))),
            "channel_count": min(512, max(1, _to_int(pf.get("channel_count", 1), 1))),
            "invert_pan": bool(pf.get("invert_pan", False)),
            "invert_tilt": bool(pf.get("invert_tilt", False)),
            "swap_pan_tilt": bool(pf.get("swap_pan_tilt", False)),
            "dimmer_curve": str(pf.get("dimmer_curve", "linear") or "linear"),
            "spider_mirrored": bool(pf.get("spider_mirrored", True)),
            "spider_dual_tilt": bool(pf.get("spider_dual_tilt", False)),
            "head_mode": _to_head_mode(pf.get("head_mode", "auto")),
            "pixel_order": _to_pixel_order(pf.get("pixel_order", "rowwise")),
            "element_rotation": _to_rotation(pf.get("element_rotation", 0)),
            "element_flip": bool(pf.get("element_flip", False)),
            "pan_range_deg": _to_int(pf.get("pan_range_deg", 540), 540),
            "tilt_range_deg": _to_int(pf.get("tilt_range_deg", 270), 270),
            "pan_zero_dmx": _to_int(pf.get("pan_zero_dmx", 128), 128),
            "tilt_zero_dmx": _to_int(pf.get("tilt_zero_dmx", 128), 128),
            "aim_offset_pan": _to_offset(pf.get("aim_offset_pan", 0.0)),
            "aim_offset_tilt": _to_offset(pf.get("aim_offset_tilt", 0.0)),
            "manufacturer_name": str(pf.get("manufacturer_name", "") or ""),
            "fixture_name": str(pf.get("fixture_name", "") or ""),
            "fixture_type": str(pf.get("fixture_type", "other") or "other"),
            "protocol": str(pf.get("protocol", "dmx") or "dmx"),
            "net_host": str(pf.get("net_host", "") or ""),
        }
    return {
        "fid": _to_int(getattr(pf, "fid", getattr(pf, "id", 0)), 0),
        # Gleiche Kanonisierung wie im dict-Zweig oben — sonst ist der
        # Save-Pfad asymmetrisch zum Loader.
        "label": str(getattr(pf, "label", getattr(pf, "name", ""))
                     or f"Fixture {_to_int(getattr(pf, 'fid', getattr(pf, 'id', 0)), 0)}"),
        "fixture_profile_id": _to_int(
            getattr(pf, "fixture_profile_id", getattr(pf, "profile_id", 0)), 0
        ),
        "mode_name": str(getattr(pf, "mode_name", getattr(pf, "mode", "")) or ""),
        # STAB-10: symmetrisch zu _patched_fixture_from_data klemmen (s. dict-Zweig).
        "universe": max(1, _to_int(getattr(pf, "universe", 1), 1)),
        "address": min(512, max(1, _to_int(getattr(pf, "address", 1), 1))),
        "channel_count": min(512, max(1, _to_int(getattr(pf, "channel_count", 1), 1))),
        "invert_pan": bool(getattr(pf, "invert_pan", False)),
        "invert_tilt": bool(getattr(pf, "invert_tilt", False)),
        "swap_pan_tilt": bool(getattr(pf, "swap_pan_tilt", False)),
        "dimmer_curve": str(getattr(pf, "dimmer_curve", "linear") or "linear"),
        "spider_mirrored": bool(getattr(pf, "spider_mirrored", True)),
        "spider_dual_tilt": bool(getattr(pf, "spider_dual_tilt", False)),
        "head_mode": _to_head_mode(getattr(pf, "head_mode", "auto")),
        "pixel_order": _to_pixel_order(getattr(pf, "pixel_order", "rowwise")),
        "element_rotation": _to_rotation(getattr(pf, "element_rotation", 0)),
        "element_flip": bool(getattr(pf, "element_flip", False)),
        "pan_range_deg": _to_int(getattr(pf, "pan_range_deg", 540), 540),
        "tilt_range_deg": _to_int(getattr(pf, "tilt_range_deg", 270), 270),
        "pan_zero_dmx": _to_int(getattr(pf, "pan_zero_dmx", 128), 128),
        "tilt_zero_dmx": _to_int(getattr(pf, "tilt_zero_dmx", 128), 128),
        "aim_offset_pan": _to_offset(getattr(pf, "aim_offset_pan", 0.0)),
        "aim_offset_tilt": _to_offset(getattr(pf, "aim_offset_tilt", 0.0)),
        "manufacturer_name": str(getattr(pf, "manufacturer_name", "") or ""),
        "fixture_name": str(getattr(pf, "fixture_name", "") or ""),
        "fixture_type": str(getattr(pf, "fixture_type", "other") or "other"),
        "protocol": str(getattr(pf, "protocol", "dmx") or "dmx"),
        "net_host": str(getattr(pf, "net_host", "") or ""),
    }


def _patched_fixture_from_data(d: dict, fallback_fid: int):
    """Create PatchedFixture from current or legacy show format."""
    from src.core.database.models import PatchedFixture

    fid = _to_int(d.get("fid", d.get("id", fallback_fid)), fallback_fid)
    label = str(d.get("label", d.get("name", f"Fixture {fid}")) or f"Fixture {fid}")
    fixture_profile_id = _to_int(
        d.get("fixture_profile_id", d.get("profile_id", 0)), 0
    )
    mode_name = str(d.get("mode_name", d.get("mode", "")) or "")
    universe = max(1, _to_int(d.get("universe", 1), 1))
    address = min(512, max(1, _to_int(d.get("address", 1), 1)))
    channel_count = min(512, max(1, _to_int(d.get("channel_count", 1), 1)))
    fixture_profile_id = _resolve_fixture_profile_id(
        fixture_profile_id,
        str(d.get("manufacturer_name", "") or ""),
        str(d.get("fixture_name", "") or ""),
        # Kanalzahl nur, wenn die Show sie traegt (sonst klemmt sie oben auf 1).
        mode_name=mode_name, channel_count=channel_count if "channel_count" in d else 0,
    )
    return PatchedFixture(
        fid=fid,
        label=label,
        fixture_profile_id=fixture_profile_id,
        mode_name=mode_name,
        universe=universe,
        address=address,
        channel_count=channel_count,
        invert_pan=bool(d.get("invert_pan", False)),
        invert_tilt=bool(d.get("invert_tilt", False)),
        swap_pan_tilt=bool(d.get("swap_pan_tilt", False)),
        dimmer_curve=str(d.get("dimmer_curve", "linear") or "linear"),
        spider_mirrored=bool(d.get("spider_mirrored", True)),
        spider_dual_tilt=bool(d.get("spider_dual_tilt", False)),
        head_mode=_to_head_mode(d.get("head_mode", "auto")),
        pixel_order=_to_pixel_order(d.get("pixel_order", "rowwise")),
        element_rotation=_to_rotation(d.get("element_rotation", 0)),
        element_flip=bool(d.get("element_flip", False)),
        pan_range_deg=_to_int(d.get("pan_range_deg", 540), 540),
        tilt_range_deg=_to_int(d.get("tilt_range_deg", 270), 270),
        pan_zero_dmx=_to_int(d.get("pan_zero_dmx", 128), 128),
        tilt_zero_dmx=_to_int(d.get("tilt_zero_dmx", 128), 128),
        aim_offset_pan=_to_offset(d.get("aim_offset_pan", 0.0)),
        aim_offset_tilt=_to_offset(d.get("aim_offset_tilt", 0.0)),
        manufacturer_name=str(d.get("manufacturer_name", "") or ""),
        fixture_name=str(d.get("fixture_name", "") or ""),
        fixture_type=str(d.get("fixture_type", "other") or "other"),
        # LAS-04: Alt-Shows ohne Feld laden als klassisches DMX-Geraet.
        protocol=str(d.get("protocol", "dmx") or "dmx"),
        net_host=str(d.get("net_host", "") or ""),
    )


def _resolve_fixture_profile_id(profile_id: int, manufacturer_name: str,
                                fixture_name: str, *, mode_name: str = "",
                                channel_count: int = 0) -> int:
    """Stabile Show-Referenz ueber Rechner/Fixture-DBs hinweg.

    SQLite-Auto-IDs sind keine portablen Fixture-IDs: eine frisch aufgebaute DB
    kann dieselben eingebauten Profile in anderer Reihenfolge enthalten. Moderne
    Shows speichern deshalb Hersteller und Modell mit. Passt die numerische ID
    dort auf ein anderes Profil, wird sie anhand dieser Namen aufgeloest.
    Legacy-Shows ohne Namen behalten unveraendert ihre alte ID.

    ★ **FM-43: die drei Ausgaenge sind verschieden schlimm — und zwei waren
    stumm.** Gemessen am 02.09.2026:

    * **Treffer** — die ID passt oder der Name loest auf. Unveraendert.
    * **Kein Treffer, die ID zeigt ins Leere** -> das Geraet loest **null
      Kanaele** auf. Die Show laedt „erfolgreich", der Patch sieht normal aus
      (Hersteller/Modell stehen denormalisiert IN der Show-Datei), und am Rig
      bleibt es dunkel. Gemessen: 6 von 6 Geraeten, ohne eine einzige Meldung.
    * **Kein Treffer, die ID zeigt auf ein ANDERES Profil** -> es faehrt
      **still das falsche Geraet**. Gemessen lief ein 11-Kanal-Eintrag als
      4-Kanal-PAR. Das ist der gefaehrlichste Ausgang und war bis hierher
      nicht von einem Treffer zu unterscheiden.

    Alle drei melden jetzt in ``_ladeprobleme`` (QA-50) — denselben Sammler,
    den die UI beim Oeffnen ohnehin als Warnung zeigt. Bewusst KEIN neuer
    Meldeweg: der Fall gehoert in denselben Dialog wie ein nicht lesbarer
    Show-Block, und ein zweiter Kanal waere ein zweiter, der uebersehen wird.

    ★★ **Und die Mehrdeutigkeit wird nicht mehr von der Einfuegereihenfolge
    entschieden.** Bisher gewann ``order_by(FixtureProfile.id).first()`` —
    also **immer der aeltere Import** statt des gepflegten Builtins. In der
    gewachsenen Bibliothek gibt es diese Kollision bereits dreimal, und bei
    einer unterscheidet sich sogar der ``fixture_type`` (``led_bar`` gegen
    ``matrix``): anderes 3D-Modell, anderer Renderpfad. Jetzt gewinnt
    ``source='builtin'``.

    Warum das die richtige Wahl ist und keine Geschmacksfrage: dieser Zweig
    wird ueberhaupt nur erreicht, wenn die gespeicherte ID **nicht** passt —
    wir raten hier also bereits. Von zwei Rateoptionen ist die eingebaute die
    bessere, weil sie auf **jedem** Rechner existiert und gepflegt ist; ein
    lokaler Import existiert womoeglich nur hier. Wer bewusst das importierte
    Profil wollte, hat dessen ID in der Show — und die kommt oben durch, ohne
    diesen Zweig zu beruehren.

    ★★ **FM-63: beim Namens-Rueckfall entscheidet zuerst der MODUS.** Seit ein
    LightOS-Profil einen gleichnamigen QLC+-Import abloesen kann, stehen beide
    nebeneinander — mit womoeglich ANDEREN Modi. Gewinnt blind das mitgelieferte
    Profil, nimmt ``app_state._resolve_mode`` dort irgendeinen Modus: falsche
    Kanalbelegung, still. Deshalb (``mode_name``/``channel_count`` aus der Show):
    1. ein Treffer mit Modusname UND passender Kanalzahl, 2. einer mit
    passender Kanalzahl, 3. wie bisher. Innerhalb jeder Stufe gilt die alte
    Reihenfolge (mitgeliefert vor Import, dann ID) — das LightOS-Profil gewinnt
    also nur, wenn es den Modus der Show hat, sonst der abgeloeste Import. Hat
    das gewaehlte Profil den Modus der Show nicht, steht IMMER eine Meldung in
    ``_ladeprobleme``. Keine Dubletten-Warnung gibt es nur fuer das Paar
    „LightOS-Profil + der Import, den es abloest“, wenn der Modus passt.
    Die FM-43-Regel „builtin vor Import“ gilt damit nur noch innerhalb einer
    Stufe: hat ein Import den Modus der Show und das builtin nicht, gewinnt
    der Import (die Dubletten-Meldung bleibt).
    """
    if not fixture_name:
        return profile_id
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import Session, joinedload
        from src.core.database.fixture_db import engine
        from src.core.database.models import (FixtureProfile, Manufacturer,
                                              MITGELIEFERT_QUELLEN)

        with Session(engine()) as session:
            current = session.execute(
                select(FixtureProfile)
                .options(joinedload(FixtureProfile.manufacturer))
                .where(FixtureProfile.id == profile_id)
            ).scalar_one_or_none()
            if current is not None:
                current_mfr = getattr(current.manufacturer, "name", "") or ""
                if (current.name == fixture_name and
                        (not manufacturer_name or current_mfr == manufacturer_name)):
                    return profile_id

            query = (
                select(FixtureProfile.id, FixtureProfile.source)
                .join(Manufacturer)
                .where(FixtureProfile.name == fixture_name)
            )
            if manufacturer_name:
                query = query.where(Manufacturer.name == manufacturer_name)
            # FM-43: `builtin` zuerst, dann wie bisher nach ID. Der zweite
            # Schluessel bleibt drin, damit die Wahl bei gleicher Herkunft
            # deterministisch ist — sonst entschiede die Zeilenreihenfolge.
            # FM-56: die Dateien der eigenen Bibliothek (`lightos`) sind
            # genauso mitgeliefert und zaehlen wie `builtin`.
            treffer = session.execute(
                query.order_by(FixtureProfile.source.not_in(MITGELIEFERT_QUELLEN),
                               FixtureProfile.id)
            ).all()
            _geraet = f"{manufacturer_name} / {fixture_name}".strip(" /")
            if treffer:
                from src.core.database.fixture_db import abgeloeste_profile
                from src.core.database.models import FixtureMode
                modi: dict[int, list[tuple[str, int]]] = {}
                for fid_, mname, mcount in session.execute(
                        select(FixtureMode.fixture_id, FixtureMode.name,
                               FixtureMode.channel_count)
                        .where(FixtureMode.fixture_id.in_([int(t[0]) for t in treffer]))):
                    modi.setdefault(int(fid_), []).append((mname, int(mcount or 0)))

                def _exakt(t) -> bool:
                    return any(n == mode_name and (not channel_count or c == channel_count)
                               for n, c in modi.get(int(t[0]), []))

                def _kanalzahl(t) -> bool:
                    return bool(channel_count) and any(
                        c == channel_count for _n, c in modi.get(int(t[0]), []))

                gewaehlt = treffer[0]
                if mode_name or channel_count:
                    gewaehlt = (next((t for t in treffer if mode_name and _exakt(t)), None)
                                or next((t for t in treffer if _kanalzahl(t)), None)
                                or treffer[0])
                resolved = int(gewaehlt[0])
                print(
                    f"[show_file] Fixture-Profil remapped: {profile_id} -> {resolved} "
                    f"({_geraet})"
                )
                modus_passt = not mode_name or _exakt(gewaehlt)
                if not modus_passt:
                    _ladeprobleme.append(
                        f"„{_geraet}“: Profil {profile_id} passt nicht zur Show "
                        f"(fehlt oder traegt einen anderen Namen), "
                        f"genommen wurde Profil {resolved} "
                        f"({gewaehlt[1] or 'ohne Herkunft'}) — es hat den Modus "
                        f"„{mode_name}“ ({channel_count} Kanaele) der Show NICHT. "
                        f"Kanalbelegung am Geraet pruefen.")
                # FM-63: das Paar „LightOS-Profil + der Import, den es abloest“
                # ist keine Dublette — aber nur, wenn der Modus passt.
                andere = [t for t in treffer if int(t[0]) != resolved]
                if modus_passt and andere:
                    abl = abgeloeste_profile(session)
                    paar = {i for i, ziel in abl.items() if ziel[0] == resolved}
                    if resolved in abl:
                        paar.add(abl[resolved][0])
                    andere = [t for t in andere if int(t[0]) not in paar]
                if andere:
                    # Mehrdeutig: gemeldet, nicht verschwiegen. Der Mensch sieht
                    # sonst ein Geraet, das *fast* stimmt, und sucht den Fehler
                    # ueberall — nur nicht in der Bibliothek.
                    _ladeprobleme.append(
                        f"„{_geraet}“ steht {len(andere) + 1}× in der Geraetebibliothek — "
                        f"genommen wurde Profil {resolved} "
                        f"({gewaehlt[1] or 'ohne Herkunft'}). Wenn das Geraet falsch "
                        f"aussieht, liegt es an der Dublette, nicht an der Show.")
                return resolved
            # FM-43: ab hier ist das Geraet NICHT aufloesbar. Bis 2026-09-03
            # endete die Funktion hier stumm mit der alten ID — und was diese
            # ID trifft, entscheidet, wie schlimm es wird.
            if current is None:
                _ladeprobleme.append(
                    f"„{_geraet}“ steht nicht in der Geraetebibliothek "
                    f"(Profil {profile_id}). Das Geraet bleibt DUNKEL: es hat "
                    f"keine Kanaele, die angesteuert werden koennen.")
            else:
                _fremd_mfr = getattr(current.manufacturer, "name", "") or ""
                _fremd = f"{_fremd_mfr} / {current.name}".strip(" /")
                _ladeprobleme.append(
                    f"„{_geraet}“ steht nicht in der Geraetebibliothek — "
                    f"Profil {profile_id} gehoert dort zu „{_fremd}“. "
                    f"ACHTUNG: es wird dieses ANDERE Geraet angesteuert, nicht "
                    f"das der Show. Vor dem Speichern pruefen, sonst wird der "
                    f"falsche Stand zurueckgeschrieben.")
    except Exception as exc:
        # Ein optionaler Library-DB-Fehler darf den Show-Load nicht verhindern.
        print(f"[show_file] Fixture-Profil-Aufloesung fehlgeschlagen: {exc}")
    return profile_id


@contextlib.contextmanager
def _deferred_addr_release(state):
    """CDX-22: Klammert den MEHRSTUFIGEN Patch-Tausch des Show-Loads (reset-first
    leerer Patch -> neuer Patch) in ``AppState.deferred_unpatched_release``, damit
    der Zwischenschritt mit dem LEEREN Patch nicht jede bisher gepatchte Adresse
    sofort im Live-Universe nullt (physischer Blackout-Puls bei JEDEM Live-Load,
    den ``blackout_output=False`` allein nicht verhindert — Begruendung + Semantik
    im Docstring von ``AppState.deferred_unpatched_release``).

    Aeltere AppState-APIs und Test-Fakes ohne die Methode laufen unveraendert
    weiter (dann kein Deferral) — gleiche Toleranz wie beim ``replace_patch``-
    Fallback in ``_replace_patch_from_data``."""
    defer = getattr(state, "deferred_unpatched_release", None)
    if not callable(defer):
        yield
        return
    with defer():
        yield


def _replace_patch_from_data(state, patch_data: list[dict]):
    # ★ STAB-25: der Block MUSS eine Liste sein. Vorher fiel ein Objekt/Text/
    # null im Aufrufer durch ein ``if isinstance(...)`` OHNE ``else``: gemessen
    # vier Geraete in der Datei, NULL in der DB, keine Meldung. Die Pruefung
    # sitzt HIER, der einen Stelle, die den Patch aus Show-Daten ersetzt.
    # Frueh raus, ohne den bestehenden Patch zu leeren (load_show hat per
    # reset-first ohnehin geleert, jeder andere Aufrufer behaelt lieber den alten).
    if not isinstance(patch_data, list):
        _lenient("Patch-Block übersprungen",
                 TypeError(f"'patch' ist {type(patch_data).__name__}, "
                           f"erwartet Liste"))
        return
    # BUG-01: Patch verlustfrei ersetzen und dabei ALLE State-Emits unterdrücken.
    # Jedes clear_patch()/clear_programmer()/add_fixture() würde sonst synchron
    # ein Event feuern → die Views (programmer_view._refresh_effects_list)
    # refreshen re-entrant mitten im noch inkonsistenten Patch →
    # QListWidget.clear() → AccessViolation. Die Aufrufer (load_show/reset_show)
    # machen nach dem vollständigen Aufbau EINEN gebündelten Refresh.
    _prev_suppress = getattr(state, "_suppress_emits", False)
    state._suppress_emits = True
    try:
        # Clear stale programmer values referencing old patch (in-memory).
        # CDX-22: OHNE DMX-Flush. Der Clear laeuft, waehrend der ALTE Patch noch
        # geladen ist — ein Flush schriebe hier jedes alte Fixture auf seine
        # Kanal-Defaults (Dimmer 0) und der Output-Thread sendet diesen
        # Blackout-Frame physisch, bis der neue Patch steht (genau der Puls, den
        # blackout_output=False verhindern soll). load_show flusht unmittelbar nach
        # dem Programmer-Block erneut — dann gegen den NEUEN Patch. Aeltere
        # AppState-APIs/Test-Fakes ohne das Keyword: Fallback auf den Alt-Pfad.
        try:
            try:
                state.clear_programmer(flush=False)
            except TypeError:
                state.clear_programmer()
        except Exception as e:
            print(f"[show_file] clear programmer failed: {e}")

        # Volle PatchedFixture-Liste bauen, doppelte FIDs auffangen — REASSIGN auf
        # die naechste freie fid (nie droppen), sonst Intra-Load-Datenverlust bei
        # einer Show-Datei mit fid-Kollision.
        next_fid = 1
        used_fids: set = set()
        pfs: list = []
        # STAB-27: die neue Nummer darf mit KEINER fid der Datei kollidieren —
        # auch nicht mit einer, die erst weiter unten steht. Vorher bekam bei
        # [1, 1, 2] das zweite Geraet die 2, und das echte Geraet 2 wurde
        # seinerseits umnummeriert: dessen Programmer-Werte, 3D-Position und
        # Gruppen landeten still auf dem falschen Geraet.
        datei_fids: set = set()
        for entry in patch_data:
            if isinstance(entry, dict):
                try:
                    datei_fids.add(int(entry.get("fid", entry.get("id"))))
                except (TypeError, ValueError):
                    pass
        erstes_label: dict = {}
        # STAB-25: PRO EINTRAG gekapselt. Vorher warf EIN unlesbarer Eintrag die
        # ganze Schleife, ``replace(pfs)`` wurde nie erreicht und der Patch blieb
        # LEER; ein Nicht-Objekt verschwand per stummem ``continue``.
        for nr, entry in enumerate(patch_data, start=1):
            try:
                if not isinstance(entry, dict):
                    raise TypeError(
                        f"Eintrag ist kein Objekt, sondern {type(entry).__name__}")
                pf = _patched_fixture_from_data(entry, next_fid)
                # Review STAB-24: Zahlen, die SQLite nicht bindet, scheiterten
                # erst im atomaren replace_patch — dann waren ALLE Geraete weg.
                for feld in ("fid", "universe", "address", "channel_count"):
                    _als_ganzzahl(getattr(pf, feld, 0), feld, 0,
                                  -_SQLITE_INT_MAX, _SQLITE_INT_MAX)
            except Exception as e:
                _lenient(f"Gerät {nr} {_eintrags_hinweis(entry, 'label', 'fid')}"
                         f"übersprungen", e)
                continue
            if pf.fid in used_fids:
                alt_fid = pf.fid
                pf.fid = max(used_fids | datei_fids) + 1
                # Werte, Position und Gruppen unter der alten Nummer gehoeren dem
                # ERSTEN Geraet mit dieser Nummer — das zweite beginnt leer.
                # Nicht still: sonst sieht niemand, warum es dunkel bleibt.
                _ladeprobleme.append(
                    f"Doppelte Geräte-Nummer {alt_fid} in der Show-Datei: "
                    f"„{pf.label}“ hat jetzt die Nummer {pf.fid}. Werte, 3D-Position "
                    f"und Gruppen der Nummer {alt_fid} gehören zu "
                    f"„{erstes_label.get(alt_fid, '?')}“ — das umnummerierte Gerät "
                    f"bitte prüfen.")
            used_fids.add(pf.fid)
            erstes_label.setdefault(pf.fid, pf.label)
            next_fid = max(next_fid, pf.fid + 1)
            pfs.append(pf)

        # STAB-CURSHOW: den GESAMTEN Patch ATOMAR in EINER Transaktion ersetzen
        # (DELETE-all + Bulk-Insert, GENAU EIN Commit). Kein persistierter Leer-/
        # Halbzustand mehr, in den ein Parallelprozess hinein-INSERTet — die Quelle
        # der 22-35-Nichtdeterminismus + der Adress-Ueberlapp-Zeilen. Aeltere
        # AppState-APIs (und die Test-Fakes) ohne replace_patch fallen auf den
        # früheren, nicht-atomaren clear_patch()+add_fixture()-Pfad zurueck.
        # Ein Fehler im Patch-Replace (z. B. OperationalError 'database is locked'
        # nach Ablauf von busy_timeout) darf den Show-Load NICHT bis in den Qt-Slot
        # durchschlagen — der frühere Pfad kapselte clear_patch/add_fixture einzeln
        # in try/except. Bei atomarem replace_patch rollt die Transaktion zurück,
        # der alte Patch bleibt intakt; hier nur loggen, nicht propagieren.
        replace = getattr(state, "replace_patch", None)
        try:
            if callable(replace):
                replace(pfs)
            else:
                _replace_patch_legacy(state, pfs)
        except Exception as e:
            # STAB-23: NICHT nur drucken. Dieses `except` sass INNERHALB des
            # Aufrufers, der seinerseits schon `_lenient("load patch error")`
            # gehabt haette — es schluckte den Fehler also, BEVOR die
            # Meldekette ihn sehen konnte. Folge: `load_show` gab
            # „Show 'X' geladen." zurueck, `letzte_ladeprobleme()` war leer,
            # der Warndialog in `main_window._open_show_path` blieb aus — und
            # auf der Buehne stand weiter der ALTE Patch. Wer danach speichert,
            # schreibt den alten Patch in die gerade geoeffnete Datei; die Show,
            # die er oeffnen wollte, ist auf der Platte weg.
            # 31 andere Schluckpunkte des Loaders waren angebunden, ausgerechnet
            # der Patch-Block nicht — der, der bestimmt, wo das Licht hingeht.
            # `_lenient` behaelt das gewollte Verhalten bei (loggen, weiterlaufen,
            # nicht propagieren) und meldet es zusaetzlich.
            _lenient("patch replace failed", e)
    finally:
        state._suppress_emits = _prev_suppress


def _replace_patch_legacy(state, pfs: list):
    """Fallback fuer AppState-APIs OHNE ``replace_patch`` (aeltere States/Fakes):
    der frühere, NICHT-atomare Pfad — Altpatch hart leeren (clear_patch, sonst
    remove_fixture-Schleife) + je Fixture add_fixture(). Nur Kompatibilitaets-
    Schicht; der Default ist das atomare ``state.replace_patch`` (STAB-CURSHOW).
    Erwartet, dass der Aufrufer ``_suppress_emits`` bereits gesetzt hat."""
    # Remove old fixtures first. FLD-FID: hart ueber clear_patch() leeren, damit
    # auch verwaiste DB-Zeilen (Cache/DB-Desync) verschwinden — sonst kollidieren
    # neue fids mit Altzeilen (IntegrityError: UNIQUE constraint patched_fixtures.fid).
    cleared = False
    try:
        state.clear_patch()
        cleared = True
    except AttributeError:
        cleared = False  # aeltere AppState-API ohne clear_patch
    except Exception as e:
        print(f"[show_file] clear_patch failed: {e}")
    if not cleared:
        old_fids = [getattr(f, "fid", None) for f in state.get_patched_fixtures()]
        for fid in [f for f in old_fids if f is not None]:
            try:
                state.remove_fixture(fid, undoable=False)
            except TypeError:
                state.remove_fixture(fid)
            except Exception as e:
                print(f"[show_file] remove fixture {fid} failed: {e}")
    for pf in pfs:
        try:
            state.add_fixture(pf, undoable=False)
        except TypeError:
            state.add_fixture(pf)
        except Exception as e:
            print(f"[show_file] add fixture {getattr(pf, 'fid', '?')} failed: {e}")


def _euron10_2ch_fids(state) -> set[int]:
    """CDX-18: fids der gepatchten **EURON10**-Nebelmaschinen im 2-Kanal-Modus
    (Nebel=``dimmer``, Lüfter=``fan``). Streng gegatet, damit die fan-Split-
    Kompat NUR dieses eine Builtin-Gerät trifft und NIE ein Custom-Fixture mit
    echtem, unabhängigem ``fan``-Kanal (``fan`` ist ein generisch wählbares
    Attribut): Builtin-Profil ``short_name=='EURON10'`` UND ``source=='builtin'``
    UND ``channel_count==2`` UND die tatsächliche Kanalform ist exakt
    ``[dimmer, fan]`` (``get_channels_for_patched``). Best-effort: schlägt die
    Erkennung fehl, wird nichts migriert (kein Crash, kein Load-Abbruch).

    Hinweis: der EURON10-Filter liegt in der WHERE-Klausel, d. h. die EINE
    Library-DB-Query läuft bei JEDEM gepatchten 2-Kanal-Gerät (nicht nur EURON10),
    einmal pro ``load_show`` — vernachlässigbar (Load ist kein Hot-Path)."""
    out: set[int] = set()
    try:
        fixtures = [f for f in state.get_patched_fixtures()
                    if getattr(f, "channel_count", 0) == 2]
    except Exception:
        return out
    if not fixtures:
        return out
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database.fixture_db import engine as _fdb_engine
        from src.core.database.models import FixtureProfile
        from src.core.app_state import get_channels_for_patched
        pids = {getattr(f, "fixture_profile_id", None) for f in fixtures}
        pids.discard(None)
        if not pids:
            return out
        with Session(_fdb_engine()) as s:
            euron10_pids = set(s.execute(
                select(FixtureProfile.id).where(
                    FixtureProfile.id.in_(pids),
                    FixtureProfile.short_name == "EURON10",
                    FixtureProfile.source == "builtin",
                )
            ).scalars().all())
        if not euron10_pids:
            return out
        for f in fixtures:
            if getattr(f, "fixture_profile_id", None) not in euron10_pids:
                continue
            try:
                attrs = [getattr(c, "attribute", None)
                         for c in get_channels_for_patched(f)]
                fid_i = int(getattr(f, "fid"))
            except Exception:
                # Pro-Fixture isoliert: ein defektes Fixture darf die Erkennung
                # der nachfolgenden nicht abbrechen (fid-Cast mit im try).
                continue
            if attrs == ["dimmer", "fan"]:
                out.add(fid_i)
    except Exception as e:
        print(f"[show_file] EURON10 fan detection failed: {e}")
    return out


def _fill_fan_from_dimmer(attrs, fid_key, euron10_fids: set) -> None:
    """CDX-18: Vor dem fan-Split (CDX-07) spiegelte der Nebelwert (``dimmer``)
    still auf den 2. Kanal. In einem attr-gekeyten Playback-Record eines EURON10
    fehlt daher das (neue) ``fan``-Attribut. Fehlt ``fan`` KOMPLETT, aber
    ``dimmer`` ist da, ziehe ``fan=dimmer`` EINMAL nach — NUR fuer erkannte
    EURON10-fids und NIE ueberschreibend (ein bereits vorhandenes ``fan``, auch
    0, gilt als bewusst editiert). Nimmt int- ODER str-fid-Keys an (Programmer/
    base_levels/Cue/Palette/Snap = int, Sequence/Snapshot = str)."""
    if not isinstance(attrs, dict):
        return
    try:
        fid_int = int(fid_key)
    except (TypeError, ValueError):
        return
    if fid_int not in euron10_fids:
        return
    if "dimmer" in attrs and "fan" not in attrs:
        try:
            # OverflowError mitfangen: int(float('inf')) aus einem rohen, nicht
            # vorsanitisierten Container-Wert (Cue/Palette/Sequence/Snap/Snapshot)
            # wirft OverflowError (NICHT ValueError) — analog STAB-18/A3D-19.
            attrs["fan"] = int(attrs["dimmer"])
        except (TypeError, ValueError, OverflowError):
            pass


def _collect_fixture_groups(state, probleme: list | None = None) -> list:
    """Spatial-Gruppen (FixtureGroup) aus der Show-DB fuer die .lshow sammeln.
    Frueher gingen Gruppen beim Save/Load verloren (nur in current_show.db).

    UI-69: ``probleme`` ist der Sammler fuer Ausfaelle (Default: die
    Speicher-Lueckenliste). Der Aenderungs-Vergleich reicht eine Wegwerf-Liste
    herein — er darf die Meldungen des letzten echten Speicherns nicht
    ueberschreiben."""
    if probleme is None:
        probleme = _speicherprobleme
    out: list = []
    try:
        from sqlalchemy import select
        from src.core.database.models import FixtureGroup
        with state._session() as s:
            zeilen = s.execute(select(FixtureGroup)).scalars().all()
            # STAB-24 (c): JE ZEILE. Vorher EIN try um die Schleife: eine kaputte
            # Zeile kostete sich UND ALLE FOLGENDEN (gemessen Position 1 -> 0 von
            # 4 Gruppen in der Datei), gemeldet nur per print. HIER wird der
            # Verlust festgeschrieben — also muss er hier gemeldet werden.
            for nr, g in enumerate(zeilen, start=1):
                try:
                    out.append({
                        "name": g.name, "cols": int(g.cols), "rows": int(g.rows),
                        "positions_json": g.positions_json or "{}",
                        "folder": g.folder or "",
                    })
                except Exception as e:
                    probleme.append(
                        f"Fixture-Gruppe {nr} '{getattr(g, 'name', '?')}' — FEHLT "
                        f"in der Datei ({e})")
    except Exception as e:
        probleme.append(f"Fixture-Gruppen ({e})")
    return out


def _fixture_group_aus_daten(g):
    """EINEN Gruppen-Eintrag der .lshow uebersetzen; wirft bei unlesbarem
    Eintrag (der Aufrufer ueberspringt und meldet genau diesen, STAB-24).
    Defaults wie frueher, damit Alt-Shows unveraendert laden."""
    from src.core.database.models import FixtureGroup
    if not isinstance(g, dict):
        raise TypeError(f"Eintrag ist kein Objekt, sondern {type(g).__name__}")
    return FixtureGroup(
        name=_als_text(g.get("name", "Gruppe"), "name", "Gruppe"),
        cols=_raster_mass(g, "cols"), rows=_raster_mass(g, "rows"),
        positions_json=_als_text(g.get("positions_json", "{}"),
                                 "positions_json", "{}") or "{}",
        folder=_als_text(g.get("folder", ""), "folder", ""),
    )


def _restore_fixture_groups(state, groups: list) -> None:
    """Spatial-Gruppen beim Laden in die Show-DB zurueckschreiben.

    ★ STAB-24: EIN unlesbarer Eintrag darf nicht ALLE Gruppen kosten. Vorher
    lagen Loeschen, Neuanlegen und Commit in EINEM try: ein ``cols`` als Text
    riss den Block ab, uebrig blieb die vom Reset geleerte Tabelle (gemessen
    4 Gruppen in der Datei -> 0 in der DB). Jetzt zwei Phasen: erst je Eintrag
    uebersetzen (kaputte werden namentlich gemeldet), dann EINE Transaktion."""
    if not isinstance(groups, list):
        _lenient("Fixture-Gruppen-Block übersprungen",
                 TypeError(f"'fixture_groups' ist {type(groups).__name__}, "
                           f"erwartet Liste"))
        groups = []
    gebaut = _je_eintrag(groups, _fixture_group_aus_daten, "Fixture-Gruppe", "name")
    try:
        from sqlalchemy import delete
        from src.core.database.models import FixtureGroup
        with state._session() as s:
            s.execute(delete(FixtureGroup))
            for fg in gebaut:
                s.add(fg)
            s.commit()
    except Exception as e:
        # STAB-23: ebenfalls im LADE-Pfad (`load_show` -> `_restore_fixture_groups`)
        # und ebenfalls stumm. Verlorene Gruppen sind derselbe Fall: sie fallen
        # erst beim naechsten Speichern endgueltig weg.
        _lenient("restore groups error", e)
    try:
        state.notify_groups_changed()
    except Exception:
        pass


def _show_daten(state, probleme: list) -> dict:
    """Der Inhalt von show.json fuer den aktuellen Stand (ohne Fensterlayout).

    UI-69: aus ``save_show`` herausgezogen, damit der Aenderungs-Vergleich
    (:func:`show_hat_aenderungen`) GENAU das betrachtet, was eine Speicherung
    schreiben wuerde — eine zweite, parallel gepflegte Liste der Show-Teile
    liefe frueher oder spaeter auseinander. Ohne Seiteneffekte auf den State;
    das Aufraeumen verwaister Platzhalter-Nodes bleibt in ``save_show``.
    """
    from src.core.engine.palette import get_palette_manager
    from src.core.engine.curve_library import get_curve_library
    from src.core.engine.snap_library import get_snap_library

    pm = get_palette_manager()

    patch_data = [_fixture_to_dict(pf) for pf in state.get_patched_fixtures()]
    stacks_data = [s.to_dict() for s in getattr(state, "cue_stacks", [])]
    palettes_data = pm.to_dict()
    curves_data = get_curve_library().to_dict()
    # LAS-07b: gezeichnete Laser-Muster.
    laser_figures_data = [f.to_dict() for f in getattr(state, "laser_figures", [])]
    # LAS-18b: gemerkte Werksmuster-Slots (Bank/Wert + Foto-Pfad).
    laser_patterns_data = [p.to_dict()
                           for p in getattr(state, "laser_patterns", [])]

    from src.core.engine.efx_path import get_efx_path_library
    efx_paths_data = get_efx_path_library().to_dict()

    # STAB-17: KEIN stiller Leer-Fallback. function_manager.to_dict() hat keine
    # Per-Funktion-Absicherung — wirft EINE kaputte Funktion, MUSS der Save
    # abbrechen (Exception propagiert). Sonst wuerde ein leerer functions-Block
    # gespeichert und ALLE Funktionen inkl. EFX/Matrix (die nur hier leben) gingen
    # verloren. Dank STAB-16 (serialize-before-open + atomarer Write) bleibt die
    # vorhandene .lshow bei einem solchen Abbruch unangetastet.
    fm = getattr(state, "function_manager", None)
    functions_data = fm.to_dict() if fm is not None else {"functions": []}

    # EFX- und RGB-Matrix-Instanzen sind seit dem Programmer-Umbau echte
    # Funktionen und werden im "functions"-Block gespeichert. Die separaten
    # Bloecke bleiben (leer) im Schema fuer Abwaertskompatibilitaet erhalten.
    efx_data: list = []
    rgb_data: list = []

    executors_data = {}
    pe = getattr(state, "playback_engine", None)
    if pe is not None:
        try:
            executors_data = pe.to_dict(getattr(state, "cue_stacks", []))
        except Exception as e:
            print(f"[show_file] save executors error: {e}")

    vc_data = getattr(state, "_vc_layout", {}) or {}

    visualizer_data = {
        "positions": {
            str(fid): [float(p[0]), float(p[1]), float(p[2])]
            for fid, p in (getattr(state, "visualizer_positions", {}) or {}).items()
        },
        # Multi-Achsen-Ausrichtung (rx, ry, rz) in Grad je Fixture. normalize_rotation
        # akzeptiert auch das Alt-Format (einzelner Y-Float) -> immer als Liste speichern.
        "rotations": {
            str(fid): list(normalize_rotation(rot))
            for fid, rot in (getattr(state, "visualizer_rotations", {}) or {}).items()
        },
        # Andock-Beziehungen {fid: stage_element_id}
        "docks": {
            str(fid): str(sid)
            for fid, sid in (getattr(state, "visualizer_docks", {}) or {}).items()
            if sid
        },
        "active_stage": getattr(state, "active_stage_name", "simple") or "simple",
        # VIZ-13 Schritt 3b-K-2: benannte Kamerapositionen -- additiv, View-
        # State (nicht Szenegraph). Liste roher dicts (JS liefert das Format
        # bereits fertig ueber bridge.cameraSaved), hier nur defensiv kopiert.
        "named_cameras": list(getattr(state, "visualizer_named_cameras", []) or []),
        # VIZ-15: fids mit ausgeblendetem Lichtkegel. Additiv wie named_cameras
        # (kein SHOW_VERSION-Bump) — eine alte Show ohne den Block laedt mit
        # leerer Menge und sieht damit exakt aus wie bisher. Sortiert gespeichert,
        # damit zwei Speicherungen desselben Standes byte-gleich sind (sonst
        # erzeugte die Set-Reihenfolge grundlose Diffs in der Show-Datei).
        "beams_off": sorted(
            int(f) for f in (getattr(state, "visualizer_beams_off", set()) or set())
        ),
    }

    # VIZ-11 (Schritt 5): SceneGraph-Block additiv dazuschreiben — EINE Quelle
    # (state._scene), die Legacy-Bloecke oben werden bereits aus den Adapter-
    # Views (state.visualizer_positions/_rotations/_docks) gebaut, die selbst
    # nur Sichten auf denselben Graphen sind -> kein Drift zwischen beiden
    # Bloecken moeglich. Fehlt state._scene (z. B. Fake-States in Tests ohne
    # Adapter), wird der Block einfach weggelassen (Dual-Write ist additiv,
    # kein Pflichtfeld beim Laden -- siehe load_show-Migrationsgate).
    scene = getattr(state, "_scene", None)
    scene_graph_data = scene.to_dict() if scene is not None else None

    # Live-View-2D-Positionen (eigene Persistenz, entkoppelt vom 3D-Visualizer)
    live_view_data = {
        "positions": {
            str(fid): [float(p[0]), float(p[1])]
            for fid, p in (getattr(state, "live_view_positions", {}) or {}).items()
        },
        # P4: Zoom/Grid/Snap/Weltgroesse der Live View wandern mit der Show.
        "meta": dict(getattr(state, "live_view_meta", {}) or {}),
    }

    # WP-Tempo: benannte Tempo-Buses der Show sichern (Default-Bus wird NICHT
    # gespeichert; fehlt der Block beim Laden -> [] = alt-kompatibel).
    try:
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        tempo_buses_data = get_tempo_bus_manager().to_dict()
        tempo_grandmaster_data = get_tempo_bus_manager().grandmaster_to_dict()
    except Exception:
        tempo_buses_data = []
        tempo_grandmaster_data = {}
    # STAB-16: programmer/base_levels werden von UI-/MIDI-Threads live mutiert.
    # Wuerde json.dumps direkt ueber die Live-Dicts iterieren, koennte es mitten
    # im Schreiben "dict changed size during iteration" werfen. Darum EINEN
    # konsistenten Snapshot ziehen (unter _prog_lock, wenn vorhanden — derselbe
    # Lock, den der Renderer/Setter fuer programmer haelt), inkl. der verschachtelten
    # Attribut-Dicts. base_levels teilt sich denselben Zugriffspfad.
    def _snapshot_nested(d):
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in (d or {}).items()}
    _prog_lock = getattr(state, "_prog_lock", None)
    if _prog_lock is not None:
        with _prog_lock:
            programmer_snapshot = _snapshot_nested(getattr(state, "programmer", {}))
            base_levels_snapshot = _snapshot_nested(getattr(state, "base_levels", {}))
    else:
        programmer_snapshot = _snapshot_nested(getattr(state, "programmer", {}))
        base_levels_snapshot = _snapshot_nested(getattr(state, "base_levels", {}))
    show = {
        "version": SHOW_VERSION,
        "name": getattr(state, "show_name", "Neue Show"),
        "patch": patch_data,
        "programmer": programmer_snapshot,
        "base_levels": base_levels_snapshot,
        "implicit_brightness": bool(getattr(state, "implicit_brightness", True)),
        "cue_stacks": stacks_data,
        "executors": executors_data,
        "palettes": palettes_data,
        "curves": curves_data,
        "laser_figures": laser_figures_data,
        "laser_patterns": laser_patterns_data,
        "efx_paths": efx_paths_data,
        "functions": functions_data,
        "tempo_buses": tempo_buses_data,
        "tempo_grandmaster": tempo_grandmaster_data,
        "efx": efx_data,
        "rgb_matrix": rgb_data,
        "virtual_console": vc_data,
        "visualizer": visualizer_data,
        "live_view": live_view_data,
        "snapshots": getattr(state, "_snapshots_data", None) or [],
        "channel_groups": getattr(state, "_channel_groups_data", None) or [],
        "fixture_groups": _collect_fixture_groups(state, probleme),
        "library": get_snap_library().to_dict(),
        "playlist": getattr(state, "playlist", []) or [],
        "music_autoshow": getattr(state, "music_autoshow", None)
        or {"enabled": False, "function_ids": [], "bank": 0},
    }
    if scene_graph_data is not None:
        show["scene_graph"] = scene_graph_data
    return show


def save_show(path: str | os.PathLike, layout: dict | None = None):
    """Save the current show state to a .lshow ZIP file.

    Args:
        path: target path.
        layout: optional layout state from collect_layout(main_window).
    """
    from src.core.app_state import get_state

    _speicherprobleme.clear()        # STAB-24 (c): Meldungen DIESES Speicherns
    state = get_state()
    scene = getattr(state, "_scene", None)
    if scene is not None:
        # Review-Fix (Geister-Platzhalter-Nodes): vor jedem Speichern
        # verwaiste Dock-Platzhalter (kein echtes Stage-Element, keine
        # Kinder mehr) aus dem LEBENDEN Graphen entfernen -- sonst wuerden sie
        # sich ueber wiederholte Save-Zyklen unbegrenzt in der .lshow
        # ansammeln (s. _prune_ghost_placeholder_nodes). In-place auf dem
        # echten state._scene (keine Kopie) -- konsistent mit load_show, wo
        # dieselbe Aufraeumfunktion nach dem Graph-Aufbau laeuft.
        _prune_ghost_placeholder_nodes(scene)
    show = _show_daten(state, _speicherprobleme)
    # Reihenfolge der Bloecke wie bisher: Fensterlayout VOR dem Szenegraphen.
    scene_graph_data = show.pop("scene_graph", None)
    if layout:
        show["layout"] = layout
    if scene_graph_data is not None:
        show["scene_graph"] = scene_graph_data

    path = os.fspath(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # STAB-16: ERST serialisieren (ein Serialisierungsfehler — inkl. STAB-17
    # functions.to_dict() — laesst die vorhandene Datei damit unangetastet), DANN
    # atomar schreiben: in eine Temp-Datei im SELBEN Verzeichnis und per os.replace()
    # ueber den Zielpfad ziehen. Frueher truncatete zipfile.ZipFile(path,"w") die gute
    # .lshow sofort und json.dumps lief erst danach im offenen Handle -> ein Crash /
    # voller Datentraeger / Serialisierungsfehler hinterliess eine korrupte Datei UND
    # die vorherige Show war weg. os.replace ist auf einem Dateisystem atomar (Windows:
    # MoveFileEx MOVEFILE_REPLACE_EXISTING).
    payload = json.dumps(show, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(prefix=".show-", suffix=".lshow.tmp",
                                    dir=parent or ".")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("show.json", payload)
            # VC-IMG: referenzierte VC-Button-Hintergrund-Assets (Bild/GIF) mit
            # einbetten -> die Show ist auf einem anderen PC weiter vollstaendig.
            # NUR referenzierte Keys (mark-sweep-GC verwaister Assets).
            from . import vc_assets
            _missing = []
            for _key in vc_assets.collect_keys(show):
                _data = vc_assets.bytes_for(_key)
                if _data is not None:
                    zf.writestr(vc_assets.zip_name(_key), _data)
                else:
                    _missing.append(_key)
            # VC-IMG-GC: Fehlt ein referenziertes Asset im lokalen Cache (z. B. weil
            # eine PARALLELE Session es aus dem geteilten Cache evictet hat), NICHT
            # still fallenlassen — sonst überschriebe os.replace unten die bestehende
            # .lshow, die das Asset noch eingebettet hatte, und der Button wäre
            # dauerhaft leer. Stattdessen die Bytes verlustfrei aus der vorhandenen
            # Ziel-Datei übernehmen: ein Save ist mindestens ein verlustfreier
            # Round-Trip dessen, was schon in der Datei stand.
            _recovered: set[str] = set()
            if _missing and os.path.isfile(path):
                try:
                    with zipfile.ZipFile(path, "r") as _old:
                        _old_names = set(_old.namelist())
                        for _key in _missing:
                            _entry = vc_assets.zip_name(_key)
                            if _entry in _old_names:
                                _bytes = _old.read(_entry)
                                zf.writestr(_entry, _bytes)
                                # Cache gleich wieder auffüllen -> Button zeigt sofort
                                # wieder + die nächste Speicherung findet es erneut.
                                vc_assets.store_extracted(_key, _bytes)
                                _recovered.add(_key)
                except Exception as _exc:
                    print(f"[show_file] WARN: fehlende VC-Assets nicht aus {path} "
                          f"übernehmbar: {_exc}")
            _lost = [k for k in _missing if k not in _recovered]
            if _lost:
                print(f"[show_file] WARN: {len(_lost)} referenzierte(s) VC-Hintergrund-"
                      f"Asset(s) fehlen im Cache und in der bestehenden Show-Datei — "
                      f"betroffene Buttons zeigen kein Bild: {_lost}")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    try:
        state._emit("show_saved", {"path": path})
    except Exception:
        pass


# ── UI-69: Aenderungen seit dem letzten Laden/Speichern ─────────────────────
#
# Beenden fragte bei einer aus Datei geladenen Show nie nach dem Speichern:
# das Hauptfenster hatte kein Dirty-Flag, Aenderungen landeten nur im
# Auto-Save. Geloest wird das hier ueber den SPEICHERPFAD statt ueber Ereignisse:
# gemerkt wird ein Fingerabdruck dessen, was ``save_show`` schreiben wuerde, und
# „geaendert" heisst „der Fingerabdruck weicht vom gemerkten ab".
#
# Warum nicht die vorhandenen SyncEvents oder der Undo-Stapel?
#   * FUNCTION_CHANGED feuert auch beim Starten/Stoppen einer Funktion,
#     CUE_STACK_CHANGED beim GO — reine Live-Bedienung waere ein Fehlalarm.
#   * Das VC-Layout, Snapshots und Kanal-Gruppen melden gar kein Ereignis, der
#     Undo-Stapel deckt nur einen Teil der Bearbeitungen ab — da fehlten echte
#     Aenderungen.
#   * Das Laden selbst feuert alle Ereignisse — es haette die Show sofort
#     „geaendert" gemacht.
# Der Vergleich deckt dagegen JEDEN Block der Datei ab (neue Bloecke kommen
# automatisch dazu), und wer eine Aenderung rueckgaengig macht, ist wieder
# „unveraendert".

#: Blockweise Felder, die sich durch reine LIVE-Bedienung aendern und deshalb
#: nicht als Show-Aenderung zaehlen. Gespeichert werden sie trotzdem (die Datei
#: haelt den letzten Stand fest) — nur die Frage „Speichern?" loesen sie nicht
#: aus. Abgrenzung: was der Bediener waehrend der Vorstellung anfasst
#: (Programmer, Fader, Tempo/BPM, Ansicht), ist keine Arbeit an der Show; was er
#: einrichtet (Patch, Gruppen, Cues, Funktionen, Paletten, VC-Layout, Szene),
#: ist es.
_LIVE_BLOECKE = frozenset({
    "programmer",          # Programmer-Werte: Arbeitsspeicher jedes Klicks
})
_LIVE_FELDER_FUNKTION = ("intensity", "speed")   # VC-Fader/Speed-Dial setzen sie live
#: Tempo-Bus: BPM (Tap/Beat-Erkennung, BPM-Regler) und Quelle — ``source``
#: stellt nur die Laufzeit um (jeder Tap -> "tap", Beat-Erkennung angedockt ->
#: "external", Master-Wechsel -> "manual"); einrichten laesst sie sich nirgends.
_LIVE_FELDER_TEMPO_BUS = ("bpm", "source")
#: Hierarchie-Felder eines Tempo-Bus, die ein VC-Tempo-Bedienelement beim
#: BEDIENEN umstellt (Tempo-Bus-Regler: Quelle Sound -> Sub/Faktor 1, Tap/Fix ->
#: Master; Speed-Knoten: Faktor-Gitter -> bus_multiplier). Nur fuer Busse, die
#: ein solches Element steuert — eingerichtet im Tempo-Bus-Tab zaehlen sie.
_LIVE_FELDER_TEMPO_BUS_GESTEUERT = ("role", "parent_id", "bus_multiplier")
_LIVE_FELDER_GRANDMASTER = ("bpm", "armed")      # auto_sync bleibt Einstellung
_LIVE_FELDER_EXECUTOR = ("fader_value",)         # Executor-Fader
_LIVE_FELDER_LIVE_VIEW_META = ("zoom",)          # Ansicht, wie das Fensterlayout
#: VC-Bedienelemente: Typ -> Felder, die im Run-Modus beim Bedienen mitlaufen.
#: Systematisch gegen src/ui/virtualconsole geprueft (Stand UI-69-Korrektur):
#:   VCSlider            value                    Fader ziehen / MIDI
#:   VCSpeedDial         bpm, active_factor, mult Rad, Tap, Faktor-Gitter
#:   VCXYPad             pan, tilt, area          Pad ziehen, Feld markieren, MIDI
#:   VCTempoBusController source, factor, fixed_bpm  Quelle/Tap, Faktor, Fix-Rad
#: Bewusst NICHT live: VCColor-Farbe (der Doppelklick-Waehler aendert, WAS die
#: Kachel tut, und gilt in Edit- wie Run-Modus), VCTempoBusController
#: tempo_bus_id/function_ids (koppeln Effekte um — das landet ohnehin im
#: Funktionsblock), MIDI-Learn (Einrichtung), VCMultiLiveEditor checked/hidden
#: (Einrichtung des Panels; die eingestellten WERTE speichert es gar nicht),
#: VCFrame-Seite (steht nicht in der Datei). Die uebrigen Typen (Button, Label,
#: Cueliste, Encoder, Stepper, Bus-Auswahl, Effekt-Anzeigen, BPM-/Song-Anzeige)
#: veraendern beim Bedienen nichts, was ``to_dict`` schreibt.
_LIVE_FELDER_VC = {
    "VCSlider": ("value",),
    "VCSpeedDial": ("bpm", "active_factor", "mult"),
    "VCXYPad": ("pan", "tilt", "area"),
    "VCTempoBusController": ("source", "factor", "fixed_bpm"),
}

#: Bloecke, die der 3D-Visualizer aus der Live View ABLEITET (Auto-Patch, s.
#: ``abgeleitete_aenderung_nachfuehren``).
ABGELEITETE_3D_BLOECKE = ("visualizer", "scene_graph")

#: Fingerabdruck des zuletzt geladenen/gespeicherten Stands, je Block der Datei
#: (None = keiner). Blockweise, damit eine abgeleitete Aenderung einzelne Bloecke
#: nachfuehren kann, ohne echte Aenderungen anderswo zu verdecken.
_gemerkter_stand: dict | None = None


def _ohne(d, felder) -> dict:
    return {k: v for k, v in d.items() if k not in felder} if isinstance(d, dict) else d


def _vc_ohne_live_werte(knoten):
    """VC-Baum (auch in Frames verschachtelt) ohne die Bedienwerte."""
    if isinstance(knoten, list):
        return [_vc_ohne_live_werte(k) for k in knoten]
    if isinstance(knoten, dict):
        felder = _LIVE_FELDER_VC.get(knoten.get("type"), ())
        return {k: _vc_ohne_live_werte(v) for k, v in knoten.items() if k not in felder}
    return knoten


def _vc_gesteuerte_busse(knoten, out: set) -> set:
    """Tempo-Busse, die ein VC-Element beim Bedienen umkonfiguriert: der
    Bus eines Tempo-Bus-Reglers und der eines Speed-Knotens (``SpeedNode``)."""
    if isinstance(knoten, list):
        for k in knoten:
            _vc_gesteuerte_busse(k, out)
    elif isinstance(knoten, dict):
        typ = knoten.get("type")
        bus = knoten.get("tempo_bus_id")
        if bus and (typ == "VCTempoBusController"
                    or (typ == "VCSpeedDial" and knoten.get("target_mode") == "SpeedNode")):
            out.add(str(bus))
        for v in knoten.values():
            if isinstance(v, (list, dict)):
                _vc_gesteuerte_busse(v, out)
    return out


def _executor_nur_fader(e) -> bool:
    """Ein Executor im Werkszustand, der nur wegen seines Faders in der Datei
    steht (``to_dict`` legt jeden abweichenden ab) — fuer den Vergleich wie
    nicht vorhanden."""
    if not isinstance(e, dict):
        return False
    return (e.get("stack_index", -1) == -1
            and e.get("label") == f"Exec {e.get('slot')}"
            and e.get("fader_function", "volume") == "volume"
            and (e.get("btn1"), e.get("btn2"), e.get("btn3")) == ("go", "back", "flash"))


def _ohne_live_werte(show: dict) -> dict:
    """Kopie von ``show`` ohne die Live-Felder (s. ``_LIVE_*``)."""
    d = {k: v for k, v in show.items() if k not in _LIVE_BLOECKE}
    fn = d.get("functions")
    if isinstance(fn, dict) and isinstance(fn.get("functions"), list):
        d["functions"] = dict(fn, functions=[
            _ohne(f, _LIVE_FELDER_FUNKTION) for f in fn["functions"]])
    if isinstance(d.get("tempo_buses"), list):
        gesteuert = _vc_gesteuerte_busse(d.get("virtual_console"), set())

        def _bus_ohne(b):
            felder = _LIVE_FELDER_TEMPO_BUS
            if isinstance(b, dict) and str(b.get("bus_id", "")) in gesteuert:
                felder = felder + _LIVE_FELDER_TEMPO_BUS_GESTEUERT
            return _ohne(b, felder)
        d["tempo_buses"] = [_bus_ohne(b) for b in d["tempo_buses"]]
    d["tempo_grandmaster"] = _ohne(d.get("tempo_grandmaster"), _LIVE_FELDER_GRANDMASTER)
    ex = d.get("executors")
    if isinstance(ex, dict):
        # current_page: welche Executor-Seite gerade offen ist = Bedienung
        ex = _ohne(ex, ("current_page",))
        if isinstance(ex.get("pages"), list):
            ex["pages"] = [[_ohne(e, _LIVE_FELDER_EXECUTOR) for e in seite
                            if not _executor_nur_fader(e)]
                           if isinstance(seite, list) else seite
                           for seite in ex["pages"]]
        d["executors"] = ex
    lv = d.get("live_view")
    if isinstance(lv, dict):
        d["live_view"] = dict(lv, meta=_ohne(lv.get("meta"), _LIVE_FELDER_LIVE_VIEW_META))
    d["virtual_console"] = _vc_ohne_live_werte(d.get("virtual_console"))
    return d


def _abdruck(wert) -> str:
    import hashlib
    try:
        text = json.dumps(wert, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:   # gemischte Schluesseltypen lassen sich nicht sortieren
        text = json.dumps(wert, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _block_abdruecke(state=None, views: dict | None = None) -> dict | None:
    """Fingerabdruck je Block des aktuellen Show-Inhalts ohne Live-Felder.

    ``views``: Bloecke, die der Aufrufer statt aus dem State liefert — das
    Hauptfenster reicht so VC-Layout, Snapshots und Kanal-Gruppen aus seinen
    Views herein, OHNE sie in den State zu schreiben (der State-Stand des
    VC-Layouts enthaelt noch die beim Laden uebersprungenen Widgets, die der
    Auto-Save sonst verloere). ``None``, wenn der Inhalt nicht einsammelbar ist.
    """
    if state is None:
        from src.core.app_state import get_state
        state = get_state()
    try:
        show = _show_daten(state, [])
        for block, wert in (views or {}).items():
            show[block] = wert
        inhalt = _ohne_live_werte(show)
        return {block: _abdruck(wert) for block, wert in inhalt.items()}
    except Exception as e:
        print(f"[show_file] fingerabdruck error: {e}")
        return None


def show_fingerabdruck(state=None, views: dict | None = None) -> str | None:
    """Fingerabdruck des aktuellen Show-Inhalts ohne Live-Felder.

    ``None``, wenn der Inhalt nicht einsammelbar ist (dann laesst sich nichts
    vergleichen). ``views`` wie bei :func:`_block_abdruecke`; ohne sammelt er
    NUR aus dem State.
    """
    bloecke = _block_abdruecke(state, views)
    return None if bloecke is None else _abdruck(bloecke)


def merke_show_stand(state=None, views: dict | None = None) -> None:
    """Aktuellen Stand als „unveraendert" merken — nach Laden, Speichern,
    Neue Show. NICHT nach dem Auto-Save: der sichert nur gegen Abstuerze, die
    Show-Datei des Nutzers ist danach weiterhin alt."""
    global _gemerkter_stand
    _gemerkter_stand = _block_abdruecke(state, views)


def show_hat_aenderungen(state=None, views: dict | None = None) -> bool:
    """True, wenn sich der Show-Inhalt seit :func:`merke_show_stand` geaendert hat.

    Ohne gemerkten Stand oder ohne berechenbaren Fingerabdruck: True — lieber
    einmal zu viel fragen als ungespeicherte Arbeit kommentarlos verwerfen."""
    if _gemerkter_stand is None:
        return True
    jetzt = _block_abdruecke(state, views)
    return jetzt is None or jetzt != _gemerkter_stand


def abgeleitete_aenderung_nachfuehren(aendern, state=None,
                                      bloecke=ABGELEITETE_3D_BLOECKE):
    """``aendern()`` ausfuehren — eine Aenderung, die die Software selbst aus
    schon gespeicherten Daten ABLEITET, nicht der Bediener. Entsprachen die
    ``bloecke`` vorher dem gemerkten Stand, gilt ihr neuer Inhalt danach als
    gemerkt; andere Bloecke bleiben unberuehrt (eine echte Aenderung dort zaehlt
    weiter). Lagen in den Bloecken schon ungespeicherte Aenderungen, bleibt alles
    wie es ist. Liefert, was ``aendern()`` liefert.

    Anlass (UI-69-Korrektur): der 3D-Visualizer uebernimmt beim ersten
    ``requestFixtures`` nach dem Laden die Live-View-Positionen asynchron in
    ``visualizer_positions`` (Auto-Patch) — nach reinem Oeffnen fragte Beenden
    sonst nach dem Speichern."""
    global _gemerkter_stand
    gemerkt = _gemerkter_stand
    vorher = _block_abdruecke(state) if gemerkt is not None else None
    ergebnis = aendern()
    if (gemerkt is None or vorher is None or ergebnis is False
            or _gemerkter_stand is not gemerkt):
        return ergebnis
    if any(vorher.get(b) != gemerkt.get(b) for b in bloecke):
        return ergebnis
    nachher = _block_abdruecke(state)
    if nachher is not None:
        _gemerkter_stand = dict(gemerkt, **{b: nachher.get(b) for b in bloecke})
    return ergebnis


def reset_show():
    """Setzt den App-State vollstaendig auf eine leere Show zurueck.

    Mirror von load_show(), nur mit leeren Daten: Patch (gepatchte Fixtures),
    Programmer, Cue-Stacks, Executors, Paletten, Kurven, Funktionen,
    Snap-Bibliothek, Virtual Console, Snapshots sowie Visualizer-/Live-View-
    Positionen werden geleert. So beginnt "Neue Show" wirklich bei null und
    behaelt nichts aus der vorherigen Show (auch nicht aus current_show.db).
    """
    from src.core.app_state import get_state
    state = get_state()
    _reset_state(state, emit_events=True)
    merke_show_stand(state)          # UI-69: frisch geleert = nichts zu speichern


def _undo_verlauf_leeren() -> None:
    """STAB-29/FM-52: Die Rueckgaengig-Verlaeufe gehoeren zur Show, nicht zur App.

    Bis 2026-09-29 ueberlebte er „Neue Show" und „Show oeffnen": seine
    Eintraege sind Closures auf Geraete-NUMMERN (``remove_fixture(fid)``,
    ``_restore_fixture_dict``). Strg+Z nach einem Showwechsel loeschte oder
    ueberschrieb damit Geraete der NEUEN Show, die zufaellig dieselbe Nummer
    tragen. Geleert wird beim Zuruecksetzen UND nach dem Laden (falls der
    Loader selbst Eintraege erzeugt)."""
    try:
        from src.core.undo import get_undo_stack
        get_undo_stack().clear()
    except Exception as e:
        print(f"[show_file] undo clear error: {e}")
    # FM-52: der Programmer hat einen EIGENEN Verlauf (Programmer-Werte je
    # Geraete-Nummer) — aus demselben Grund mit leeren.
    try:
        from src.core.app_state import get_state
        get_state()._get_programmer_verlauf().leeren()
    except Exception as e:
        print(f"[show_file] programmer verlauf clear error: {e}")


def _reset_state(state, *, emit_events: bool = True, blackout_output: bool = True):
    """STAB-19b: geteilte SSOT-Reset-Logik (Rumpf von reset_show). Leert den
    App-State auf eine leere Show.

    ``reset_show()`` ruft dies mit ``emit_events=True`` (Voll-Reset +
    Listener-Benachrichtigung fuer „Neue Show"). ``load_show()`` ruft es als
    ERSTEN Schritt mit ``emit_events=False`` (leere Baseline VOR dem Laden):
    stuerzt danach eine der wenigen ungefangenen Zeilen ab, sind die noch nicht
    geladenen Bloecke LEER statt ALT — kein halb-alter Frankenstein-Zustand.

    ``emit_events=False`` unterdrueckt den Tail-Emit-Block KOMPLETT —
    insbesondere ``state.sync.refresh_all()``, das als direkter Bus-Call
    ``_suppress_emits`` UMGEHT: sonst gaebe reset-first ein Doppel-Refresh
    (leer -> voll) und einen re-entranten Rebuild mitten im Laden (BUG-01).

    ⚠️ MIRROR-PFLICHT: dies MUSS jedes Feld leeren, das ``load_show`` setzt —
    sonst kippt die reset-first-Garantie fuer ein neu hinzugefuegtes Feld still
    nach Frankenstein zurueck. Regressionstest: ``test_stab19b_load_atomic.py``.
    """
    _undo_verlauf_leeren()           # STAB-29
    from src.core.engine.palette import get_palette_manager

    # UI-57: LIVE-Uebersteuerungen ZUERST aufheben — vor allem anderen.
    #
    # „Alles Weiss" legt einen Moment-Override in den Render-Pfad
    # (`AppState._all_white_map`), Freeze haelt die ganze Ausgabe an. Beide
    # ueberlebten bisher JEDE globale Ruecksetzung: nach „Neue Show" wirkte der
    # Weiss-Override auf die fids der NEUEN Show, also auf voellig andere
    # Geraete, und ein eingefrorener Ausgang liess die neue Show gar nicht erst
    # erscheinen. Beides ist ein Zustand, aus dem der Nutzer nicht mehr
    # herausfindet, weil die naheliegende Rettung („dann eben neue Show") ihn
    # nicht erreicht.
    #
    # Bewusst am ANFANG: der Rest des Resets nullt die DMX-Puffer und flusht;
    # bei noch stehendem Freeze ginge dieser Flush nicht auf die Leitung.
    state._all_white_map = None
    try:
        state.set_freeze(False)
    except Exception as e:
        print(f"[show_file] reset unfreeze error: {e}")
    # VCB-11: gezielte Blackouts (gedrueckte VC-Blackout-Tasten mit Ziel) gehoeren
    # zur alten Show — ihre fids zeigten in der neuen auf fremde Geraete.
    try:
        state.clear_all_target_blackouts()
    except Exception as e:
        print(f"[show_file] reset target blackout error: {e}")

    # Patch (gepatchte Fixtures) leeren — entfernt sie auch aus current_show.db
    _replace_patch_from_data(state, [])

    # DEMO-03: zusaetzlich HART die Patch-Tabelle leeren (DELETE), wie es load_show
    # ueber clear_patch() tut. Schlaegt das clear_patch() in _replace_patch_from_data
    # fehl (z.B. nach abgestuerztem Generator-Lauf), faellt es dort auf remove_fixture
    # ueber den CACHE zurueck — verwaiste DB-Zeilen, die NICHT im Cache stehen, bleiben
    # dann liegen und lassen den FLD-FID-Guard in add_fixture auf next_fid() ausweichen
    # (ueberraschend verschobene Fixture-IDs beim naechsten Patch). Ein direkter,
    # eigenstaendig abgesicherter clear_patch()-Aufruf garantiert die leere Tabelle.
    # STAB-09: den harten clear_patch() im _suppress_emits-Fenster ausfuehren.
    # _replace_patch_from_data hat _suppress_emits in seinem finally wieder auf
    # False gesetzt; ein ungedrosseltes clear_patch() wuerde hier synchron
    # patch_changed feuern, waehrend programmer/functions/VC/Snaps noch ALT sind
    # -> re-entranter Refresh mitten im Reset (genau der STAB-07/BUG-01-Pfad ->
    # native Access Violation). Der finale gebuendelte patch_changed-Emit unten
    # bleibt die einzige Notification.
    _prev_suppress = getattr(state, "_suppress_emits", False)
    state._suppress_emits = True
    try:
        state.clear_patch()
    except AttributeError:
        pass  # aeltere AppState-API ohne clear_patch
    except Exception as e:
        print(f"[show_file] reset clear_patch error: {e}")
    finally:
        state._suppress_emits = _prev_suppress

    # Fixture-Gruppen aus der Show-DB leeren (SSOT — sonst bleiben Gruppen nach Neue Show)
    try:
        from sqlalchemy import delete
        from src.core.database.models import FixtureGroup
        with state._session() as s:
            s.execute(delete(FixtureGroup))
            s.commit()
    except Exception as e:
        print(f"[show_file] reset groups error: {e}")

    state.programmer = {}
    # FM-52: der Patch-Ersatz oben leert den Programmer ueber clear_programmer —
    # das wuerde als ruecknehmbarer Schritt im Programmer-Verlauf landen. Der
    # Verlauf gehoert zur alten Show: nach dem Leeren hier erneut verwerfen.
    try:
        state._get_programmer_verlauf().leeren()
    except AttributeError:
        pass  # gefaelschter State ohne Verlauf
    state.base_levels = {}
    # VCB-05: Gruppen-/Fixture-Dimmer (F-25 GROUP_DIMMER-Fader) leeren — sonst dimmt
    # ein Fader der vorigen Show die Fixtures der neuen Show weiter herunter.
    state.fixture_dimmers = {}
    # F-26b: ebenso die Feature-Dimmer-Slots (FEATURE_DIMMER-Fader) verwerfen.
    # STAB-19b: kapseln — ein Wurf hier darf im reset-first-Pfad nicht den REST
    # des Resets verschlucken (sonst blieben spaetere Felder ALT = Frankenstein).
    try:
        if hasattr(state, "clear_feature_dimmers"):
            state.clear_feature_dimmers()
    except Exception as e:
        print(f"[show_file] reset feature_dimmers error: {e}")
    # Neue Show: strikte Trennung Farbe/Dimmer (Default seit 2026-06-24). Eine reine
    # Farbe macht den Dimmer NICHT automatisch auf — Helligkeit kommt aus Dimmer-
    # Snaps/-Effekten/Mastern. Per Menue-Schalter umschaltbar.
    state.implicit_brightness = False
    # DMX-Puffer aller Universes nullen. Sonst sendet der Output-Thread nach
    # "Neue Show" weiter die ALTEN Werte (die Strahler bleiben an): ein leerer
    # Patch hat keinen Default-Frame mehr, und _render_frame fasst die Buffer der
    # nun unpatchten Universes nicht mehr an -> alte Werte bleiben stehen.
    # STAB-19b: NUR bei blackout_output (reset_show / „Neue Show" will die harte
    # Blende). Beim load_show-reset-first (blackout_output=False) uebersprungen —
    # sonst blitzt bei JEDEM Laden ein physischer Blackout-Puls auf der laufenden
    # DMX-Ausgabe (44-Hz-Output-Thread liest die genullten Universes), bevor der
    # neue Patch-Render die Werte gleich wieder setzt. Der Render-Plan wird ueber
    # replace_patch (leerer + dann neuer Patch) ohnehin frisch aufgebaut.
    if blackout_output:
        try:
            for _u in getattr(state, "universes", {}).values():
                _u.clear()
        except Exception as e:
            print(f"[show_file] reset universes error: {e}")
        try:
            state._flush_all_to_dmx()
        except Exception as e:
            print(f"[show_file] reset flush error: {e}")

    try:
        get_palette_manager().from_dict({})
    except Exception as e:
        print(f"[show_file] reset palettes error: {e}")

    # Live-Edit-Slots (benannte Bearbeitungsziele) leeren — sonst zeigen Fader/Farben
    # nach „Neue Show" noch auf alte Funktions-IDs.
    try:
        from src.core.engine import effect_live
        effect_live.clear_edit_targets()
        effect_live.clear_live_overrides()
    except Exception as e:
        print(f"[show_file] reset live edit state error: {e}")

    try:
        from src.core.engine.curve_library import get_curve_library
        get_curve_library().from_dict({})
    except Exception as e:
        print(f"[show_file] reset curves error: {e}")

    try:
        from src.core.engine.efx_path import get_efx_path_library
        get_efx_path_library().from_dict({})
    except Exception as e:
        print(f"[show_file] reset efx_paths error: {e}")

    try:
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        get_tempo_bus_manager().load_dict([])
        get_tempo_bus_manager().load_grandmaster({})
    except Exception as e:
        print(f"[show_file] reset tempo buses error: {e}")

    try:
        state.cue_stacks.clear()
    except Exception as e:
        print(f"[show_file] reset cue stacks error: {e}")

    # LAS-07b: gezeichnete Laser-Muster leeren.
    try:
        state.laser_figures = []
    except Exception as e:
        print(f"[show_file] reset laser figures error: {e}")

    # LAS-18b: gemerkte Werksmuster-Slots leeren.
    try:
        state.laser_patterns = []
    except Exception as e:
        print(f"[show_file] reset laser patterns error: {e}")

    pe = getattr(state, "playback_engine", None)
    if pe is not None:
        try:
            pe.from_dict({}, state.cue_stacks)
        except Exception as e:
            print(f"[show_file] reset executors error: {e}")

    try:
        fm = getattr(state, "function_manager", None)
        if fm is not None:
            fm.from_dict({"functions": []})
    except Exception as e:
        print(f"[show_file] reset function manager error: {e}")

    try:
        from src.core.engine.snap_library import get_snap_library
        get_snap_library().from_dict({})
    except Exception as e:
        print(f"[show_file] reset snap library error: {e}")

    state._efx_instances = []
    state._rgb_matrix_instances = []
    state._vc_layout = {}
    state._snapshots_data = []
    state._channel_groups_data = []
    # VIZ-11: Szenegraph komplett neu (deckt den echten AppState, dessen 5
    # Legacy-Felder Views auf state._scene sind, siehe app_state.py). Die
    # expliziten Feld-Resets darunter bleiben zusaetzlich bestehen, damit
    # Fake-States ohne Property-Adapter (z. B. tests/test_show_file.py
    # _FakeState) weiterhin korrekt geleert werden.
    try:  # STAB-19b: kapseln (set_scene haengt lebende Registry-Views um).
        if hasattr(state, "_scene"):
            from src.core.stage.scene_graph import SceneGraph
            _replace_scene(state, SceneGraph())
    except Exception as e:
        print(f"[show_file] reset scene error: {e}")
    if hasattr(state, "_live_view_transient"):
        state._live_view_transient = {}
    state.visualizer_positions = {}
    state.visualizer_rotations = {}
    state.visualizer_docks = {}
    state.active_stage_name = "simple"
    state.live_view_positions = {}
    state.live_view_meta = {}
    state.visualizer_named_cameras = []
    state.visualizer_beams_off = set()
    state._last_loaded_layout = {}
    state.show_name = "Neue Show"
    state.playlist = []
    state.music_autoshow = {"enabled": False, "function_ids": [], "bank": 0}
    try:
        from src.core.audio.media_player import get_media_player
        mp = get_media_player()
        # STAB-19b: `set_tracks` feuert playlistChanged/trackChanged (Qt-Signale,
        # die _suppress_emits NICHT kennen). Beim reset-first (emit_events=False)
        # die Tracks weiter LEEREN (Frankenstein-Garantie), aber den synchronen
        # UI-Rebuild via blockSignals unterdruecken.
        if emit_events:
            mp.set_tracks([])
        else:
            _blocked = mp.blockSignals(True)
            try:
                mp.set_tracks([])
            finally:
                mp.blockSignals(_blocked)
    except Exception as e:
        print(f"[show_file] playlist reset error: {e}")

    try:
        state._rebuild_render_plan()
    except Exception as e:
        print(f"[show_file] reset render plan error: {e}")

    # Listener benachrichtigen (gleiche Events wie beim Laden), damit alle
    # Views (Patch, VC, Programmer, Snapshots …) die leere Show uebernehmen.
    # STAB-19b: NUR bei emit_events (reset_show / „Neue Show"). Beim load_show-
    # reset-first (emit_events=False) uebersprungen — sonst Doppel-Emit
    # (leer -> voll) UND sync.refresh_all() als direkter Bus-Call, der
    # _suppress_emits umgeht (BUG-01: re-entranter Rebuild mitten im Laden).
    if emit_events:
        try:
            state._emit("patch_changed", None)
            state._emit("stacks_changed", None)
            state._emit("cue_stack_changed", None)
            state._emit("show_loaded", {"path": None, "issues": []})
            state.sync.refresh_all()
        except Exception as e:
            print(f"[show_file] reset post events error: {e}")


def _resolve_stage_definition(stage_name: str):
    """Loest die aktive Buehne (Preset-Key oder User-Stage, %APPDATA%) auf.
    None, wenn nicht aufloesbar (z.B. User-Stage-Datei fehlt) — dann werden
    beim VIZ-11-Migrations-Fallback Fixtures zu Root-Nodes (siehe
    SceneGraph.from_legacy, docs/VIZ11_SCENEGRAPH_DESIGN.md (c) Schritt 2)."""
    try:
        from src.core.stage.stage_definition import DEFAULT_PRESETS, load_stage
        name = stage_name or "simple"
        if name in DEFAULT_PRESETS:
            return DEFAULT_PRESETS[name]()
        return load_stage(name)
    except Exception as e:
        print(f"[show_file] resolve stage definition error: {e}")
        return None


def _resolve_stage_element_ids(stage_name: str) -> set[str] | None:
    """Element-IDs der aktiven Buehne (Preset-Key oder User-Stage), oder None
    wenn die Buehne nicht aufloesbar ist (dann keine Dock-Bereinigung)."""
    stage = _resolve_stage_definition(stage_name)
    if stage is None:
        return None
    return {e.id for e in stage.elements}


def read_show_version(path: str | os.PathLike) -> str | None:
    """Liest NUR das ``version``-Feld einer .lshow, ohne den App-State
    anzufassen. Fuer den VIZ-11-Backup-Entscheid in main_window._do_save
    (Orchestrator-Entscheidung 2): Backup nur, wenn die auf der Platte
    liegende Datei NOCH kein scene_graph-Format hat (Version < 1.2).
    None bei jeglichem Lesefehler (z.B. Datei existiert noch nicht -> "Speichern
    unter" auf neuen Pfad) oder fehlendem "version"-Schluessel."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            raw = zf.read("show.json").decode("utf-8")
        data = json.loads(raw)
        version = data.get("version")
        return str(version) if version is not None else None
    except Exception:
        return None


def _load_show_impl(path: str | os.PathLike):
    """Load a .lshow file and replace app state. Returns (ok: bool, msg: str)."""
    from src.core.app_state import get_state
    from src.core.engine.palette import get_palette_manager
    from src.core.engine.cue_stack import CueStack

    _ladeprobleme.clear()   # QA-50: Sammler gehoert diesem Ladevorgang

    try:
        with zipfile.ZipFile(path, "r") as zf:
            raw = zf.read("show.json").decode("utf-8")
            # VC-IMG: eingebettete VC-Button-Assets in den lokalen Cache entpacken,
            # damit die Buttons ihre Bilder/GIFs finden (resolve()). Fehler pro
            # Eintrag ignorieren (eine kaputte Asset-Datei darf das Laden nicht
            # abbrechen — der Button zeigt dann eben kein Bild).
            from . import vc_assets
            for _name in zf.namelist():
                if vc_assets.is_asset_entry(_name):
                    try:
                        vc_assets.store_extracted(vc_assets.key_from_entry(_name), zf.read(_name))
                    except Exception:
                        pass
        data = json.loads(raw)
    except Exception as e:
        return False, f"Öffnen fehlgeschlagen: {e}"

    # STAB-20: show.json MUSS ein Objekt sein. Gueltiges JSON, das eine Liste/Zahl/
    # String/null ist (korrupte oder fremde Datei), fuehrte sonst beim ersten
    # data.get(...) zu einem ungefangenen AttributeError (der Aufrufer stuerzt) statt
    # einer sauberen Fehlermeldung.
    if not isinstance(data, dict):
        return False, "Ungültiges Show-Format: show.json ist kein Objekt."

    # Fremdformat-Gate (2026-07-26): eine show.json OHNE "version" UND ohne
    # jeden bekannten Show-Block ist keine LightOS-Show. Vorher lief so eine
    # Datei durch den ganzen Loader — jedes data.get("patch"/"functions"/…)
    # traf ins Leere -> der Nutzer bekam ok=True samt "Show '<Name>' geladen."
    # und stand vor einer LEEREN Bühne (Patch, VC, Funktionen alle weg), ohne
    # eine einzige Warnung. Konkret aufgefallen an shows/demo_rgb_par.lshow:
    # ein nie implementierter Entwurf ("format_version"/"universes" + eigene
    # ZIP-Einträge patch.json/sequences/…), der zwei Monate lang als "geladen"
    # gemeldet wurde. Ein von save_show geschriebenes Show hat IMMER "version"
    # und alle Blöcke -> kann hier nicht hängenbleiben (Test:
    # tests/test_show_format_upgrade.py).
    if "version" not in data and not (_KNOWN_SHOW_BLOCKS & set(data)):
        _foreign = ", ".join(sorted(set(data) & _FOREIGN_MARKERS)) or "keine"
        return False, (
            "Unbekanntes Show-Format: show.json enthält keinen einzigen "
            "LightOS-Block (patch/functions/virtual_console/…) und keine "
            f"'version'. Fremd-Marker: {_foreign}. Datei nicht geladen — der "
            "bisherige Show-Zustand bleibt erhalten."
        )

    # VC-IMG-GC: den lokalen VC-Asset-Cache deckeln. Oben wurden die eingebetteten
    # Assets DIESER Show entpackt; über viele Shows sammeln sich verwaiste Assets
    # früher geladener Shows an. Verwaiste per LRU wegräumen — aber nie die vom
    # gerade geladenen Show referenzierten Keys. Darf das Laden nie stören.
    try:
        from . import vc_assets as _vc_assets
        _vc_assets.prune(keep=_vc_assets.collect_keys(data))
    except Exception:
        pass

    # STAB-20: Versions-Gate. Ist die Datei NEUER als das unterstuetzte Format,
    # warnen und best-effort weiterladen (statt sie still als aktuelles Format zu
    # deuten und ggf. neuere Felder falsch zu interpretieren).
    def _ver_tuple(v):
        try:
            return tuple(int(x) for x in str(v).split("."))
        except (TypeError, ValueError):
            return ()
    _file_ver = _ver_tuple(data.get("version"))
    if _file_ver and _file_ver > _ver_tuple(SHOW_VERSION):
        print(f"[show_file] WARNUNG: Show-Version {data.get('version')!r} ist neuer "
              f"als unterstuetzt ({SHOW_VERSION}) — lade best-effort, neuere Felder "
              f"werden ignoriert.")

    state = get_state()
    pm = get_palette_manager()

    # STAB-19b: RESET-FIRST — den GESAMTEN State auf leer setzen, BEVOR ein Block
    # geladen wird (geteilte SSOT mit reset_show via _reset_state). Stuerzt danach
    # eine der wenigen ungefangenen Zeilen ab, sind die noch NICHT geladenen
    # Bloecke LEER statt ALT -> kein halb-alter Frankenstein-Zustand. emit_events=
    # False + Suppress-Fenster: kein Doppel-Refresh, kein refresh_all-BUG-01.
    # Best-effort — der Reset selbst darf den Load NIE abbrechen.
    #
    # CDX-22: reset-first (leerer Patch) UND der neue Patch bilden EINEN
    # Patch-Tausch — die Freigabe entpatchter Adressen darf erst am ENDE laufen,
    # sonst nullt der Zwischenschritt mit dem leeren Patch alle alten Adressen im
    # Live-Universe und der Output-Thread sendet den Blackout-Puls, bis der neue
    # Patch gerendert ist.
    with _deferred_addr_release(state):
        _prev_suppress = getattr(state, "_suppress_emits", False)
        state._suppress_emits = True
        try:
            # emit_events=False: keine Tail-Emits/refresh_all (BUG-01). blackout_output=
            # False: kein physischer DMX-Blackout-Puls (der neue Patch-Render setzt die
            # Werte gleich; alte Werte bleiben bis dahin stehen wie vor STAB-19b).
            _reset_state(state, emit_events=False, blackout_output=False)
        except Exception as e:
            _lenient("reset-first before load error", e)
        finally:
            state._suppress_emits = _prev_suppress

        # STAB-19b (C-Haertung): der Patch-Replace ist eine der wenigen UNGEFANGENEN
        # Zeilen (die pfs-Bauschleife in _replace_patch_from_data ist nicht pro-Eintrag
        # gekapselt) — kapseln, damit ein Wurf hier den Show-Load nicht bis in den
        # Qt-Slot durchschlaegt (reset-first hat den Rest bereits geleert).
        # STAB-25: kein stummes ``if isinstance(..., list)`` mehr um den Aufruf —
        # die Formpruefung sitzt in ``_replace_patch_from_data`` und meldet.
        # Fehlt der Block ganz, bleibt es beim ``[]`` ohne Warnung.
        patch_entries = data.get("patch", [])
        try:
            _replace_patch_from_data(state, patch_entries)
        except Exception as e:
            _lenient("load patch error", e)

    # VCB-05: Gruppen-/Fixture-Dimmer der vorigen Show verwerfen (sonst Ghost-Dimmer).
    state.fixture_dimmers = {}
    # F-26b: ebenso die Feature-Dimmer-Slots verwerfen (STAB-19b: ungefangen -> kapseln).
    try:
        if hasattr(state, "clear_feature_dimmers"):
            state.clear_feature_dimmers()
    except Exception as e:
        _lenient("load clear_feature_dimmers error", e)

    # Spatial-Gruppen wiederherstellen (sonst fehlt die MH-/PAR-Gruppe nach Load).
    # STAB-24 (b): KEIN ``or []`` — das machte einen ``null``-Block stumm leer.
    _restore_fixture_groups(
        state, _liste_im_block(data, "fixture_groups", "Fixture-Gruppen"))

    # CDX-18: EURON10-2-Kanal-fids EINMAL bestimmen (nach dem Patch, daher fid->
    # Profil verfuegbar) fuer die fan-Split-Kompat, die unten pro Playback-Container
    # inline laeuft — jeweils VOR dessen nachgelagertem Flush/Rebuild/Verbraucher.
    _euron10_fids = _euron10_2ch_fids(state)

    try:
        programmer = data.get("programmer", {}) or {}
        cleaned = {}
        for fid_raw, attrs in programmer.items():
            try:
                fid = int(fid_raw)
            except Exception:
                continue
            if not isinstance(attrs, dict):
                continue
            # STAB-18: int(v) PRO Wert kapseln — ein einzelner kaputter Wert
            # (None/Liste/nicht-numerisch) darf nur diesen Eintrag ueberspringen,
            # nicht den GESAMTEN Programmer aller Fixtures loeschen (Verlust-
            # Amplifikation). Analog zur schon vorhandenen fid-/attrs-Isolation.
            # A3D-19: OverflowError mitfangen — json.loads('1e999') ergibt
            # float('inf'), und int(inf) wirft OverflowError (NICHT ValueError);
            # ohne den Fang riss der eine Wert bisher den ganzen Programmer mit.
            vals = {}
            for a, v in attrs.items():
                try:
                    vals[str(a)] = int(v)
                except (TypeError, ValueError, OverflowError):
                    continue
            # CDX-18: fan<-dimmer VOR dem gleich folgenden _flush_all_to_dmx(),
            # sonst zeigte der Luefter unmittelbar nach dem Laden weiter 0.
            _fill_fan_from_dimmer(vals, fid, _euron10_fids)
            cleaned[fid] = vals
        state.programmer = cleaned
        state._flush_all_to_dmx()
    except Exception as e:
        _lenient("load programmer error", e)
        state.programmer = {}

    # Basis-Level (PAR-Grundhelligkeit o. ä.) NACH dem Patch laden und den
    # Render-Plan neu bauen, damit die Basis im Default-Frame landet.
    try:
        bl = data.get("base_levels", {}) or {}
        parsed = {}
        for k, vals in bl.items():
            if not isinstance(vals, dict):
                continue
            try:
                fid = int(k)
            except (TypeError, ValueError):
                continue
            # STAB-18: int(v) pro Wert kapseln (ein kaputter Wert -> nur dieser
            # faellt, nicht alle Basis-Level). A3D-19: OverflowError mitfangen
            # (int(float('inf')) aus '1e999'), sonst reisst er alle Basis-Level mit.
            clean = {}
            for a, v in vals.items():
                try:
                    clean[str(a)] = int(v)
                except (TypeError, ValueError, OverflowError):
                    continue
            # CDX-18: fan<-dimmer VOR dem gleich folgenden _rebuild_render_plan(),
            # sonst faehrt der Default-Frame den Luefter dauerhaft auf 0.
            _fill_fan_from_dimmer(clean, fid, _euron10_fids)
            parsed[fid] = clean
        state.base_levels = parsed
        state.implicit_brightness = bool(data.get("implicit_brightness", True))
    except Exception as e:
        _lenient("load base_levels error", e)
        state.base_levels = {}
        state.implicit_brightness = True
    # STAB-18: Render-Plan-Rebuild NACH und AUSSERHALB des base_levels-try. Frueher
    # stand er IM try nach der base_levels-Zuweisung -> ein aus voellig unabhaengigem
    # Grund werfender Rebuild landete im except und verwarf die eben geladenen
    # base_levels + kippte implicit_brightness. Jetzt getrennt behandelt.
    try:
        state._rebuild_render_plan()
    except Exception as e:
        _lenient("rebuild render plan after base_levels error", e)

    if "palettes" in data:
        try:
            pm.from_dict(data["palettes"])
        except Exception as e:
            _lenient("load palettes error", e)
    else:
        # STAB-19: Show OHNE palettes-Key -> Paletten der Vorshow verwerfen. palettes
        # war der einzige Manager mit reinem if-ohne-else — dadurch blieben beim Laden
        # einer palettes-losen Show die Farbpaletten der vorigen Show haengen (Bleed).
        # reset_show leert Paletten ebenfalls via from_dict({}).
        try:
            pm.from_dict({})
        except Exception as e:
            _lenient("reset palettes (kein Key) error", e)

    # CDX-18: fan<-dimmer NUR in den per-Fixture-Overrides (Palette.fixture_values);
    # die generische Palette.values hat keinen Fixture-Bezug und darf NICHT (sonst
    # bekaeme jedes Gerät, das die Palette nutzt, faelschlich einen fan-Kanal).
    if _euron10_fids:
        try:
            for _p in pm.get_all():
                for _fid, _attrs in (getattr(_p, "fixture_values", {}) or {}).items():
                    _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan palette migration failed: {e}")

    try:
        from src.core.engine.curve_library import get_curve_library
        get_curve_library().from_dict(data.get("curves", {}) or {})
    except Exception as e:
        _lenient("load curves error", e)

    # LAS-07b: gezeichnete Laser-Muster.
    try:
        from src.core.laser.figure import LaserFigure
        # STAB-24 (d): je Figur — ein kaputter Punkt kostete sonst alle Figuren.
        state.laser_figures = _je_eintrag(
            _liste_im_block(data, "laser_figures", "Laser-Figuren"),
            LaserFigure.from_dict, "Laser-Figur", "name")
    except Exception as e:
        _lenient("load laser figures error", e)

    # LAS-18b: gemerkte Werksmuster-Slots (Alt-Shows: Key fehlt -> leer).
    try:
        from src.core.laser.pattern_slots import PatternSlot
        state.laser_patterns = _je_eintrag(
            _liste_im_block(data, "laser_patterns", "Laser-Muster"),
            PatternSlot.from_dict, "Laser-Muster", "name", "label")
    except Exception as e:
        _lenient("load laser patterns error", e)

    try:
        from src.core.engine.efx_path import get_efx_path_library
        get_efx_path_library().from_dict(data.get("efx_paths", {}) or {})
    except Exception as e:
        _lenient("load efx_paths error", e)

    try:
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        get_tempo_bus_manager().load_dict(data.get("tempo_buses", []) or [])
        get_tempo_bus_manager().load_grandmaster(data.get("tempo_grandmaster") or {})
    except Exception as e:
        _lenient("load tempo buses error", e)

    try:
        state.cue_stacks.clear()
        for sd in data.get("cue_stacks", []) or []:
            if not isinstance(sd, dict):
                continue
            try:                       # eine kaputte Cueliste darf nicht ALLE verwerfen
                state.cue_stacks.append(CueStack.from_dict(sd))
            except Exception as e:
                _lenient("skip bad cue stack", e)
        # F-16: jeder Cueliste den Sub-Cuelisten-Resolver geben.
        if hasattr(state, "wire_cue_stack_resolvers"):
            state.wire_cue_stack_resolvers()
    except Exception as e:
        _lenient("load cue stacks error", e)

    # CDX-18: fan<-dimmer in allen Cue-Werten der gerade geladenen Cuelisten.
    if _euron10_fids:
        try:
            for _stk in state.cue_stacks:
                for _cue in (getattr(_stk, "cues", []) or []):
                    for _fid, _attrs in (getattr(_cue, "values", {}) or {}).items():
                        _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan cue migration failed: {e}")

    # Executor-/Page-Bindung wiederherstellen (nach den cue_stacks, da die
    # Stack-Referenzen als Index in cue_stacks abgelegt sind). Wird auch bei
    # fehlendem "executors"-Key aufgerufen → setzt stale Bindungen zurueck.
    pe = getattr(state, "playback_engine", None)
    if pe is not None:
        try:
            pe.from_dict(data.get("executors", {}) or {}, state.cue_stacks)
        except Exception as e:
            _lenient("load executors error", e)

    try:
        fm = getattr(state, "function_manager", None)
        if fm is not None:
            functions_payload = data.get("functions", {"functions": []})
            if not isinstance(functions_payload, dict):
                functions_payload = {"functions": []}
            fm.from_dict(functions_payload)
    except Exception as e:
        _lenient("load function manager error", e)

    # CDX-18: fan<-dimmer in allen Sequence-Schritt-Werten (SequenceStep.values
    # nutzt STRING-fid-Keys — _fill_fan_from_dimmer normalisiert via int()).
    if _euron10_fids:
        try:
            from src.core.engine.function import FunctionType as _FT
            _fm = getattr(state, "function_manager", None)
            if _fm is not None:
                for _seq in _fm.by_type(_FT.Sequence):
                    for _step in (getattr(_seq, "steps", []) or []):
                        for _fid, _attrs in (getattr(_step, "values", {}) or {}).items():
                            _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan sequence migration failed: {e}")

    # Snap-Bibliothek pro Show. Hat die Show einen "library"-Block, ist er
    # maßgeblich. Alt-Shows ohne Block erben einmalig die globalen Snap-Dateien.
    try:
        from src.core.engine.snap_library import get_snap_library
        lib = get_snap_library()
        if "library" in data:
            lib.from_dict(data.get("library") or {})
        else:
            lib.migrate_from_disk(replace=True)
    except Exception as e:
        _lenient("load snap library error", e)

    # CDX-18: fan<-dimmer in allen Snap-Werten der Show-Snap-Bibliothek.
    if _euron10_fids:
        try:
            from src.core.engine.snap_library import get_snap_library as _gsl
            for _snap in _gsl().snaps():
                for _fid, _attrs in (getattr(_snap, "values", {}) or {}).items():
                    _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan snap migration failed: {e}")

    # Abwaertskompatibilitaet: Alt-Shows speicherten EFX/RGB-Matrix in separaten
    # Bloecken (nicht als Funktionen). Diese werden hier einmalig in echte
    # Funktionen migriert, damit sie ausgegeben/abrufbar werden. Neue Shows haben
    # die Bloecke leer (Instanzen stehen bereits im "functions"-Block).
    state._efx_instances = []
    state._rgb_matrix_instances = []
    try:
        from src.core.engine.efx import EfxInstance
        for ed in (data.get("efx", []) or []):
            if not isinstance(ed, dict):
                continue
            try:  # STAB-20: pro Eintrag isolieren — ein kaputter Legacy-EFX darf
                  # nicht die Migration abbrechen und alle folgenden verlieren.
                state.function_manager.add(EfxInstance.from_dict(ed))
            except Exception as e:
                _lenient("migrate legacy efx entry error", e)
    except Exception as e:
        _lenient("migrate legacy efx error", e)
    try:
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        for md in (data.get("rgb_matrix", []) or []):
            if not isinstance(md, dict):
                continue
            try:  # STAB-20: pro Eintrag isolieren (wie Legacy-EFX).
                state.function_manager.add(RgbMatrixInstance.from_dict(md))
            except Exception as e:
                _lenient("migrate legacy rgb matrix entry error", e)
    except Exception as e:
        _lenient("migrate legacy rgb matrix error", e)

    state._vc_layout = data.get("virtual_console", {}) or {}

    # Snapshots pro Show: Rohdaten ablegen, die SnapshotsView spielt sie im
    # show_loaded-Handler des Hauptfensters zurück (UI-Thread).
    _snaps_raw = data.get("snapshots", []) or []
    # CDX-18: fan<-dimmer direkt auf den ROHEN Snapshot-Dicts — zum load_show-
    # Zeitpunkt existieren noch KEINE Snapshot-Objekte (sie entstehen erst im
    # UI-Thread), daher hier auf entry["values"][fid_str][attr] (str-fid).
    if _euron10_fids:
        try:
            for _entry in _snaps_raw:
                _vals = _entry.get("values") if isinstance(_entry, dict) else None
                if isinstance(_vals, dict):
                    for _fid, _attrs in _vals.items():
                        _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan snapshot migration failed: {e}")
    state._snapshots_data = _snaps_raw
    # SDK-02: Kanal-Gruppen pro Show (ChannelGroupsView spielt sie zurück).
    state._channel_groups_data = data.get("channel_groups", []) or []

    # Visualizer: Fixture-Positionen + aktive Stage wiederherstellen.
    # Review-Fix (Zwischenmutationen): die rohen Legacy-Dicts (positions/
    # rotations/docks/lv_pos) werden HIER NUR als lokale Python-dicts
    # gesammelt -- OHNE zwischenzeitlich state.visualizer_* zu schreiben.
    # Das vermied fruehere Zwischenmutationen des ALTEN Graphen (state._scene
    # zeigte hier noch auf den Graphen der VORIGEN Show): schlug der weiter
    # unten folgende SceneGraph-Aufbau fehl (Exception), blieb state._scene
    # sonst auf einem Teil-migrierten Zwischenstand haengen (neue Positionen/
    # Rotationen bereits geschrieben, aber KEINE Docks -- from_legacy braucht
    # dafuer mehr als den blossen state.visualizer_docks=docks-Write). Jetzt:
    # erst NACH dem erfolgreichen (oder fehlgeschlagenen) Graph-Aufbau werden
    # die Legacy-Properties gesetzt -- entweder redundant in den bereits
    # korrekten NEUEN Graphen (Abwaertskompatibilitaet fuer Konsumenten, die
    # die Legacy-Properties direkt lesen) oder, fuer Fake-States OHNE
    # state._scene (z. B. tests/test_show_file.py::_FakeState), als einzige
    # Schreibquelle (deren Reihenfolge fuer sie irrelevant ist, da plain-dict-
    # Attribute ohne Graph-Kopplung).
    positions: dict[int, tuple[float, float, float]] = {}
    rotations: dict[int, tuple[float, float, float]] = {}
    docks: dict[int, str] = {}
    lv_pos: dict[int, tuple[float, float]] = {}
    active_stage_name = "simple"
    live_view_meta: dict = {}
    named_cameras: list = []
    visualizer_load_error: Exception | None = None
    try:
        viz = data.get("visualizer", {}) or {}
        for fid_raw, p in (viz.get("positions", {}) or {}).items():
            try:
                positions[int(fid_raw)] = (float(p[0]), float(p[1]), float(p[2]))
            except Exception:
                continue
        # Multi-Achsen-Ausrichtung (rx, ry, rz) in Grad. normalize_rotation laedt
        # auch Alt-Shows korrekt, die nur einen einzelnen Y-Float gespeichert haben.
        for fid_raw, val in (viz.get("rotations", {}) or {}).items():
            try:
                rotations[int(fid_raw)] = normalize_rotation(val)
            except Exception:
                continue
        active_stage_name = str(viz.get("active_stage", "simple") or "simple")
        # Andock-Beziehungen {fid: stage_element_id}. Stale-Eintraege (Element der
        # aktiven Buehne existiert nicht mehr) verwerfen, falls die Buehne aufloesbar.
        for fid_raw, sid in (viz.get("docks", {}) or {}).items():
            try:
                if sid:
                    docks[int(fid_raw)] = str(sid)
            except Exception:
                continue
        valid_ids = _resolve_stage_element_ids(active_stage_name)
        if valid_ids is not None:
            docks = {fid: sid for fid, sid in docks.items() if sid in valid_ids}
    except Exception as e:
        visualizer_load_error = e
        positions = {}
        rotations = {}
        docks = {}
        active_stage_name = "simple"

    # VIZ-13 Schritt 3b-K-2: benannte Kamerapositionen -- additiv, eigener
    # Fehler-Isolierungsblock (ein kaputter named_cameras-Eintrag darf
    # positions/rotations/docks oben nicht mit zu Fall bringen). Alte Shows
    # ohne den Key -> leere Liste (kein SHOW_VERSION-Bump noetig).
    try:
        viz = data.get("visualizer", {}) or {}
        raw_cams = viz.get("named_cameras", []) or []
        named_cameras = [dict(c) for c in raw_cams if isinstance(c, dict)]
    except Exception as e:
        _lenient("load named_cameras error", e)
        named_cameras = []

    # VIZ-15: ausgeblendete Lichtkegel. Eigener Isolierungsblock aus demselben
    # Grund wie oben — ein kaputter Eintrag hier darf die Positionen nicht mit
    # zu Fall bringen. Alte Shows ohne den Key -> leere Menge, also unveraendert.
    try:
        viz = data.get("visualizer", {}) or {}
        # STAB-24 (d): je Eintrag — der Kommentar oben versprach es schon.
        # Blockvertrag wie ueberall: fehlt -> leer, vorhanden aber keine Liste
        # (auch null, auch "12" -> frueher {1, 2}!) -> gemeldet.
        beams_off = set(_je_eintrag(
            _liste_im_block(viz if isinstance(viz, dict) else {}, "beams_off",
                            "Ausgeblendete-Lichtkegel"),
            _kegel_fid, "Ausgeblendeter Lichtkegel"))
    except Exception as e:
        _lenient("load beams_off error", e)
        beams_off = set()

    # Live View: 2D-Fixture-Positionen (eigene Persistenz, entkoppelt vom 3D-Viz)
    live_view_load_error: Exception | None = None
    try:
        lv = data.get("live_view", {}) or {}
        for fid_raw, p in (lv.get("positions", {}) or {}).items():
            try:
                lv_pos[int(fid_raw)] = (float(p[0]), float(p[1]))
            except Exception:
                continue
        # P4: Show-spezifische View-Einstellungen (Zoom/Grid/Snap/Weltgroesse).
        # Alte Shows ohne "meta" -> leeres Dict; die Live View faellt dann auf
        # die ui_prefs-Defaults zurueck (Fallback, kein Fehler).
        meta = lv.get("meta", {})
        live_view_meta = dict(meta) if isinstance(meta, dict) else {}
    except Exception as e:
        live_view_load_error = e
        lv_pos = {}
        live_view_meta = {}

    # active_stage_name wird VOR dem Graph-Aufbau gesetzt (from_dict/from_legacy
    # sowie der Stale-Dock-Filter brauchen die aufgeloeste Buehne).
    state.active_stage_name = active_stage_name

    # VIZ-11 (Schritt 5): SceneGraph aufbauen -- entweder direkt aus dem
    # "scene_graph"-Block (bereits migrierte v1.2+ Show, Graph fuehrend) oder
    # einmalig aus den soeben geladenen Legacy-Feldern (Alt-Show v<=1.1,
    # siehe docs/VIZ11_SCENEGRAPH_DESIGN.md (c) Migrations-Algorithmus).
    # hasattr-Guard: Fake-States in Tests ohne Adapter (kein state._scene)
    # ueberspringen die Migration einfach -- sie kennen die 5 Felder eh nur
    # als plain-dict-Attribute.
    if hasattr(state, "_scene"):
        try:
            if "scene_graph" in data:
                from src.core.stage.scene_graph import SceneGraph
                new_scene = SceneGraph.from_dict(data["scene_graph"])
                # Stale-Dock-Filter (dieselbe Regel wie im Legacy-Pfad, Design
                # (d)) auch hier anwenden: from_dict verwirft nur STRUKTURELL
                # ungueltige parent_id-Referenzen (Ziel-Node fehlt komplett
                # im geladenen Datensatz). Ein Dock auf eine Platzhalter-Node
                # (von _DockView beim blossen Setzen ohne Existenzpruefung
                # angelegt, siehe scene_adapters.py) WIRD mitgespeichert und
                # ist damit strukturell gueltig, aber kein echtes Element der
                # aktuell aufgeloesten Buehne mehr -> ohne diesen Zusatz-Filter
                # wuerde ein geloeschtes Buehnen-Element nach dem Laden wieder
                # als Dock-Ziel auftauchen (test_stale_dock_discarded_on_load).
                valid_ids = _resolve_stage_element_ids(state.active_stage_name)
                if valid_ids is not None:
                    # Erst sammeln, dann reparenten (nicht waehrend der
                    # dict-Iteration mutieren).
                    stale_node_ids = [
                        n.id for n in new_scene._nodes.values()
                        if n.parent_id is not None and n.parent_id not in valid_ids
                    ]
                    for nid in stale_node_ids:
                        new_scene.reparent(nid, None, keep_world=True)
                # Geister-Platzhalter-Nodes (Review-Fix): reine Platzhalter, die
                # _DockView._ensure_parent_node bei einem Dock auf eine
                # (damals) unbekannte Stage-Element-ID angelegt hat, OHNE echte
                # Stage-Referenz UND ohne (mehr) verbleibende Kinder, raeumen
                # wir beim Laden auf -- sonst akkumulieren sie unbegrenzt ueber
                # wiederholte Save/Load-Zyklen in der .lshow.
                _prune_ghost_placeholder_nodes(new_scene)
                _replace_scene(state, new_scene)
            else:
                from src.core.stage.scene_graph import SceneGraph
                stage_def = _resolve_stage_definition(state.active_stage_name)
                # Die rohen, oben lokal gesammelten Legacy-dicts sind hier
                # FUEHREND (nicht state.visualizer_positions/live_view_positions
                # zurueckgelesen -- die werden erst NACH dem Graph-Aufbau als
                # Legacy-Properties gesetzt, s. Kommentar oben).
                new_scene = SceneGraph.from_legacy(
                    positions=positions,
                    rotations=rotations,
                    docks=docks,
                    active_stage_name=state.active_stage_name,
                    live_view_positions=lv_pos,
                    stage_def=stage_def,
                )
                _replace_scene(state, new_scene)
        except Exception as e:
            _lenient("load scene_graph error", e)

    # Legacy-Properties setzen. Fuer einen Adapter-State (state._scene
    # vorhanden, s.o.) ist der frisch gebaute Graph bereits die alleinige
    # Wahrheit -- die 5 Legacy-Felder LESEN live aus genau diesem Graphen
    # (Property-Getter, siehe app_state.py), ein redundanter Write wuerde
    # hier NICHT nur nichts bringen, sondern waere sogar SCHAEDLICH: ein
    # nachtraeglicher ``state.live_view_positions = lv_pos``-Write wuerde
    # ueber den bestehenden _LiveViewDict-Adapter die bereits korrekte 3D-X/Z-
    # Weltposition JEDER Fixture mit der aus dem 2D-Pixel-Raster abgeleiteten
    # Position ueberschreiben (Adapter kennt beim reinen dict-Write keine
    # Prioritaet "3D vor 2D") -- der Migrations-Algorithmus (Design (c))
    # verlangt aber positions als FUEHREND. Fake-States OHNE Adapter (kein
    # state._scene, z. B. tests/test_show_file.py::_FakeState) kennen die 5
    # Felder nur als plain-dict-Attribute OHNE Graph-Kopplung -- fuer die
    # bleibt dieser Write die einzige Schreibquelle.
    has_adapter = hasattr(state, "_scene")
    if visualizer_load_error is not None:
        _lenient("load visualizer error", visualizer_load_error)
        if not has_adapter:
            state.visualizer_positions = {}
            state.visualizer_rotations = {}
            state.visualizer_docks = {}
        state.active_stage_name = "simple"
    elif not has_adapter:
        state.visualizer_positions = positions
        state.visualizer_rotations = rotations
        state.visualizer_docks = docks

    if live_view_load_error is not None:
        _lenient("load live_view error", live_view_load_error)
        if not has_adapter:
            state.live_view_positions = {}
        state.live_view_meta = {}
    else:
        if not has_adapter:
            state.live_view_positions = lv_pos
        state.live_view_meta = live_view_meta

    # VIZ-13 Schritt 3b-K-2: plain-list-Attribut, kein SceneGraph-Adapter ->
    # unabhaengig von has_adapter immer direkt gesetzt (gleiches Muster wie
    # live_view_meta).
    state.visualizer_named_cameras = named_cameras
    state.visualizer_beams_off = beams_off

    try:
        state._last_loaded_layout = data.get("layout", {}) or {}
    except Exception as e:
        _lenient("layout store error", e)

    state.show_name = data.get("name", "Show")

    # Musik-Playlist (In-App-Player) — SSOT in state.playlist; MediaPlayer wird
    # ohne Audio-Backend gefüllt (lazy), die UI/VCSongInfo lesen daraus.
    try:
        state.playlist = data.get("playlist", []) or []
        from src.core.audio.media_player import get_media_player
        get_media_player().set_playlist_dicts(state.playlist)
    except Exception as e:
        _lenient("playlist load error", e)

    # Auto-Show an Musik koppeln (welche Funktionen beim Play starten).
    try:
        ma = data.get("music_autoshow") or {}
        slots = {}
        for k, v in (ma.get("slots") or {}).items():
            try:
                slots[int(k)] = str(v)
            except (TypeError, ValueError):
                pass
        state.music_autoshow = {
            "enabled": bool(ma.get("enabled", False)),
            "function_ids": [int(x) for x in (ma.get("function_ids") or [])],
            "bank": int(ma.get("bank", 0) or 0),
            "slots": slots,
        }
    except Exception as e:
        _lenient("music_autoshow load error", e)
        state.music_autoshow = {"enabled": False, "function_ids": [], "bank": 0, "slots": {}}

    # Notify listeners after full replacement
    try:
        state._emit("patch_changed", None)
        state._emit("stacks_changed", None)
        state._emit("cue_stack_changed", None)
        state._emit("show_loaded", {"path": os.fspath(path), "issues": []})
        state.sync.refresh_all()
    except Exception as e:
        print(f"[show_file] post-load events error: {e}")

    _undo_verlauf_leeren()           # STAB-29: auch was der Loader selbst gepusht hat
    # UI-69: das Laden selbst ist keine Aenderung. Hier auf dem Stand des
    # States; das Hauptfenster merkt nach dem Neuaufbau seiner Views erneut
    # (dessen VC-Layout kommt aus der Flaeche, nicht aus der Datei).
    merke_show_stand(state)

    # ★ QA-50: „geladen" nur sagen, wenn auch alles gelesen wurde. Sonst steht
    # die Zahl im Text — die Einzelheiten holt die UI ueber
    # `letzte_ladeprobleme()`. Der Rueckgabewert bleibt `True`: die Show IST
    # offen und bedienbar, nur eben unvollstaendig. Ein `False` hier wuerde die
    # Aufrufer dazu bringen, eine benutzbare Show als Fehlschlag zu behandeln.
    if _ladeprobleme:
        return True, (f"Show '{state.show_name}' geladen — ABER "
                      f"{len(_ladeprobleme)} Teile konnten nicht gelesen werden.")
    return True, f"Show '{state.show_name}' geladen."


def load_show(path: str | os.PathLike):
    """Load a .lshow file and replace app state. Returns (ok: bool, msg: str).

    OUT-60: der ganze Ladevorgang laeuft unter der Lade-Sperre des
    OutputManagers — die Ausgabe sendet bis zum Ende den Stand VOR dem Laden,
    statt mitten im reset-first einen Null-Frame zu rendern (am Rig ein Blitz).
    Danach rendert der naechste Frame die neue Show.
    """
    from src.core.app_state import get_state
    sperre = getattr(getattr(get_state(), "output_manager", None), "lade_sperre", None)
    if sperre is None:
        return _load_show_impl(path)
    with sperre():
        return _load_show_impl(path)
