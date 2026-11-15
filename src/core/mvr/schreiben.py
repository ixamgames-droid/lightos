"""VIZ-56 Teil 2: den Patch samt 3D-Lagen als ``.mvr`` schreiben.

Eine ``.mvr`` ist ein ZIP mit ``GeneralSceneDescription.xml`` und je
Geraetetyp einer eingebetteten ``.gdtf`` (:mod:`.gdtf_schreiben`). Was
geschrieben wird:

* ``GeneralSceneDescription verMajor="1" verMinor="5"``, darin EIN Layer
  „LightOS“ und je gepatchtem Geraet ein ``<Fixture>`` mit ``name``,
  ``uuid`` (UUID5 aus der Geraetenummer — stabil von Export zu Export),
  ``Matrix`` (mm, Z oben; Rueckrechnung :func:`.achsen.lightos_zu_mvr`),
  ``GDTFSpec``/``GDTFMode``, ``Addresses`` (absolute DMX-Adresse, break 0),
  ``FixtureID`` (= Geraetenummer) und ``UnitNumber``.
* Ein Geraet ohne Position im 3D steht am Ursprung; es wird im
  :class:`ExportErgebnis` genannt, damit die Meldung es sagen kann.
* Fehlt das Bibliotheksprofil eines Geraets, wird ein Ersatz-GDTF mit der
  Kanalzahl aus dem Patch geschrieben (alle Kanaele ``raw``) — das Geraet
  verschwindet nicht.

Die Ausgabe ist deterministisch: gleiche Show -> byte-gleiche XML und ZIP
(sortiert nach Geraetenummer, feste ZIP-Zeitstempel, feste Zahlenformate).
Fehler beim Schreiben kommen als :class:`~.sicher.MvrFehler` mit deutschem
Satz; eine halb geschriebene Datei bleibt nie liegen.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

from . import gdtf_schreiben as GS
from .achsen import lightos_zu_mvr
from .lesen import SZENE, UNIVERSUM_GROESSE
from .sicher import MvrFehler

VER_MAJOR, VER_MINOR = 1, 5
LAYER_NAME = "LightOS"


@dataclass(frozen=True)
class ExportGeraet:
    fid: int
    name: str
    profil_id: int | None
    hersteller: str
    modell: str
    modus: str
    kanalzahl: int
    universum: int
    adresse: int
    position: tuple[float, float, float] | None
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class ExportErgebnis:
    pfad: str = ""
    geraete: int = 0
    #: Namen der Geraete, die ohne Position (am Ursprung) exportiert wurden.
    ohne_position: list[str] = field(default_factory=list)
    #: Namen der Geraete, deren Bibliotheksprofil fehlte (Ersatz-GDTF).
    ohne_profil: list[str] = field(default_factory=list)
    #: Dateinamen der eingebetteten GDTF.
    gdtf: list[str] = field(default_factory=list)


def fixture_uuid(fid: int) -> str:
    return str(uuid.uuid5(GS.NAMENSRAUM, f"fixture:{int(fid)}")).upper()


def _layer_uuid() -> str:
    return str(uuid.uuid5(GS.NAMENSRAUM, "layer:1")).upper()


# ── Daten aus dem AppState ───────────────────────────────────────────────────

def geraete_aus_state(state) -> list[ExportGeraet]:
    from src.core.stage.coords import normalize_rotation
    positionen = dict(state.visualizer_positions)
    drehungen = dict(state.visualizer_rotations)
    aus = []
    for f in sorted(state.get_patched_fixtures(), key=lambda f: int(f.fid)):
        fid = int(f.fid)
        pos = positionen.get(fid)
        if pos is not None:
            try:
                pos = tuple(float(w) for w in pos)[:3]
                if len(pos) != 3:
                    pos = None
            except (TypeError, ValueError):
                pos = None
        aus.append(ExportGeraet(
            fid=fid, name=f.label or f"Gerät {fid}",
            profil_id=f.fixture_profile_id, hersteller=f.manufacturer_name or "",
            modell=f.fixture_name or "", modus=f.mode_name or "",
            kanalzahl=int(f.channel_count or 0), universum=int(f.universe or 1),
            adresse=int(f.address or 1), position=pos,
            rotation=normalize_rotation(drehungen.get(fid))))
    return aus


# ── Aufbau ───────────────────────────────────────────────────────────────────

def _profile_sammeln(geraete, lader) -> tuple[dict, dict, list[str]]:
    """Je Geraet: GDTF-Dateiname. Rueckgabe ``(fid -> datei,
    datei -> ProfilDaten, ohne_profil)``."""
    je_profil: dict = {}
    dateien: dict[str, GS.ProfilDaten] = {}
    zuordnung: dict[int, str] = {}
    ohne: list[str] = []
    for g in geraete:
        daten = None
        if g.profil_id is not None:
            if g.profil_id not in je_profil:
                je_profil[g.profil_id] = lader(g.profil_id)
            daten = je_profil[g.profil_id]
        if daten is None:
            ohne.append(g.name)
            schluessel = ("ersatz", g.hersteller, g.modell, g.modus, g.kanalzahl)
            if schluessel not in je_profil:
                je_profil[schluessel] = GS.ersatz_profil(g.hersteller, g.modell,
                                                         g.modus, g.kanalzahl)
            daten = je_profil[schluessel]
        name = next((n for n, d in dateien.items() if d is daten), None)
        if name is None:
            name = GS.dateiname(daten)
            if name in dateien:
                basis = name[:-5]
                i = 2
                while f"{basis}_{i}.gdtf" in dateien:
                    i += 1
                name = f"{basis}_{i}.gdtf"
            dateien[name] = daten
        zuordnung[g.fid] = name
    return zuordnung, dateien, ohne


def _modus_name(g: ExportGeraet, daten: GS.ProfilDaten) -> str:
    """Der Modusname, wie er in der GDTF steht (Ersatz: der aus dem Patch)."""
    namen = [m.name for m in daten.modi]
    if g.modus in namen:
        return g.modus
    lose = [n for n in namen if n.casefold() == g.modus.casefold()]
    if lose:
        return lose[0]
    passend = [m.name for m in daten.modi if m.kanalzahl == g.kanalzahl]
    return passend[0] if passend else g.modus


def szene_xml(geraete: list[ExportGeraet], zuordnung: dict[int, str],
              dateien: dict[str, GS.ProfilDaten]) -> bytes:
    z = ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
         f'<GeneralSceneDescription verMajor="{VER_MAJOR}" verMinor="{VER_MINOR}"'
         ' provider="LightOS" providerVersion="VIZ-56">',
         "<UserData/>", "<Scene>", "<AUXData/>", "<Layers>",
         f"<Layer name={quoteattr(LAYER_NAME)} uuid={quoteattr(_layer_uuid())}>",
         "<Matrix>{1,0,0}{0,1,0}{0,0,1}{0,0,0}</Matrix>", "<ChildList>"]
    for g in geraete:
        datei = zuordnung[g.fid]
        matrix = lightos_zu_mvr(g.position or (0.0, 0.0, 0.0), g.rotation)
        absolut = (g.universum - 1) * UNIVERSUM_GROESSE + g.adresse
        z += [f"<Fixture name={quoteattr(GS.xml_sauber(g.name))} "
              f"uuid={quoteattr(fixture_uuid(g.fid))}>",
              f"<Matrix>{matrix.als_text()}</Matrix>",
              f"<GDTFSpec>{escape(GS.xml_sauber(datei))}</GDTFSpec>",
              f"<GDTFMode>{escape(GS.xml_sauber(_modus_name(g, dateien[datei])))}"
              "</GDTFMode>",
              "<Addresses>", f'<Address break="0">{absolut}</Address>', "</Addresses>",
              f"<FixtureID>{g.fid}</FixtureID>",
              "<UnitNumber>0</UnitNumber>",
              "</Fixture>"]
    z += ["</ChildList>", "</Layer>", "</Layers>", "</Scene>",
          "</GeneralSceneDescription>"]
    return ("\n".join(z) + "\n").encode("utf-8")


def baue_mvr(geraete: list[ExportGeraet], lader=None) -> tuple[bytes, ExportErgebnis]:
    """Die ganze ``.mvr`` als Bytes. ``lader(profil_id) -> ProfilDaten|None``
    (Vorgabe: aus der Bibliothek)."""
    lader = lader or GS.profil_aus_db
    geraete = sorted(geraete, key=lambda g: g.fid)
    zuordnung, dateien, ohne = _profile_sammeln(geraete, lader)
    eintraege = [(SZENE, szene_xml(geraete, zuordnung, dateien))]
    for name in sorted(dateien):
        eintraege.append((name, GS.gdtf_bytes(dateien[name])))
    ergebnis = ExportErgebnis(
        geraete=len(geraete),
        ohne_position=[g.name for g in geraete if g.position is None],
        ohne_profil=ohne, gdtf=sorted(dateien))
    return GS.zip_bytes(eintraege), ergebnis


# ── Schreiben ────────────────────────────────────────────────────────────────

def atomar_schreiben(pfad: str, daten: bytes) -> None:
    """Erst in eine Zwischendatei im Zielordner, dann umbenennen — eine
    halbe Datei bleibt nie liegen. Fehler als :class:`MvrFehler`."""
    ordner = os.path.dirname(os.path.abspath(pfad)) or "."
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".lightos-export-", suffix=".tmp", dir=ordner)
        with os.fdopen(fd, "wb") as f:
            f.write(daten)
        os.replace(tmp, pfad)
        tmp = None
    except OSError as e:
        raise MvrFehler(f"Die Datei lässt sich nicht schreiben: "
                        f"{e.strerror or e}.") from None
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)
            except OSError:
                pass


def schreibe_mvr(state, pfad: str, lader=None) -> ExportErgebnis:
    """Den Patch von ``state`` samt Positionen/Drehungen nach ``pfad``
    schreiben. Wirft nur :class:`MvrFehler`."""
    try:
        daten, ergebnis = baue_mvr(geraete_aus_state(state), lader)
    except MvrFehler:
        raise
    except Exception as e:        # letzte Sicherung: nie ein Absturz
        raise MvrFehler(f"Der MVR-Export ist gescheitert ({type(e).__name__}: "
                        f"{e}).") from None
    atomar_schreiben(pfad, daten)
    ergebnis.pfad = pfad
    return ergebnis
