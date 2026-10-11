"""LAS-32 (Slice S1): Sperrzonen und Laser-Maximalfeld — NUR ANZEIGE.

Dieses Modul rechnet aus, ob das Feld, das ein Laser ueberhaupt erreichen
kann, eine im 3D angelegte Sperrzone beruehrt. Mehr nicht:

* Es schaltet **nichts** ab. Die DMX-Ausgabe kennt dieses Modul nicht; es wird
  weder vom ``OutputManager`` noch vom Render-Pfad importiert.
* Es ist **kein Laserschutz**. Die Rechnung kennt nur, was im 3D eingetragen
  wurde (Position, Drehung, vier Randwinkel). Steht das Geraet real anders,
  stimmt das Ergebnis nicht. Keine Spiegelungen, keine Abschattung.

Reines Rechen-/Datenmodul ohne Qt, damit es ohne geoeffnetes 3D-Fenster
laeuft und sich vollstaendig testen laesst.

Geometrie
---------
Welt wie im 3D-Visualizer: ``x`` rechts, ``y`` hoch, ``z`` nach vorn (Meter).
Das Geraet strahlt entlang seiner lokalen ``+Z``-Achse (so baut der Viewer den
Laser, ``fixtures/laser.js``); die Montage-Drehung ist ``visualizer_rotations``
(Euler XYZ in Grad, dieselbe Matrix wie ``stage/aim.py`` und three.js). Eine
haengende Montage ist damit einfach eine Drehung (z. B. ``rz = 180``).

Das Maximalfeld sind vier Randwinkel, gemessen von der Geraeteachse:
**links/rechts/oben/unten aus Sicht des Geraets in Strahlrichtung**. Sie
duerfen verschieden sein (per Blende begrenztes Feld). Rundum kommt der
Sicherheitszuschlag dazu. Das ergibt eine nach vorn offene Pyramide mit der
Spitze am Geraet. Gerechnet wird mit Ebenen (Richtungen), nicht mit Winkeln in
einer Bildebene — grosse Winkel verzerren so nicht.

Eine Zone ist ein Quader (um die Hochachse drehbar) mit festem Rand. Der Teil
einer Zone, der hinter dem Geraet liegt, zaehlt nicht (die Pyramide ist nach
hinten abgeschnitten): ein Laser ueber der Tanzflaeche hat das Publikum unter
und hinter sich, ohne dass er es deshalb erreicht.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field

from src.core.stage.aim import _mount_matrix
from src.core.stage.coords import normalize_rotation

#: Version des Abschnitts ``sperrzonen`` in der Show-Datei.
SPERRZONEN_VERSION = 1

#: Sicherheitszuschlag in Grad, rundum auf das Feld. Vorgabe, aenderbar.
ZUSCHLAG_STANDARD = 5.0
#: Kleinster einstellbarer Zuschlag — nie 0.
ZUSCHLAG_MIN = 2.0
ZUSCHLAG_MAX = 30.0
#: Groesster eintragbarer Randwinkel (von der Achse aus).
WINKEL_MAX = 85.0
#: Rand + Zuschlag bleiben unter 90 Grad — sonst gaebe es keine Pyramide mehr.
_WINKEL_GESAMT_MAX = 89.0
#: Fester Rand um jede Zone (Meter).
ZONEN_RAND_M = 0.10
#: Kleinstes Kantenmass einer Zone (Meter).
ZONE_MIN_M = 0.05

RAENDER = ("links", "rechts", "oben", "unten")

HINWEIS_NUR_ANZEIGE = ("Nur Anzeige — schaltet den Laser NICHT ab "
                       "(am Gerät noch nicht abgenommen)")

STATUS_ERREICHT = "erreicht"
STATUS_FREI = "frei"
STATUS_NICHT_PRUEFBAR = "nicht_pruefbar"


def _zahl(wert, default: float) -> float:
    try:
        z = float(wert)
    except (TypeError, ValueError):
        return default
    return z if math.isfinite(z) else default


def zuschlag_begrenzen(wert) -> float:
    """Zuschlag in den erlaubten Bereich holen. Unlesbar -> Standard; nie
    unter :data:`ZUSCHLAG_MIN`, also nie 0."""
    z = _zahl(wert, ZUSCHLAG_STANDARD)
    return min(ZUSCHLAG_MAX, max(ZUSCHLAG_MIN, z))


def _winkel_oder_none(wert):
    """Ein Randwinkel: Zahl in 0..WINKEL_MAX, sonst ``None`` (= nicht angegeben)."""
    if wert is None or isinstance(wert, bool):
        return None
    try:
        z = float(wert)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(z) or z < 0.0:
        return None
    return min(WINKEL_MAX, z)


@dataclass
class Sperrzone:
    """Quader. ``x``/``z`` = Mitte der Grundflaeche, ``y`` = Unterkante."""
    id: str = ""
    name: str = "Sperrzone"
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    breite: float = 4.0     # entlang x (vor der Drehung)
    hoehe: float = 3.0      # entlang y
    tiefe: float = 4.0      # entlang z (vor der Drehung)
    dreh_y: float = 0.0     # Grad um die Hochachse

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "x": float(self.x), "y": float(self.y), "z": float(self.z),
                "breite": float(self.breite), "hoehe": float(self.hoehe),
                "tiefe": float(self.tiefe), "dreh_y": float(self.dreh_y)}

    @classmethod
    def from_dict(cls, d: dict) -> "Sperrzone":
        if not isinstance(d, dict):
            raise ValueError("Sperrzone ist kein Objekt")
        return cls(
            id=str(d.get("id") or ""),
            name=str(d.get("name") or "Sperrzone"),
            x=_zahl(d.get("x"), 0.0), y=_zahl(d.get("y"), 0.0),
            z=_zahl(d.get("z"), 0.0),
            breite=max(ZONE_MIN_M, _zahl(d.get("breite"), 4.0)),
            hoehe=max(ZONE_MIN_M, _zahl(d.get("hoehe"), 3.0)),
            tiefe=max(ZONE_MIN_M, _zahl(d.get("tiefe"), 4.0)),
            dreh_y=_zahl(d.get("dreh_y"), 0.0),
        )


@dataclass
class LaserFeld:
    """Maximalfeld eines Lasers: vier Randwinkel in Grad (``None`` = nicht
    angegeben) und der Sicherheitszuschlag."""
    links: float | None = None
    rechts: float | None = None
    oben: float | None = None
    unten: float | None = None
    zuschlag: float = ZUSCHLAG_STANDARD

    def __post_init__(self):
        for r in RAENDER:
            setattr(self, r, _winkel_oder_none(getattr(self, r)))
        self.zuschlag = zuschlag_begrenzen(self.zuschlag)

    @property
    def vollstaendig(self) -> bool:
        return all(getattr(self, r) is not None for r in RAENDER)

    @property
    def leer(self) -> bool:
        return (all(getattr(self, r) is None for r in RAENDER)
                and self.zuschlag == ZUSCHLAG_STANDARD)

    def to_dict(self) -> dict:
        d = {r: getattr(self, r) for r in RAENDER}
        d["zuschlag"] = float(self.zuschlag)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LaserFeld":
        if not isinstance(d, dict):
            raise ValueError("Laser-Feld ist kein Objekt")
        return cls(links=d.get("links"), rechts=d.get("rechts"),
                   oben=d.get("oben"), unten=d.get("unten"),
                   zuschlag=d.get("zuschlag", ZUSCHLAG_STANDARD))


def feld_aus_profil(profil) -> LaserFeld | None:
    """Vorgabe fuer die Randwinkel aus einem Geraeteprofil — oder ``None``
    („nicht angegeben").

    Gelesen wird (als Attribut oder dict-Schluessel), was ein Profil dazu
    tragen kann: ``laser_randwinkel`` (``{"links":…, "rechts":…, "oben":…,
    "unten":…}``) oder ``laser_abstrahlwinkel`` — der volle Winkel laut
    Datenblatt, eine Zahl (beide Achsen) oder ``[waagrecht, senkrecht]``; er
    fuellt je Achse beide Raender mit der Haelfte. Steht nichts Brauchbares
    da, wird NICHT geraten.
    """
    def _lies(name):
        if isinstance(profil, dict):
            return profil.get(name)
        return getattr(profil, name, None)

    if profil is None:
        return None
    rw = _lies("laser_randwinkel")
    if isinstance(rw, dict):
        feld = LaserFeld(**{r: rw.get(r) for r in RAENDER})
        if feld.vollstaendig:
            return feld
    aw = _lies("laser_abstrahlwinkel")
    if isinstance(aw, (list, tuple)) and len(aw) == 2:
        h, v = _winkel_voll(aw[0]), _winkel_voll(aw[1])
    else:
        h = v = _winkel_voll(aw)
    if h is None or v is None:
        return None
    return LaserFeld(links=h / 2, rechts=h / 2, oben=v / 2, unten=v / 2)


def _winkel_voll(wert):
    if wert is None or isinstance(wert, bool):
        return None
    try:
        z = float(wert)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(z) or z <= 0.0 or z > 2 * WINKEL_MAX:
        return None
    return z


@dataclass
class SperrzonenDaten:
    """Alles, was der Abschnitt ``sperrzonen`` der Show-Datei traegt."""
    zonen: list = field(default_factory=list)
    laser_felder: dict = field(default_factory=dict)   # fid -> LaserFeld
    #: Abschnitt aus einem NEUEREN Programmstand, unveraendert aufgehoben:
    #: er wird nicht gedeutet (keine Anzeige daraus) und beim Speichern so
    #: zurueckgeschrieben, wie er kam.
    fremd: dict | None = None

    def ist_leer(self) -> bool:
        return (not self.zonen and self.fremd is None
                and all(f.leer for f in self.laser_felder.values()))

    def feld(self, fid: int) -> LaserFeld:
        """Das Feld eines Lasers (ohne Eintrag: nichts angegeben)."""
        return self.laser_felder.get(int(fid)) or LaserFeld()

    def setze_feld(self, fid: int, feld: LaserFeld) -> None:
        if feld.leer:
            self.laser_felder.pop(int(fid), None)
        else:
            self.laser_felder[int(fid)] = feld

    def zone(self, zid: str):
        for z in self.zonen:
            if z.id == zid:
                return z
        return None

    def to_dict(self) -> dict:
        if self.fremd is not None:
            return self.fremd
        return {
            "version": SPERRZONEN_VERSION,
            "zonen": [z.to_dict() for z in self.zonen],
            "laser_felder": {str(fid): f.to_dict()
                             for fid, f in sorted(self.laser_felder.items())
                             if not f.leer},
        }


def daten_aus_abschnitt(abschnitt) -> tuple[SperrzonenDaten, list[str]]:
    """Abschnitt ``sperrzonen`` einer Show lesen.

    Rueckgabe ``(daten, probleme)``. Fehlt der Abschnitt (Alt-Show), kommt ein
    leerer Bestand ohne Problem zurueck — es gibt dann schlicht keine Zonen,
    und die Anzeige sagt das auch so. Ein Abschnitt aus einem neueren
    Programmstand wird nicht gedeutet, sondern aufgehoben (``fremd``).
    """
    probleme: list[str] = []
    if abschnitt is None:
        return SperrzonenDaten(), probleme
    if not isinstance(abschnitt, dict):
        return SperrzonenDaten(), ["Sperrzonen: Abschnitt unlesbar — keine Zonen geladen"]
    try:
        version = int(abschnitt.get("version", 1))
    except (TypeError, ValueError):
        version = SPERRZONEN_VERSION + 1
    if version > SPERRZONEN_VERSION:
        return (SperrzonenDaten(fremd=abschnitt),
                [f"Sperrzonen: Abschnitt stammt aus einem neueren Programmstand "
                 f"(Version {abschnitt.get('version')!r}) — wird hier NICHT angezeigt"])
    daten = SperrzonenDaten()
    roh_zonen = abschnitt.get("zonen")
    if roh_zonen is not None and not isinstance(roh_zonen, list):
        probleme.append("Sperrzonen: Zonenliste unlesbar")
        roh_zonen = []
    gesehen: set[str] = set()
    for i, roh in enumerate(roh_zonen or []):
        try:
            zone = Sperrzone.from_dict(roh)
        except Exception as e:                           # noqa: BLE001
            probleme.append(f"Sperrzonen: Zone {i + 1} nicht lesbar ({e})")
            continue
        if zone.id in gesehen:
            zone.id = uuid.uuid4().hex[:12]
        gesehen.add(zone.id)
        daten.zonen.append(zone)
    roh_felder = abschnitt.get("laser_felder")
    if roh_felder is not None and not isinstance(roh_felder, dict):
        probleme.append("Sperrzonen: Laser-Felder unlesbar")
        roh_felder = {}
    for fid_roh, roh in (roh_felder or {}).items():
        try:
            daten.setze_feld(int(fid_roh), LaserFeld.from_dict(roh))
        except Exception as e:                           # noqa: BLE001
            probleme.append(f"Sperrzonen: Feld von Gerät {fid_roh} nicht lesbar ({e})")
    return daten, probleme


# ── Geometrie ────────────────────────────────────────────────────────────────

def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def geraete_achsen(rot_deg):
    """Welt-Richtungen ``(vorn, rechts, oben)`` eines Geraets mit Montage-
    Drehung ``rot_deg``. „rechts" ist rechts aus Sicht des Geraets in
    Strahlrichtung — bei ungedrehtem Geraet (Strahl nach +Z) also Welt ``-X``.
    """
    rx, ry, rz = normalize_rotation(rot_deg)
    R = _mount_matrix(rx, ry, rz)
    lokal_x = (R[0][0], R[1][0], R[2][0])
    oben = (R[0][1], R[1][1], R[2][1])
    vorn = (R[0][2], R[1][2], R[2][2])
    rechts = (-lokal_x[0], -lokal_x[1], -lokal_x[2])
    return vorn, rechts, oben


def feld_ebenen(rot_deg, feld: LaserFeld):
    """Die fuenf Ebenen der Feld-Pyramide als Normalen ``n`` (durch die
    Spitze): innen ist, wo ``n · (p - spitze) <= 0`` gilt. Zuschlag eingerechnet."""
    if not feld.vollstaendig:
        raise ValueError("Randwinkel fehlen")
    vorn, rechts, oben = geraete_achsen(rot_deg)
    z = zuschlag_begrenzen(feld.zuschlag)

    def _tan(winkel):
        return math.tan(math.radians(min(_WINKEL_GESAMT_MAX, winkel + z)))

    def _ebene(achse, vz, winkel):
        t = _tan(winkel)
        return tuple(vz * achse[i] - t * vorn[i] for i in range(3))

    return [
        # Nichts hinter dem Geraet. Folgt rechnerisch schon aus den beiden
        # Seitenebenen (ihre Summe ergibt genau diese Bedingung); ausdruecklich,
        # damit es nicht an der Winkelsumme haengt.
        tuple(-v for v in vorn),
        _ebene(rechts, 1.0, feld.rechts),
        _ebene(rechts, -1.0, feld.links),
        _ebene(oben, 1.0, feld.oben),
        _ebene(oben, -1.0, feld.unten),
    ]


def zonen_ecken(zone: Sperrzone, rand: float = ZONEN_RAND_M):
    """Die 8 Ecken des Quaders (mit Rand) in Weltkoordinaten.

    Reihenfolge: Index-Bit 0 = x, Bit 1 = y, Bit 2 = z (jeweils -/+)."""
    hb = max(ZONE_MIN_M, float(zone.breite)) / 2 + rand
    hh = max(ZONE_MIN_M, float(zone.hoehe)) / 2 + rand
    ht = max(ZONE_MIN_M, float(zone.tiefe)) / 2 + rand
    cx, cy, cz = float(zone.x), float(zone.y) + float(zone.hoehe) / 2, float(zone.z)
    w = math.radians(float(zone.dreh_y))
    c, s = math.cos(w), math.sin(w)
    ecken = []
    for i in range(8):
        lx = hb if i & 1 else -hb
        ly = hh if i & 2 else -hh
        lz = ht if i & 4 else -ht
        # Drehung um Y wie three.js (rotation.y): x' = c*x + s*z, z' = -s*x + c*z
        ecken.append((cx + c * lx + s * lz, cy + ly, cz - s * lx + c * lz))
    return ecken


_FLAECHEN = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
             (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))


def punkt_in_zone(p, zone: Sperrzone, rand: float = ZONEN_RAND_M) -> bool:
    w = math.radians(float(zone.dreh_y))
    c, s = math.cos(w), math.sin(w)
    dx = float(p[0]) - float(zone.x)
    dy = float(p[1]) - (float(zone.y) + float(zone.hoehe) / 2)
    dz = float(p[2]) - float(zone.z)
    lx = c * dx - s * dz
    lz = s * dx + c * dz
    return (abs(lx) <= float(zone.breite) / 2 + rand
            and abs(dy) <= float(zone.hoehe) / 2 + rand
            and abs(lz) <= float(zone.tiefe) / 2 + rand)


def _schneide(polygon, spitze, n):
    """Polygon am Halbraum ``n · (p - spitze) <= 0`` beschneiden."""
    if not polygon:
        return polygon
    aus = []
    abst = [_dot(n, (p[0] - spitze[0], p[1] - spitze[1], p[2] - spitze[2]))
            for p in polygon]
    anzahl = len(polygon)
    for i in range(anzahl):
        a, b = polygon[i], polygon[(i + 1) % anzahl]
        da, db = abst[i], abst[(i + 1) % anzahl]
        if da <= 0.0:
            aus.append(a)
        if (da < 0.0 < db) or (db < 0.0 < da):
            t = da / (da - db)
            aus.append((a[0] + t * (b[0] - a[0]),
                        a[1] + t * (b[1] - a[1]),
                        a[2] + t * (b[2] - a[2])))
    return aus


def kann_erreichen(pos, rot_deg, feld: LaserFeld, zone: Sperrzone,
                   rand: float = ZONEN_RAND_M) -> bool:
    """Kann ein Laser an ``pos`` mit Montage-Drehung ``rot_deg`` und dem
    Maximalfeld ``feld`` (plus Zuschlag) die Zone erreichen?

    Die Reichweite ist unbegrenzt gerechnet (ein Laserstrahl endet nicht nach
    ein paar Metern). Beruehren zaehlt als Erreichen. Der Teil der Zone hinter
    dem Geraet zaehlt nicht. Sitzt das Geraet IN der Zone, ist sie erreicht.

    Wirft ``ValueError``, wenn Randwinkel fehlen — der Aufrufer meldet das als
    „nicht pruefbar", nie als „erreicht keine Zone".
    """
    spitze = (float(pos[0]), float(pos[1]), float(pos[2]))
    if not all(math.isfinite(v) for v in spitze):
        raise ValueError("Position unlesbar")
    ebenen = feld_ebenen(rot_deg, feld)
    if punkt_in_zone(spitze, zone, rand):
        return True
    ecken = zonen_ecken(zone, rand)
    # Der Schnitt aus (nach vorn unbegrenzter) Pyramide und Quader ist
    # beschraenkt und konvex; liegt die Spitze ausserhalb des Quaders, hat er
    # deshalb immer einen Anteil an einer Quaderflaeche. Es reicht also, die
    # sechs Flaechen an den fuenf Ebenen zu beschneiden.
    for flaeche in _FLAECHEN:
        polygon = [ecken[i] for i in flaeche]
        for n in ebenen:
            polygon = _schneide(polygon, spitze, n)
            if not polygon:
                break
        if polygon:
            return True
    return False


# ── Befund je Laser ──────────────────────────────────────────────────────────

@dataclass
class LaserBefund:
    fid: int
    name: str
    status: str
    zonen: list = field(default_factory=list)   # Namen der erreichbaren Zonen
    grund: str = ""

    @property
    def text(self) -> str:
        kopf = f"Laser {self.fid}" + (f" „{self.name}“" if self.name else "")
        if self.status == STATUS_ERREICHT:
            namen = ", ".join(f"„{n}“" for n in self.zonen)
            wort = "Zone" if len(self.zonen) == 1 else "Zonen"
            return f"{kopf}: kann {wort} {namen} erreichen"
        if self.status == STATUS_FREI:
            return f"{kopf}: erreicht keine Zone"
        return f"{kopf}: {self.grund or 'nicht prüfbar'}"


def pruefe_laser(fid: int, name: str, pos, rot_deg, feld: LaserFeld,
                 zonen) -> LaserBefund:
    """Befund fuer EINEN Laser. Jede Unsicherheit heisst „nicht pruefbar" —
    nie „erreicht keine Zone"."""
    fid = int(fid)
    if feld is None or not feld.vollstaendig:
        return LaserBefund(fid, name, STATUS_NICHT_PRUEFBAR,
                           grund="Randwinkel fehlen — nicht prüfbar")
    if pos is None:
        return LaserBefund(fid, name, STATUS_NICHT_PRUEFBAR,
                           grund="im 3D nicht platziert — nicht prüfbar")
    erreicht = []
    try:
        for zone in zonen:
            if kann_erreichen(pos, rot_deg, feld, zone):
                erreicht.append(zone.name)
    except Exception:                                    # noqa: BLE001
        return LaserBefund(fid, name, STATUS_NICHT_PRUEFBAR,
                           grund="Rechnung fehlgeschlagen — nicht prüfbar")
    if erreicht:
        return LaserBefund(fid, name, STATUS_ERREICHT, zonen=erreicht)
    return LaserBefund(fid, name, STATUS_FREI)


def pruefe_alle(laser, positionen, rotationen, daten: SperrzonenDaten) -> list:
    """Befunde fuer alle Laser. ``laser`` = Folge von ``(fid, name)``."""
    befunde = []
    positionen = positionen or {}
    rotationen = rotationen or {}
    for fid, name in laser:
        fid = int(fid)
        befunde.append(pruefe_laser(fid, name, positionen.get(fid),
                                    rotationen.get(fid), daten.feld(fid),
                                    daten.zonen))
    return befunde


def kopfzeile(anzahl_laser: int, daten: SperrzonenDaten) -> str:
    """Die eine Zeile ueber den Befunden. Leer, wenn es nichts zu sagen gibt
    (kein DMX-Laser gepatcht)."""
    if daten.fremd is not None:
        return ("Sperrzonen dieser Show stammen aus einem neueren Programmstand "
                "— hier keine Anzeige")
    if anzahl_laser <= 0:
        return ""
    if not daten.zonen:
        return "Laser gepatcht, keine Sperrzonen angelegt"
    return f"Sperrzonen: {len(daten.zonen)} — {HINWEIS_NUR_ANZEIGE}"


def dmx_laser(state) -> list:
    """``[(fid, name), ...]`` der gepatchten DMX-Laser.

    Netzwerk-Laser (Ether Dream/IDN) senden ihren eigenen Punktstrom und sind
    nicht Teil dieser Anzeige.
    """
    from src.core.laser.capability import LaserClass, laser_capability
    laser = []
    for fx in state.get_patched_fixtures():
        try:
            cap = laser_capability(fx)
        except Exception:                                # noqa: BLE001
            cap = None
        if cap is None or cap.laser_class == LaserClass.NET_STREAM:
            continue
        name = (getattr(fx, "label", "") or getattr(fx, "fixture_name", "") or "")
        laser.append((int(fx.fid), str(name)))
    return laser


def state_befunde(state) -> tuple[str, list]:
    """``(kopfzeile, befunde)`` fuer den aktuellen Stand der Show (nur
    DMX-Laser, s. :func:`dmx_laser`)."""
    daten = getattr(state, "sperrzonen", None) or SperrzonenDaten()
    laser = dmx_laser(state)
    kopf = kopfzeile(len(laser), daten)
    if daten.fremd is not None or not daten.zonen:
        return kopf, []
    befunde = pruefe_alle(laser, getattr(state, "visualizer_positions", {}),
                          getattr(state, "visualizer_rotations", {}), daten)
    return kopf, befunde


#: Laenge der im 3D gezeichneten Feld-Pyramide (Meter). Nur Darstellung — die
#: Rechnung oben kennt keine Reichweiten-Grenze.
FELD_ANZEIGE_LAENGE_M = 25.0


def szenen_daten(state) -> dict:
    """Was der 3D-Visualizer zeichnet: alle Zonen und je DMX-Laser mit
    vollstaendigen Randwinkeln das Feld. Reine Anzeige-Daten."""
    daten = getattr(state, "sperrzonen", None) or SperrzonenDaten()
    if daten.fremd is not None:
        return {"zonen": [], "felder": [], "laenge": FELD_ANZEIGE_LAENGE_M}
    felder = []
    for fid, _name in dmx_laser(state):
        feld = daten.feld(fid)
        if feld.vollstaendig:
            eintrag = feld.to_dict()
            eintrag["fid"] = fid
            felder.append(eintrag)
    return {"zonen": [z.to_dict() for z in daten.zonen], "felder": felder,
            "laenge": FELD_ANZEIGE_LAENGE_M}
