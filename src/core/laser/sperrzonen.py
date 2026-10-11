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
Spitze im **Austrittsfenster** (:func:`feld_spitze` — dort, wo das 3D-Modell
das Fenster hat, nicht im Geraete-Mittelpunkt). Gerechnet wird mit Ebenen (Richtungen), nicht mit Winkeln in
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

#: Lage des Austrittsfensters vor dem Geraete-Ursprung, entlang der
#: Strahlachse (Meter). Dieselbe Zahl, mit der das 3D-Modell sein Strahlen-Rig
#: aufhaengt (``fixtures/builders.js``: ``buildLaserRig(group, 0.088)``) — per
#: Test aneinander gebunden. Dort sitzt die Spitze der Feld-Pyramide.
AUSTRITT_VORN_M = 0.088

#: Das 3D zeichnet die Strahlen eines Lasers als SCHEMA: fest um diesen Winkel
#: nach unten geneigt (``fixtures/laser.js``: ``LASER_PITCH = 0.06`` rad), damit
#: sie im Bild ueber die Koepfe laufen. Die Feld-Pyramide folgt dagegen der
#: Geraeteachse, von der aus die Randwinkel gemessen werden — sie ist das, womit
#: gerechnet wird. Der Unterschied ist kleiner als der Standard-Zuschlag
#: (:data:`ZUSCHLAG_STANDARD`); bei kleinerem Zuschlag und kleinem Randwinkel
#: „unten" kann das Strahlen-Schema im Bild knapp ausserhalb der Pyramide
#: liegen. Massgeblich ist die Pyramide.
STRAHLBILD_NEIGUNG_GRAD = math.degrees(0.06)

#: Kopfleiste des Hauptfensters (G10).
KOPFLEISTE_KEINE_ZONEN = "Laser gepatcht — keine Sperrzonen angelegt"
MELDUNG_SHOW_OHNE_ZONEN = ("Die vorige Show hatte Sperrzonen, diese hat keine "
                           "— Laser gepatcht, keine Sperrzonen angelegt")

HINWEIS_NUR_ANZEIGE = ("Nur Anzeige — schaltet den Laser NICHT ab "
                       "(am Gerät noch nicht abgenommen)")

#: LAS-35: die EINE Zeile, die im Planer dauernd sichtbar bleibt.
GRENZEN_KOMPAKT = ("Nur Anzeige — schaltet den Laser nicht ab. Kein Ersatz für "
                   "Blende, Abstände, Laserschutzbeauftragten.")

#: LAS-35: woher die Randwinkel eines Lasers stammen (Abschnitt
#: ``laser_felder``, Schluessel ``quelle``; fehlt er, ist nichts vermerkt).
QUELLE_PROFIL = "profil"
QUELLE_DATENBLATT = "datenblatt"
QUELLE_EINGEMESSEN = "eingemessen"
QUELLE_HAND = "hand"
QUELLEN = (QUELLE_PROFIL, QUELLE_DATENBLATT, QUELLE_EINGEMESSEN, QUELLE_HAND)

STATUS_ERREICHT = "erreicht"
STATUS_FREI = "frei"
STATUS_NICHT_PRUEFBAR = "nicht_pruefbar"
#: Nur fuer die Ampel je Zone (:func:`zonen_ampel`): es ist kein DMX-Laser da.
STATUS_KEIN_LASER = "kein_laser"


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
    angegeben) und der Sicherheitszuschlag.

    ``geraet`` bindet das Feld an das Geraet, fuer das es eingetragen wurde
    (:func:`geraete_kennung`: Hersteller, Modell, Modus). Die Geraete-Nummer
    allein reicht nicht: sie wird nach dem Loeschen neu vergeben, und ein
    anderer Laser auf derselben Nummer darf die Winkel nicht erben. Leer =
    ungebunden (Show aus einem Stand vor dieser Bindung)."""
    links: float | None = None
    rechts: float | None = None
    oben: float | None = None
    unten: float | None = None
    zuschlag: float = ZUSCHLAG_STANDARD
    geraet: str = ""
    #: LAS-35: Herkunft der Winkel (:data:`QUELLEN`, leer = nicht vermerkt)
    #: und der Tag dazu (``JJJJ-MM-TT``, nur beim Einmessen gesetzt).
    quelle: str = ""
    quelle_datum: str = ""

    def __post_init__(self):
        for r in RAENDER:
            setattr(self, r, _winkel_oder_none(getattr(self, r)))
        self.zuschlag = zuschlag_begrenzen(self.zuschlag)
        self.geraet = str(self.geraet or "")
        self.quelle = self.quelle if self.quelle in QUELLEN else ""
        datum = self.quelle_datum if isinstance(self.quelle_datum, str) else ""
        self.quelle_datum = datum if (self.quelle and _ist_datum(datum)) else ""

    def passt_zu(self, kennung) -> bool:
        """Gilt dieses Feld fuer das Geraet mit ``kennung``? Ungebunden (eine
        Seite leer/unbekannt) passt immer."""
        return not self.geraet or not kennung or self.geraet == str(kennung)

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
        if self.geraet:
            d["geraet"] = self.geraet
        # LAS-35: nur schreiben, was gesetzt ist — ein Feld ohne Herkunft sieht
        # in der Datei aus wie bisher.
        if self.quelle:
            d["quelle"] = self.quelle
        if self.quelle_datum:
            d["quelle_datum"] = self.quelle_datum
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LaserFeld":
        if not isinstance(d, dict):
            raise ValueError("Laser-Feld ist kein Objekt")
        return cls(links=d.get("links"), rechts=d.get("rechts"),
                   oben=d.get("oben"), unten=d.get("unten"),
                   zuschlag=d.get("zuschlag", ZUSCHLAG_STANDARD),
                   geraet=d.get("geraet") if isinstance(d.get("geraet"), str) else "",
                   quelle=d.get("quelle") if isinstance(d.get("quelle"), str) else "",
                   quelle_datum=d.get("quelle_datum", ""))


def _ist_datum(text) -> bool:
    try:
        import datetime
        datetime.date.fromisoformat(text)
        return len(text) == 10
    except (TypeError, ValueError):
        return False


def datum_deutsch(iso: str) -> str:
    """``2026-10-11`` -> ``11.10.2026`` (leer, wenn unlesbar)."""
    if not _ist_datum(iso):
        return ""
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def quelle_text(feld) -> str:
    """Woher die Randwinkel stammen, als Klartext fuer die Laser-Karte."""
    if feld is None or all(getattr(feld, r) is None for r in RAENDER):
        return "nicht angegeben"
    if feld.quelle == QUELLE_EINGEMESSEN:
        tag = datum_deutsch(feld.quelle_datum)
        return f"eingemessen am {tag}" if tag else "eingemessen"
    return {QUELLE_PROFIL: "Geräteprofil", QUELLE_DATENBLATT: "Datenblatt",
            QUELLE_HAND: "von Hand eingetragen"}.get(feld.quelle,
                                                     "Herkunft nicht vermerkt")


def geraete_kennung(fx) -> str:
    """Woran ein Laser-Feld sein Geraet wiedererkennt: Hersteller, Modell und
    Modus (klein geschrieben). Bewusst NICHT die Profil-Nummer der Datenbank —
    die ist je Rechner verschieden, die Show reist. Leer, wenn das Geraet
    nichts davon traegt (dann wird nicht gebunden)."""
    teile = [str(getattr(fx, n, "") or "").strip().lower()
             for n in ("manufacturer_name", "fixture_name", "mode_name")]
    return "|".join(teile) if any(teile[:2]) else ""


def feld_aus_gesamtwinkel(waagerecht, senkrecht) -> LaserFeld | None:
    """Datenblatt-Schnellweg: der VOLLE Abstrahlwinkel je Achse, je zur
    Haelfte auf die beiden Raender verteilt. Unbrauchbare Angabe -> ``None``."""
    h, v = _winkel_voll(waagerecht), _winkel_voll(senkrecht)
    if h is None or v is None:
        return None
    return LaserFeld(links=h / 2, rechts=h / 2, oben=v / 2, unten=v / 2)


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
        return feld_aus_gesamtwinkel(aw[0], aw[1])
    return feld_aus_gesamtwinkel(aw, aw)


def winkel_aus_bibliothek(hersteller, modell, verzeichnis=None) -> LaserFeld | None:
    """Das Feld, das die mitgelieferte Geraete-Bibliothek fuer dieses Modell
    belegt — oder ``None``. Gelesen wird die Profil-Datei selbst (Kopffelder
    ``laser_randwinkel`` / ``laser_abstrahlwinkel``); ein Profil traegt den
    Winkel nur, wenn er im Handbuch/Datenblatt steht. Jeder Fehler -> ``None``
    (dann fragt die Oberflaeche nach dem Datenblatt-Wert, statt zu raten)."""
    try:
        import os
        from src.core.database import bibliothek_format as B
        if not str(hersteller or "").strip() or not str(modell or "").strip():
            return None
        pfad = os.path.join(verzeichnis or B.BIBLIOTHEK_DIR,
                            B.dateiname(str(hersteller), str(modell)))
        if not os.path.isfile(pfad):
            return None
        return feld_aus_profil(B.lade_datei(pfad))
    except Exception:                                    # noqa: BLE001
        return None


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

    def feld(self, fid: int, kennung=None) -> LaserFeld:
        """Das Feld eines Lasers (ohne Eintrag: nichts angegeben).

        Mit ``kennung`` (:func:`geraete_kennung` des Geraets, das JETZT auf
        dieser Nummer sitzt): ein Feld, das fuer ein ANDERES Geraet eingetragen
        wurde, gilt als nicht angegeben — „nicht pruefbar", nie ein geerbtes
        „erreicht keine Zone"."""
        feld = self.laser_felder.get(int(fid))
        if feld is None or not feld.passt_zu(kennung):
            return LaserFeld()
        return feld

    def nimm_feld(self, fid: int):
        """Feld eines Lasers herausnehmen (Geraet geloescht). Rueckgabe: das
        Feld oder ``None`` — der Aufrufer hebt es fuer das Rueckgaengig auf."""
        return self.laser_felder.pop(int(fid), None)

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


def feld_spitze(pos, rot_deg):
    """Spitze der Feld-Pyramide: das Austrittsfenster, :data:`AUSTRITT_VORN_M`
    vor dem Geraete-Ursprung ``pos`` entlang der Strahlachse."""
    vorn, _rechts, _oben = geraete_achsen(rot_deg)
    return tuple(float(pos[i]) + AUSTRITT_VORN_M * vorn[i] for i in range(3))


def kann_erreichen(pos, rot_deg, feld: LaserFeld, zone: Sperrzone,
                   rand: float = ZONEN_RAND_M) -> bool:
    """Kann ein Laser, dessen AUSTRITTSFENSTER an ``pos`` sitzt
    (:func:`feld_spitze`), mit Montage-Drehung ``rot_deg`` und dem
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
    # Der Schnitt aus (nach vorn unbegrenzter) Pyramide und Quader ist
    # beschraenkt und konvex; liegt die Spitze ausserhalb des Quaders, hat er
    # deshalb immer einen Anteil an einer Quaderflaeche. Es reicht also, die
    # sechs Flaechen an den fuenf Ebenen zu beschneiden.
    return bool(_schnitt_polygone(spitze, ebenen, zone, rand, erstes_genuegt=True))


def _schnitt_polygone(spitze, ebenen, zone: Sperrzone, rand: float,
                      erstes_genuegt: bool = False) -> list:
    """Die Anteile der sechs Quaderflaechen, die im Feld liegen. DIE Rechnung
    hinter „erreicht": :func:`kann_erreichen` fragt, ob es einen gibt,
    :func:`erreichter_teil` zeichnet sie."""
    ecken = zonen_ecken(zone, rand)
    aus = []
    for flaeche in _FLAECHEN:
        polygon = [ecken[i] for i in flaeche]
        for n in ebenen:
            polygon = _schneide(polygon, spitze, n)
            if not polygon:
                break
        if polygon:
            aus.append(polygon)
            if erstes_genuegt:
                break
    return aus


# ── LAS-35: Umrisse fuer den Planer (Draufsicht x/z, Seitenansicht z/y) ─────

def huelle_2d(punkte) -> list:
    """Konvexe Huelle (gegen den Uhrzeigersinn), Andrew-Kette."""
    pts = sorted({(round(float(p[0]), 9), round(float(p[1]), 9)) for p in punkte})
    if len(pts) <= 2:
        return pts

    def _kreuz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    unten, oben = [], []
    for p in pts:
        while len(unten) >= 2 and _kreuz(unten[-2], unten[-1], p) <= 0:
            unten.pop()
        unten.append(p)
    for p in reversed(pts):
        while len(oben) >= 2 and _kreuz(oben[-2], oben[-1], p) <= 0:
            oben.pop()
        oben.append(p)
    return unten[:-1] + oben[:-1]


def flaeche_2d(polygon) -> float:
    n = len(polygon)
    if n < 3:
        return 0.0
    return abs(sum(polygon[i][0] * polygon[(i + 1) % n][1]
                   - polygon[(i + 1) % n][0] * polygon[i][1]
                   for i in range(n))) / 2.0


def _ansichten(punkte) -> dict:
    """3D-Punkte als zwei Umrisse: ``drauf`` = (x, z), ``seite`` = (z, y)."""
    return {"drauf": huelle_2d([(p[0], p[2]) for p in punkte]),
            "seite": huelle_2d([(p[2], p[1]) for p in punkte])}


def zonen_umriss(zone: Sperrzone, rand: float = 0.0) -> dict:
    """Die Zone in beiden Ansichten (``drauf``/``seite``)."""
    return _ansichten(zonen_ecken(zone, rand))


#: Kleiner als das ist kein zeichenbarer Fleck (Quadratmeter).
_FLECK_MIN_M2 = 1e-4


def erreichter_teil(pos, rot_deg, feld: LaserFeld, zone: Sperrzone,
                    rand: float = ZONEN_RAND_M):
    """Der Teil der Zone, den das Feld erreicht — als Umriss fuer Draufsicht
    und Seitenansicht (``{"drauf": [...], "seite": [...]}``), oder ``None``,
    wenn der Laser die Zone nicht erreicht.

    Dieselbe Entscheidung wie :func:`pruefe_laser` (gleiche Funktionen, gleiche
    Reihenfolge): sagt die Rechnung „erreicht", kommt hier IMMER ein Umriss
    zurueck. Ist der Schnitt zu duenn zum Zeichnen (das Feld streift nur eine
    Kante) oder sitzt nur das Geraet in der Zone, ist es die ganze Zone —
    lieber zu viel schraffiert als ein „frei" im Bild.

    Wirft ``ValueError`` bei fehlenden Randwinkeln/unlesbarer Position."""
    spitze = feld_spitze(pos, rot_deg)
    if not all(math.isfinite(v) for v in spitze):
        raise ValueError("Position unlesbar")
    ebenen = feld_ebenen(rot_deg, feld)
    punkte = [p for polygon in _schnitt_polygone(spitze, ebenen, zone, rand)
              for p in polygon]
    spitze_drin = punkt_in_zone(spitze, zone, rand)
    if not (punkte or spitze_drin or punkt_in_zone(pos, zone)):
        return None
    if spitze_drin:
        punkte.append(spitze)
    teil = _ansichten(punkte)
    ganz = zonen_umriss(zone, rand)
    for ansicht in ("drauf", "seite"):
        if flaeche_2d(teil[ansicht]) < _FLECK_MIN_M2:
            teil[ansicht] = ganz[ansicht]
    return teil


def feld_umriss(pos, rot_deg, feld: LaserFeld, laenge: float,
                mit_zuschlag: bool = True) -> dict:
    """Das Feld eines Lasers als Faecher in beiden Ansichten: Spitze im
    Austrittsfenster, die vier Kantenstrahlen ``laenge`` Meter weit (entlang
    der Geraeteachse gemessen). Nur Darstellung."""
    if not feld.vollstaendig:
        raise ValueError("Randwinkel fehlen")
    vorn, rechts, oben = geraete_achsen(rot_deg)
    spitze = feld_spitze(pos, rot_deg)
    z = zuschlag_begrenzen(feld.zuschlag) if mit_zuschlag else 0.0

    def _tan(winkel):
        return math.tan(math.radians(min(_WINKEL_GESAMT_MAX, winkel + z)))

    punkte = [spitze]
    for a in (_tan(feld.rechts), -_tan(feld.links)):
        for b in (_tan(feld.oben), -_tan(feld.unten)):
            punkte.append(tuple(
                spitze[i] + float(laenge) * (vorn[i] + a * rechts[i] + b * oben[i])
                for i in range(3)))
    return _ansichten(punkte)


# ── LAS-35: Vorlagen ────────────────────────────────────────────────────────

#: ``(kennung, Knopftext, Zonenname, breite, hoehe, tiefe)``
VORLAGEN = (
    ("publikum", "Publikum bis 3 m Höhe vor der Bühne", "Publikum", 10.0, 3.0, 6.0),
    ("technik", "Technik/FOH", "Technik", 3.0, 2.5, 2.0),
    ("gang", "Gang", "Gang", 1.5, 2.5, 6.0),
)
#: Abstand zwischen Buehnen-Vorderkante und Publikum bzw. Publikum und FOH.
_VORLAGE_LUECKE_M = 1.0


def freier_name(daten: "SperrzonenDaten", wunsch: str) -> str:
    vorhandene = {z.name for z in daten.zonen}
    name, n = wunsch, 2
    while name in vorhandene:
        name, n = f"{wunsch} {n}", n + 1
    return name


def vorlage_zone(kennung: str, daten: "SperrzonenDaten",
                 buehne_vorn_z: float = 2.0) -> Sperrzone:
    """Eine sinnvoll platzierte Zone zum Zurechtziehen. ``buehne_vorn_z`` =
    Vorderkante der Buehne (dahinter, Richtung ``+z``, steht das Publikum).

    Publikum: mittig vor der Buehne, Boden bis 3 m. Technik/FOH: mittig hinter
    der Publikumsflaeche. Gang: rechts neben der Publikumsflaeche."""
    eintrag = next((v for v in VORLAGEN if v[0] == kennung), None)
    if eintrag is None:
        raise ValueError(f"unbekannte Vorlage {kennung!r}")
    _k, _knopf, name, breite, hoehe, tiefe = eintrag
    pub = next(v for v in VORLAGEN if v[0] == "publikum")
    pub_vorn = float(buehne_vorn_z) + _VORLAGE_LUECKE_M
    x, z = 0.0, pub_vorn + tiefe / 2
    if kennung == "technik":
        z = pub_vorn + pub[5] + _VORLAGE_LUECKE_M + tiefe / 2
    elif kennung == "gang":
        x = pub[3] / 2 + breite / 2
    return Sperrzone(name=freier_name(daten, name), x=x, y=0.0, z=z,
                     breite=breite, hoehe=hoehe, tiefe=tiefe)


def zonen_ampel(laser, positionen, rotationen, daten: "SperrzonenDaten") -> dict:
    """Je Zone: ``{"status", "laser": [fid…], "ungeprueft": [fid…]}``.

    Gefragt wird :func:`pruefe_laser` — je Laser und Zone einzeln, also
    dieselbe Antwort wie die Meldung je Laser. „frei" gibt es nur, wenn JEDER
    Laser pruefbar war und keiner die Zone erreicht."""
    positionen, rotationen = positionen or {}, rotationen or {}
    ampel = {}
    for zone in daten.zonen:
        erreicht, ungeprueft = [], []
        for eintrag in laser:
            fid, name = int(eintrag[0]), eintrag[1]
            kennung = eintrag[2] if len(eintrag) > 2 else None
            b = pruefe_laser(fid, name, positionen.get(fid), rotationen.get(fid),
                             daten.feld(fid, kennung), [zone])
            if b.status == STATUS_ERREICHT:
                erreicht.append(fid)
            elif b.status == STATUS_NICHT_PRUEFBAR:
                ungeprueft.append(fid)
        if erreicht:
            status = STATUS_ERREICHT
        elif ungeprueft:
            status = STATUS_NICHT_PRUEFBAR
        elif not laser:
            status = STATUS_KEIN_LASER
        else:
            status = STATUS_FREI
        ampel[zone.id] = {"status": status, "laser": erreicht,
                          "ungeprueft": ungeprueft}
    return ampel


def ampel_text(eintrag: dict) -> str:
    status = eintrag.get("status")
    if status == STATUS_ERREICHT:
        return "erreicht von Laser " + ", ".join(str(f) for f in eintrag["laser"])
    if status == STATUS_NICHT_PRUEFBAR:
        return "nicht prüfbar (Laser " + ", ".join(
            str(f) for f in eintrag["ungeprueft"]) + ")"
    if status == STATUS_KEIN_LASER:
        return "kein Laser"
    return "frei"


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
        spitze = feld_spitze(pos, rot_deg)
        for zone in zonen:
            # Sitzt das GERAET in der Zone, gilt sie als erreicht — auch wenn
            # das Fenster gerade noch herausschaut.
            if punkt_in_zone(pos, zone) or kann_erreichen(spitze, rot_deg, feld, zone):
                erreicht.append(zone.name)
    except Exception:                                    # noqa: BLE001
        return LaserBefund(fid, name, STATUS_NICHT_PRUEFBAR,
                           grund="Rechnung fehlgeschlagen — nicht prüfbar")
    if erreicht:
        return LaserBefund(fid, name, STATUS_ERREICHT, zonen=erreicht)
    return LaserBefund(fid, name, STATUS_FREI)


def pruefe_alle(laser, positionen, rotationen, daten: SperrzonenDaten) -> list:
    """Befunde fuer alle Laser. ``laser`` = Folge von ``(fid, name)`` oder
    ``(fid, name, kennung)`` (:func:`dmx_laser_geraete`)."""
    befunde = []
    positionen = positionen or {}
    rotationen = rotationen or {}
    for eintrag in laser:
        fid, name = int(eintrag[0]), eintrag[1]
        kennung = eintrag[2] if len(eintrag) > 2 else None
        befunde.append(pruefe_laser(fid, name, positionen.get(fid),
                                    rotationen.get(fid), daten.feld(fid, kennung),
                                    daten.zonen))
    return befunde


def kopfleisten_hinweis(anzahl_laser: int, daten: SperrzonenDaten,
                        benutzt: bool) -> str:
    """Die gelbe Zeile in der Kopfleiste des Hauptfensters — oder leer.

    Sie steht nur da, wenn (a) ein DMX-Laser gepatcht ist, (b) die Show keine
    Zone hat und (c) auf diesem Rechner schon einmal mit Sperrzonen gearbeitet
    wurde (``benutzt``). Wer keinen Laser hat oder die Funktion nie angefasst
    hat, sieht nichts: die Sperrzonen sind eine reine Anzeige, ihr Fehlen
    nimmt niemandem etwas weg, der nie welche hatte — eine Dauerwarnung dort
    stumpft nur ab. Wer sie benutzt, verlaesst sich auf das Bild; fuer den ist
    eine Show ohne Zonen (z. B. eine aeltere, mitten am Abend geladen) genau
    der Zustand, der nicht still bleiben darf."""
    if anzahl_laser <= 0 or not benutzt:
        return ""
    if daten is None or daten.fremd is not None or daten.zonen:
        return ""
    return KOPFLEISTE_KEINE_ZONEN


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
    """``[(fid, name), ...]`` der gepatchten DMX-Laser."""
    return [(fid, name) for fid, name, _k in dmx_laser_geraete(state)]


def dmx_laser_geraete(state) -> list:
    """``[(fid, name, kennung), ...]`` der gepatchten DMX-Laser.

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
        laser.append((int(fx.fid), str(name), geraete_kennung(fx)))
    return laser


def state_befunde(state) -> tuple[str, list]:
    """``(kopfzeile, befunde)`` fuer den aktuellen Stand der Show (nur
    DMX-Laser, s. :func:`dmx_laser`)."""
    daten = getattr(state, "sperrzonen", None) or SperrzonenDaten()
    laser = dmx_laser_geraete(state)
    kopf = kopfzeile(len(laser), daten)
    if daten.fremd is not None or not daten.zonen:
        return kopf, []
    befunde = pruefe_alle(laser, getattr(state, "visualizer_positions", {}),
                          getattr(state, "visualizer_rotations", {}), daten)
    return kopf, befunde


#: Laenge, bis zu der das 3D das Feld hoechstens darstellt (Meter); der
#: Fussabdruck am Boden endet meist frueher und blendet aus. Nur Darstellung —
#: die Rechnung oben kennt keine Reichweiten-Grenze.
FELD_ANZEIGE_LAENGE_M = 25.0


def szenen_daten(state) -> dict:
    """Was der 3D-Visualizer zeichnet: alle Zonen und je DMX-Laser mit
    vollstaendigen Randwinkeln das Feld. Reine Anzeige-Daten.

    ``ungeprueft`` = Zahl der DMX-Laser OHNE vollstaendige Randwinkel. Solange
    es einen gibt, zeichnet das 3D keine Zone als „von keinem Laser erreicht"
    (blasser) — fuer den nicht pruefbaren Laser weiss das niemand."""
    daten = getattr(state, "sperrzonen", None) or SperrzonenDaten()
    if daten.fremd is not None:
        return {"zonen": [], "felder": [], "laenge": FELD_ANZEIGE_LAENGE_M,
                "ungeprueft": 0}
    felder = []
    ungeprueft = 0
    for fid, _name, kennung in dmx_laser_geraete(state):
        feld = daten.feld(fid, kennung)
        if feld.vollstaendig:
            eintrag = feld.to_dict()
            eintrag["fid"] = fid
            felder.append(eintrag)
        else:
            ungeprueft += 1
    return {"zonen": [z.to_dict() for z in daten.zonen], "felder": felder,
            "laenge": FELD_ANZEIGE_LAENGE_M, "ungeprueft": ungeprueft}
