"""FM-80: LED-Matrix-Assistent — die Rechnung hinter dem Dialog.

Aus wenigen Angaben (Pixel Breite x Hoehe, Flaeche in cm, Bauform,
Kanalformat je Pixel, Verdrahtung, Startecke) entsteht ein NORMALES
Bibliotheks-Profil: ``fixture_type='matrix'``, je Modus ``grid_rows``/
``grid_cols``, je Pixel eine Kopf-Bank (``color_r`` … in Kanalreihenfolge des
Formats). Gepatcht, als Auto-Kopf-Gruppe (FM-21) gerastert und im 3D gezeigt
wird es ueber die vorhandenen Wege — hier entsteht nur das Profil und die
Lage der Teile.

★ **Universen-Aufteilung — warum mehrere Geraete-TEILE (ein Modus je Teil).**
Ein gepatchtes Geraet hat in LightOS genau EIN Universum und eine Startadresse
(``PatchedFixture.universe``/``address``/``channel_count``); jede Ausgabe- und
Render-Stelle klemmt auf 1..512. Eine Mehr-Universen-Mechanik fuer EIN Geraet
gibt es nicht — sie nachzuruesten hiesse, jeden Adress-Pfad anzufassen. Die
einfachste korrekte Loesung ist deshalb: die Matrix wird in ganze ZEILEN-
Streifen geteilt, jeder Streifen passt in ein Universum und ist ein eigener
Modus des einen Profils („Teil 1/5 · Zeilen 1–8“). Beim Patchen wird je Teil
ein Geraet in ein eigenes Universum gelegt (:func:`matrix_patchen`).

Warum ganze Zeilen und nicht „170 Pixel je Universum, egal wo die Zeile
endet“: so bleibt jeder Teil ein RECHTECK — ``grid_rows x grid_cols`` stimmt,
``place_element``/``head_matrix_layout`` (FM-21) rastern ihn ohne Sonderfall,
und das 3D-Panel zeigt ihn richtig. Der Preis sind ungenutzte Kanaele am Ende
eines Universums (20 Pixel breit, RGB: 480 von 512). Ein Pixel wird so nie
ueber eine Universumsgrenze geteilt. Am Pixel-Controller muss dieselbe Zahl
Pixel je Universum eingestellt sein — der Dialog nennt sie.

★ Master-Dimmer/Strobe stehen VORN in JEDEM Teil: jeder Teil ist ein eigenes
Geraet mit eigener Helligkeit. Der Master startet auf 0 (wie jeder Dimmer —
Farbe zieht den Dimmer nie automatisch mit).

★ Wo die Pixel physisch sitzen, sagt — wie bisher — das gepatchte Geraet
(``pixel_order``, ``element_rotation``, ``element_flip``). Der Assistent
rechnet Verdrahtung und Startecke in diese drei Felder um
(:func:`teil_lage`), je Teil: bei Schlangenlinie und ungerader Zeilenzahl je
Teil beginnt der naechste Teil in der Gegenrichtung.

Die Angaben selbst stehen als JSON im Profil (``FixtureProfile.matrix_angaben``),
damit der Assistent ein Profil spaeter wieder oeffnen kann; die Bauform steht
zusaetzlich in einer eigenen Spalte (``FixtureProfile.bauform``), die das 3D
(VIZ-114) liest — :func:`bauform_von`.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

DMX_KANAELE = 512

#: Bauformen (VIZ-114 baut daraus das 3D-Modell). Bestand = ``panel``.
BAUFORMEN = ("panel", "vorhang", "leiste", "ring", "saeule")
BAUFORM_STANDARD = "panel"
BAUFORM_TEXT = {
    "panel": "Panel / Kachel",
    "vorhang": "LED-Vorhang",
    "leiste": "Pixel-Leiste / Stab",
    "ring": "Ring",
    "saeule": "Säule / Zylinder",
}

#: Kanalformat je Pixel -> Attribute in Kanalreihenfolge.
FORMATE = {
    "RGB": ("color_r", "color_g", "color_b"),
    "GRB": ("color_g", "color_r", "color_b"),
    "BGR": ("color_b", "color_g", "color_r"),
    "RGBW": ("color_r", "color_g", "color_b", "color_w"),
    "GRBW": ("color_g", "color_r", "color_b", "color_w"),
}
FARB_NAME = {"color_r": "Rot", "color_g": "Grün", "color_b": "Blau",
             "color_w": "Weiß"}

VERDRAHTUNGEN = ("zeilenweise", "schlange")
VERDRAHTUNG_TEXT = {
    "zeilenweise": "Zeilenweise (jede Zeile gleiche Richtung)",
    "schlange": "Schlangenlinie (jede 2. Zeile rückwärts)",
}
STARTECKEN = ("oben_links", "oben_rechts", "unten_links", "unten_rechts")
STARTECKE_TEXT = {
    "oben_links": "oben links", "oben_rechts": "oben rechts",
    "unten_links": "unten links", "unten_rechts": "unten rechts",
}

#: Obergrenzen der Eingabe (Pixel je Seite, Teile je Matrix).
PIXEL_MAX = 512
TEILE_MAX = 64
FLAECHE_MAX_CM = 10000.0
ANGABEN_VERSION = 1


@dataclass
class MatrixAngaben:
    """Alles, was der Assistent fragt."""
    hersteller: str = "Eigenbau"
    modell: str = "LED-Matrix"
    breite_px: int = 20
    hoehe_px: int = 40
    breite_cm: float = 30.0
    hoehe_cm: float = 50.0
    bauform: str = BAUFORM_STANDARD
    format: str = "RGB"
    master: bool = False
    strobe: bool = False
    verdrahtung: str = "zeilenweise"
    startecke: str = "oben_links"
    #: 0 = so viele Zeilen je Universum wie hineinpassen.
    zeilen_je_teil: int = 0

    # ── abgeleitete Groessen ────────────────────────────────────────────
    def kopf_kanaele(self) -> int:
        return int(bool(self.master)) + int(bool(self.strobe))

    def kanaele_je_pixel(self) -> int:
        return len(FORMATE.get(self.format, FORMATE["RGB"]))

    def pixel_je_universum(self) -> int:
        return max(0, (DMX_KANAELE - self.kopf_kanaele()) // self.kanaele_je_pixel())

    def zeilen_max(self) -> int:
        """Wie viele ganze Zeilen hoechstens in ein Universum passen."""
        b = max(1, int(self.breite_px))
        return self.pixel_je_universum() // b

    def zeilen_teil(self) -> int:
        """Tatsaechliche Zeilen je Teil (Wunsch, auf das Moegliche geklemmt)."""
        zmax = min(self.zeilen_max(), max(1, int(self.hoehe_px)))
        wunsch = int(self.zeilen_je_teil or 0)
        return zmax if wunsch <= 0 else max(1, min(wunsch, zmax))

    def pixelabstand_mm(self) -> tuple[float, float]:
        """(waagerecht, senkrecht) Mitte-zu-Mitte in mm; 0 = keine Flaeche."""
        b = max(1, int(self.breite_px))
        h = max(1, int(self.hoehe_px))
        return (round(float(self.breite_cm or 0) * 10.0 / b, 2),
                round(float(self.hoehe_cm or 0) * 10.0 / h, 2))

    # ── Pruefung ────────────────────────────────────────────────────────
    def fehler(self) -> list[str]:
        out: list[str] = []
        if not (self.hersteller or "").strip():
            out.append("Hersteller fehlt.")
        if not (self.modell or "").strip():
            out.append("Modellname fehlt.")
        for name, v in (("Breite", self.breite_px), ("Höhe", self.hoehe_px)):
            if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= PIXEL_MAX:
                out.append(f"{name} in Pixeln: 1 bis {PIXEL_MAX}.")
        for name, v in (("Breite", self.breite_cm), ("Höhe", self.hoehe_cm)):
            try:
                f = float(v)
            except (TypeError, ValueError):
                f = -1.0
            if not 0.0 <= f <= FLAECHE_MAX_CM:
                out.append(f"{name} in cm: 0 bis {FLAECHE_MAX_CM:g}.")
        if self.bauform not in BAUFORMEN:
            out.append(f"Bauform unbekannt: {self.bauform!r}.")
        if self.format not in FORMATE:
            out.append(f"Kanalformat unbekannt: {self.format!r}.")
        if self.verdrahtung not in VERDRAHTUNGEN:
            out.append(f"Verdrahtung unbekannt: {self.verdrahtung!r}.")
        if self.startecke not in STARTECKEN:
            out.append(f"Startecke unbekannt: {self.startecke!r}.")
        if out:
            return out
        if self.zeilen_max() < 1:
            out.append(
                f"Eine Zeile mit {self.breite_px} Pixeln braucht "
                f"{self.breite_px * self.kanaele_je_pixel() + self.kopf_kanaele()} "
                f"Kanäle — mehr als ein Universum ({DMX_KANAELE}). Höchstens "
                f"{self.pixel_je_universum()} Pixel je Zeile; breitere Matrizen "
                "hochkant anlegen (Breite und Höhe tauschen, Montage 90°).")
        elif len(teile(self)) > TEILE_MAX:
            out.append(f"Mehr als {TEILE_MAX} Universen — bitte kleiner anlegen.")
        return out

    # ── JSON ────────────────────────────────────────────────────────────
    def als_json(self) -> str:
        d = asdict(self)
        d.pop("hersteller", None)
        d.pop("modell", None)
        d["version"] = ANGABEN_VERSION
        return json.dumps(d, ensure_ascii=False, sort_keys=True)


@dataclass
class Teil:
    """Ein Universums-Teil der Matrix = ein Modus = ein gepatchtes Geraet."""
    index: int              # 0-basiert, in Verdrahtungsreihenfolge
    anzahl: int             # Teile insgesamt
    zeilen: int             # Zeilen dieses Teils
    erste_zeile: int        # 0-basiert, in Verdrahtungsreihenfolge
    erstes_pixel: int       # 0-basiert, globale Pixelnummer
    kanaele: int
    name: str = ""
    attribute: list = field(default_factory=list)


def teile(a: MatrixAngaben) -> list[Teil]:
    """Die Universums-Teile der Matrix (leer, wenn keine Zeile passt)."""
    zt = a.zeilen_teil()
    if zt < 1:
        return []
    b, h = int(a.breite_px), int(a.hoehe_px)
    n = math.ceil(h / zt)
    out = []
    for k in range(n):
        z0 = k * zt
        zk = min(zt, h - z0)
        kanaele = a.kopf_kanaele() + zk * b * a.kanaele_je_pixel()
        if n == 1:
            name = f"{b}×{h} {a.format} ({kanaele} Kanäle)"
        else:
            name = (f"Teil {k + 1}/{n} · Zeilen {z0 + 1}–{z0 + zk} "
                    f"({kanaele} Kanäle)")
        out.append(Teil(k, n, zk, z0, z0 * b, kanaele, name))
    return out


def kanaele_fuer_teil(a: MatrixAngaben, t: Teil) -> list[dict]:
    """Kanalliste eines Teils als Payload-Kanaele (1-basiert nummeriert).
    Pixel sind global 1-basiert benannt (``P161 Rot``) — in
    Verdrahtungsreihenfolge, also so, wie der Controller sie zaehlt."""
    ch: list[dict] = []

    def neu(name, attr, default=0, highlight=255, ranges=None):
        ch.append({"channel_number": len(ch) + 1, "name": name,
                   "attribute": attr, "default_value": default,
                   "highlight_value": highlight, "ranges": ranges or []})

    if a.master:
        neu("Master-Dimmer", "intensity", 0, 255)
    if a.strobe:
        neu("Strobe", "strobe", 0, 0, [
            {"range_from": 0, "range_to": 9, "name": "Offen", "kind": "open"},
            {"range_from": 10, "range_to": 255,
             "name": "Strobe langsam → schnell", "kind": "strobe"}])
    attrs = FORMATE[a.format]
    for p in range(t.erstes_pixel, t.erstes_pixel + t.zeilen * int(a.breite_px)):
        for attr in attrs:
            neu(f"P{p + 1} {FARB_NAME[attr]}", attr, 0, 255)
    return ch


def kurzname(a: MatrixAngaben) -> str:
    return f"MATRIX{a.breite_px}X{a.hoehe_px}{a.format}"[:40]


def profil_payload(a: MatrixAngaben) -> dict:
    """Generator-Payload (``fixture_db.create_user_profile``/
    ``update_user_profile``) fuer die Matrix. Wirft ``ValueError`` bei
    ungueltigen Angaben."""
    fehler = a.fehler()
    if fehler:
        raise ValueError(" ".join(fehler))
    pb, ph = a.pixelabstand_mm()
    modi = []
    for t in teile(a):
        kan = kanaele_fuer_teil(a, t)
        modi.append({"name": t.name, "channel_count": len(kan),
                     "grid_rows": t.zeilen, "grid_cols": int(a.breite_px),
                     "channels": kan})
    notiz = (f"LED-Matrix-Assistent (FM-80): {a.breite_px}×{a.hoehe_px} Pixel "
             f"{a.format}, {a.breite_cm:g}×{a.hoehe_cm:g} cm "
             f"(Pixelabstand {pb:g}×{ph:g} mm), Bauform "
             f"{BAUFORM_TEXT[a.bauform]}, {len(modi)} Universum/Universen à "
             f"{a.zeilen_teil()} Zeilen.")
    return {
        "manufacturer": a.hersteller.strip(),
        "short_mfr": a.hersteller.strip()[:8].upper() or "EIGEN",
        "name": a.modell.strip(),
        "short_name": kurzname(a),
        "fixture_type": "matrix",
        "power_w": 0,
        "notes": notiz,
        "source": "user",
        "bauform": a.bauform,
        "matrix_angaben": a.als_json(),
        "modes": modi,
    }


# ── Lesen aus dem Profil ────────────────────────────────────────────────────

def normalize_bauform(value) -> str:
    """Beliebige Eingabe -> gueltige Bauform; Leeres/Unbekanntes = ``panel``
    (jedes Profil vor FM-80 ist ein Panel). Nie werfen."""
    v = str(value or "").strip().lower()
    return v if v in BAUFORMEN else BAUFORM_STANDARD


def bauform_von(profil) -> str:
    """Bauform eines Profils (``FixtureProfile`` oder Objekt mit ``bauform``)."""
    return normalize_bauform(getattr(profil, "bauform", "") if profil is not None else "")


def angaben_aus_json(text, hersteller: str = "", modell: str = "") -> MatrixAngaben | None:
    """``FixtureProfile.matrix_angaben`` -> :class:`MatrixAngaben` oder
    ``None`` (leer/kaputt = kein Assistenten-Profil). Unbekannte Schluessel
    werden ignoriert, fehlende bekommen den Vorgabewert."""
    if not text:
        return None
    try:
        d = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    a = MatrixAngaben()
    for k in ("breite_px", "hoehe_px", "zeilen_je_teil"):
        try:
            setattr(a, k, int(d.get(k, getattr(a, k))))
        except (TypeError, ValueError):
            pass
    for k in ("breite_cm", "hoehe_cm"):
        try:
            setattr(a, k, float(d.get(k, getattr(a, k))))
        except (TypeError, ValueError):
            pass
    for k in ("master", "strobe"):
        setattr(a, k, bool(d.get(k, getattr(a, k))))
    a.bauform = normalize_bauform(d.get("bauform"))
    for k, erlaubt in (("format", FORMATE), ("verdrahtung", VERDRAHTUNGEN),
                       ("startecke", STARTECKEN)):
        v = d.get(k)
        if v in erlaubt:
            setattr(a, k, v)
    if hersteller:
        a.hersteller = hersteller
    if modell:
        a.modell = modell
    return a


def angaben_von_profil(profil) -> MatrixAngaben | None:
    """Angaben eines gespeicherten Profils (``None`` = nicht vom Assistenten)."""
    if profil is None:
        return None
    a = angaben_aus_json(getattr(profil, "matrix_angaben", "") or "",
                         getattr(getattr(profil, "manufacturer", None), "name", "") or "",
                         getattr(profil, "name", "") or "")
    if a is not None:
        a.bauform = bauform_von(profil)
    return a


def masse_von(profil) -> tuple[float, float] | None:
    """(Breite, Hoehe) in cm aus einem Assistenten-Profil, sonst ``None``."""
    a = angaben_aus_json(getattr(profil, "matrix_angaben", "") or "")
    if a is None or not (a.breite_cm > 0 and a.hoehe_cm > 0):
        return None
    return float(a.breite_cm), float(a.hoehe_cm)


# ── Lage der Teile: Verdrahtung/Startecke -> Patch-Felder ───────────────────

def teil_lage(a: MatrixAngaben, t: Teil) -> tuple[str, int, bool]:
    """``(pixel_order, element_rotation, element_flip)`` fuer das gepatchte
    Geraet von Teil ``t`` — ausgedrueckt in den vorhandenen Feldern, die
    ``place_element`` liest (FM-13/ORIENT).

    * Startecke oben rechts = waagerecht gespiegelt; unten rechts = 180°;
      unten links = 180° + gespiegelt.
    * Schlangenlinie: beginnt der Teil auf einer (global) ungeraden Zeile,
      laeuft seine erste Zeile rueckwaerts -> Spiegelung umschalten. Das
      vertraegt sich mit der 180°-Drehung, weil beide nur die Spalten
      spiegeln bzw. waagerechtes Spiegeln mit 180° vertauschbar ist.
    """
    order = "serpentine" if a.verdrahtung == "schlange" else "rowwise"
    drehung = 180 if a.startecke.startswith("unten") else 0
    flip = a.startecke in ("oben_rechts", "unten_links")
    if order == "serpentine" and t.erste_zeile % 2 == 1:
        flip = not flip
    return order, drehung, flip


def teil_anzeige_zeile(a: MatrixAngaben, t: Teil) -> int:
    """Oberste ANZEIGE-Zeile (0 = oben) des Teils in der ganzen Matrix."""
    if a.startecke.startswith("unten"):
        return int(a.hoehe_px) - t.erste_zeile - t.zeilen
    return t.erste_zeile


def pixel_platz(a: MatrixAngaben, pixel: int) -> tuple[int, int]:
    """Globale Pixelnummer (0-basiert, Verdrahtungsreihenfolge) ->
    ``(zeile, spalte)`` in der Anzeige (0,0 = oben links). Fuer die Vorschau
    im Dialog — ueber dieselben Bausteine wie das gepatchte Geraet."""
    from src.core.pixel_order import place_element
    b = int(a.breite_px)
    for t in teile(a):
        lokal = pixel - t.erstes_pixel
        if 0 <= lokal < t.zeilen * b:
            order, drehung, flip = teil_lage(a, t)
            r, c, _nr, _nc = place_element(lokal, b, t.zeilen, order, drehung, flip)
            return teil_anzeige_zeile(a, t) + r, c
    raise IndexError(pixel)


# ── Patchen: je Teil ein Geraet, je Teil ein Universum ──────────────────────

def matrix_patchen(state, profil_id: int, start_universum: int = 1,
                   adresse: int = 1, label: str = "", *,
                   gesamt_gruppe: bool = True, engine=None) -> list[int]:
    """Patcht ALLE Teile eines Assistenten-Profils: Teil k in Universum
    ``start_universum + k`` ab ``adresse``, mit Pixel-Reihenfolge/Montage aus
    :func:`teil_lage`. Jeder Teil bekommt seine Auto-Kopf-Gruppe (FM-21) wie
    jedes Panel; bei mehreren Teilen zusaetzlich EINE Gruppe ueber die ganze
    Matrix (``… · Matrix``), damit ein Effekt ueber alle Pixel laufen kann.

    Prueft vorher alles (Teil passt ins Universum, keine Adresskonflikte) und
    patcht dann entweder alles oder nichts (``ValueError`` mit Begruendung).
    Gibt die neuen fids zurueck."""
    from sqlalchemy.orm import Session
    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureProfile, PatchedFixture

    eng = engine if engine is not None else fdb.engine()
    with Session(eng) as s:
        prof = s.get(FixtureProfile, int(profil_id))
        if prof is None:
            raise ValueError(f"Profil {profil_id} steht nicht in der Bibliothek.")
        a = angaben_von_profil(prof)
        if a is None:
            raise ValueError(f"„{prof.name}“ ist kein Profil des Matrix-Assistenten.")
        mfr = prof.manufacturer.name if prof.manufacturer else ""
        name, typ = prof.name, prof.fixture_type or "matrix"
        modi = {m.name: int(m.channel_count) for m in prof.modes}
    tl = teile(a)
    fehlt = [t.name for t in tl if t.name not in modi]
    if fehlt:
        raise ValueError("Im Profil fehlen Modi: " + ", ".join(fehlt))
    u0, adr = int(start_universum), int(adresse)
    probleme = []
    for t in tl:
        u = u0 + t.index
        if adr + t.kanaele - 1 > DMX_KANAELE:
            probleme.append(f"Teil {t.index + 1} passt ab Adresse {adr} nicht "
                            f"in Universum {u} ({t.kanaele} Kanäle).")
        elif state.check_address_conflict(u, adr, t.kanaele):
            probleme.append(f"Universum {u}, Adressen {adr}–{adr + t.kanaele - 1} "
                            "sind schon belegt.")
    if probleme:
        raise ValueError(" ".join(probleme))
    basis = (label or name).strip() or name
    fids: list[int] = []
    from contextlib import nullcontext
    sammeln = getattr(state, "patch_sammeln", None) or nullcontext
    with sammeln():
        for t in tl:
            order, drehung, flip = teil_lage(a, t)
            fid = int(state.next_fid())
            state.add_fixture(PatchedFixture(
                fid=fid,
                label=basis if len(tl) == 1 else f"{basis} T{t.index + 1}",
                fixture_profile_id=int(profil_id), mode_name=t.name,
                universe=u0 + t.index, address=adr, channel_count=t.kanaele,
                manufacturer_name=mfr, fixture_name=name, fixture_type=typ,
                pixel_order=order, element_rotation=drehung, element_flip=flip))
            fids.append(fid)
    for fid in fids:
        # Die Auto-Kopf-Gruppe legt add_fixture im Einzel-Patch selbst an;
        # im Sammelweg nicht — idempotent nachziehen.
        fx = next((f for f in state.get_patched_fixtures() if f.fid == fid), None)
        if fx is not None:
            try:
                state.create_head_matrix_group(fx, emit=False)
            except Exception:
                pass
    if gesamt_gruppe and len(tl) > 1:
        gesamt_gruppe_anlegen(state, a, fids, basis)
    try:
        state.notify_groups_changed()
    except Exception:
        pass
    return fids


def gesamt_raster(state, a: MatrixAngaben, fids: list[int]) -> dict:
    """``{"c,r": "fid:kopf"}`` ueber die ganze Matrix — aus den Rastern der
    Teile (``head_matrix_layout``, dieselbe Rechnung wie ihre Auto-Gruppen),
    um die Anzeige-Zeile des Teils verschoben."""
    from src.core.app_state import color_head_count, head_matrix_layout
    pos: dict = {}
    by = {f.fid: f for f in state.get_patched_fixtures()}
    for t, fid in zip(teile(a), fids):
        fx = by.get(fid)
        if fx is None:
            continue
        _c, _r, plaetze, _ring = head_matrix_layout(fx, color_head_count(fx))
        z0 = teil_anzeige_zeile(a, t)
        for h, (c, r) in plaetze.items():
            pos[f"{c},{z0 + r}"] = f"{fid}:{h}"
    return pos


def gesamt_gruppe_anlegen(state, a: MatrixAngaben, fids: list[int],
                          basis: str) -> int | None:
    import json as _json
    from src.core.database.models import FixtureGroup
    pos = gesamt_raster(state, a, fids)
    if not pos:
        return None
    try:
        with state._session() as s:
            g = FixtureGroup(name=f"{basis} · Matrix", cols=int(a.breite_px),
                             rows=int(a.hoehe_px),
                             positions_json=_json.dumps(pos), folder="Multi-Head")
            s.add(g)
            s.commit()
            return int(g.id)
    except Exception:
        return None
