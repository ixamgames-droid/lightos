"""FM-56: Die eigene Geraete-Bibliothek als Dateien — das Format „LightOS-Profil“.

Eine JSON-Datei je Geraet unter ``fixtures/bibliothek/<hersteller>/<modell>.json``
(Dateinamen: :func:`dateiname`). Die Beschreibung fuer Menschen steht in
``fixtures/bibliothek/SCHEMA.md``; diese Datei ist die Pruefung dazu.

Was hier steht:

* :func:`pruefe` — eine geladene Datei gegen das Format pruefen. Liefert ALLE
  Befunde als Saetze „Datei: Feld: Meldung“, damit ein Autor in einem Lauf
  sieht, was fehlt (nicht Fehler fuer Fehler).
* :func:`lade_datei` — lesen + pruefen, wirft :class:`ProfilFehler`.
* :func:`einspielen` — alle Dateien der Bibliothek in die Fixture-DB, mit
  ``source='lightos'``. Aufgerufen aus ``fixture_db.ensure_builtins``.
* :func:`profil_zu_daten` / :func:`exportiere` — ein Profil aus der DB als
  LightOS-Profil (fuer eigene Profile des Nutzers, FM-53).
* :func:`importiere` — eine Datei als EIGENES Profil (``source='user'``).
* :func:`qxf_zu_daten` — eine QLC+-``.qxf`` ueber den vorhandenen Importer ins
  LightOS-Format (mit Herkunftsangabe, Apache-2.0 §4b).

★ **Warum ein eigener Kanal ``lightos`` und nicht ``builtin``.** Die Builtins
  stehen als Python-Tupel in ``fixture_db.py`` und haben eine eigene Pflege
  (FM-50-Abgleich, Signatur-Migrationen, QA-68). Wuerden die Dateien dasselbe
  Etikett tragen, glichen zwei Mechanismen dasselbe Profil gegeneinander ab.
  Fuer alle Stellen, die „mitgeliefert vor importiert“ entscheiden (FM-43,
  Showbuilder, ``tools/_profil.py``), zaehlen beide gleich:
  ``models.MITGELIEFERT_QUELLEN``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata

#: Version des Dateiformats. Hochzaehlen nur bei inkompatiblen Aenderungen —
#: neue OPTIONALE Felder brauchen keine neue Version.
FORMAT_VERSION = 1

#: ``FixtureProfile.source`` der aus den Dateien eingespielten Profile.
SOURCE_LIGHTOS = "lightos"

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
#: Wurzel der mitgelieferten Bibliothek.
BIBLIOTHEK_DIR = os.path.join(_REPO, "fixtures", "bibliothek")

#: Geraetetypen (``FixtureProfile.fixture_type``) — dieselben wie im Editor.
TYPEN: dict[str, str] = {
    "dimmer": "reiner Dimmer / Dimmerpack",
    "par": "PAR / Wash ohne Bewegung (LED-PAR, Flood, Blinder mit einer Zelle)",
    "led_bar": "Leiste mit mehreren Segmenten (LED-Bar, Pixel-Bar)",
    "moving_head": "Moving Head (Spot, Beam, Wash), auch Mehrkopf-Mover",
    "scanner": "Scanner (Spiegel)",
    "strobe": "Stroboskop",
    "laser": "Laser",
    "matrix": "Pixel-Panel / Matrix (Rasterform im Modus angeben)",
    "smoke": "Nebelmaschine",
    "hazer": "Hazer / Dunst",
    "other": "alles andere",
}

#: Kanal-Attribute (``FixtureChannel.attribute``) mit Bedeutung. Exakt die
#: Namen des Bestands — andere Namen kennt LightOS nicht (Programmer-Tabs,
#: Farbmischung, Renderer haengen daran).
ATTRIBUTE: dict[str, str] = {
    # Helligkeit
    "intensity": "Dimmer / Helligkeit (Master des Geraets oder eines Kopfes)",
    "dimmer": "Dimmer (gleichwertig zu intensity; bevorzugt intensity)",
    "master": "Master-Dimmer (gleichwertig zu intensity)",
    "shutter": "Shutter/Strobe-Kanal mit Offen-/Zu-/Strobe-Bereichen",
    "strobe": "reine Strobe-Geschwindigkeit (ohne Shutter-Funktion)",
    "duration": "Blitzdauer (Stroboskope)",
    # Farbe
    "color_r": "Rot", "color_g": "Gruen", "color_b": "Blau",
    "color_w": "Weiss (auch Warm-/Kaltweiss; eigene Weiss-Achse siehe weiss)",
    "color_a": "Amber", "color_uv": "UV",
    "cmy_c": "CMY Cyan", "cmy_m": "CMY Magenta", "cmy_y": "CMY Gelb",
    "color_wheel": "Farbrad (Bereiche mit art color/open/rotate)",
    # Position
    "pan": "Pan grob", "pan_fine": "Pan fein (16 bit)",
    "tilt": "Tilt grob", "tilt_fine": "Tilt fein (16 bit)",
    # Beam
    "zoom": "Zoom", "focus": "Fokus", "frost": "Frost", "iris": "Iris",
    "prism": "Prisma ein/aus bzw. Auswahl",
    "prism_rotation": "Prisma-Rotation",
    # Gobo
    "gobo_wheel": "Gobo-Rad (Bereiche mit art gobo/open/shake/rotate)",
    "gobo_wheel2": "zweites Gobo-Rad desselben Geraets",
    "gobo_rotation": "Gobo-Rotation / Index",
    "gobo_fx": "Gobo-Effekt (z. B. Animationsrad-Funktion)",
    "animation": "Animationsrad",
    # Effekte / Steuerung
    "speed": "Bewegungs-/Funktionsgeschwindigkeit",
    "effect_speed": "Effekt-/Programmgeschwindigkeit",
    "effect": "Effekt-Auswahl",
    "macro": "Makro / Auto-Programm / Farbmakro",
    "fan": "Luefter (Nebelmaschine)",
    "reset": "Reset / Steuerkanal mit Reset-Bereich",
    "lamp": "Lampe an/aus",
    "raw": "alles, was in keine Klasse passt (nur Fader, keine Logik)",
    # Laser
    "laser_boundary": "Laser: Begrenzung", "laser_bank": "Laser: Musterbank",
    "laser_x": "Laser: X-Position", "laser_y": "Laser: Y-Position",
    "laser_zoom_x": "Laser: Zoom X", "laser_zoom_y": "Laser: Zoom Y",
    "laser_color": "Laser: Farbe", "laser_color_change": "Laser: Farbwechsel",
    "laser_dots": "Laser: Punkte", "laser_draw": "Laser: Zeichnen",
    "laser_draw_mode": "Laser: Zeichenmodus", "laser_twist": "Laser: Verdrehung",
    "laser_grating": "Laser: Gitter", "laser_scan_rate": "Laser: Scanrate",
}

#: Arten eines Wertebereichs (``ChannelRange.kind``). Aus ihnen baut die UI
#: Schnellwahl-Kacheln (Farbe, Gobo, Strobe, Offen/Zu, Reset).
RANGE_ARTEN: dict[str, str] = {
    "": "unbekannt / nur Beschriftung",
    "open": "offen (Shutter offen, Weiss/offen auf Farb- oder Gobo-Rad)",
    "closed": "geschlossen / Blackout",
    "strobe": "Strobe",
    "color": "eine Farbe auf dem Farbrad",
    "gobo": "ein Gobo",
    "rotate": "Rotation / Durchlauf (Rad- oder Gobo-Rotation)",
    "shake": "Gobo-Shake",
    "sound": "Musiksteuerung",
    "reset": "Reset",
    "frost": "Frost",
    "prism": "Prisma",
}

#: ``herkunft.art`` -> erlaubte ``herkunft.lizenz``.
HERKUNFT_ARTEN: dict[str, tuple[str, ...]] = {
    "lightos": ("eigen",),
    "hersteller-handbuch": ("eigen",),
    "qlcplus": ("Apache-2.0",),
    "ofl": ("MIT",),
}
#: Diese Arten uebernehmen fremde Dateien -> urheber/original/geaendert Pflicht.
FREMD_ARTEN = ("qlcplus", "ofl")

AUFLOESUNGEN = ("8bit", "16bit")

_KOPF_FELDER = {
    "format_version", "hersteller", "hersteller_kurz", "modell", "kurzname",
    "typ", "leistung_w", "notizen", "viz_model", "quelle", "herkunft", "autor",
    "geprueft", "modi",
}
_KOPF_PFLICHT = ("format_version", "hersteller", "modell", "kurzname", "typ",
                 "quelle", "herkunft", "autor", "geprueft", "modi")
_QUELLE_FELDER = {"titel", "version", "datum", "url"}
_HERKUNFT_FELDER = {"art", "lizenz", "urheber", "original", "geaendert"}
_GEPRUEFT_FELDER = {"ok", "wie"}
_MODUS_FELDER = {"name", "beschreibung", "raster", "weiss", "kanaele"}
_KANAL_FELDER = {"name", "attribut", "default", "highlight", "invert",
                 "aufloesung", "segment", "bereiche"}
_BEREICH_FELDER = {"von", "bis", "name", "art"}
_FORM_FELDER = {"rows", "cols"}


class ProfilFehler(ValueError):
    """Eine Datei verletzt das Format. ``befunde`` = alle Saetze."""

    def __init__(self, befunde: list[str]):
        self.befunde = list(befunde)
        super().__init__("\n".join(self.befunde))


# ── Dateinamen ───────────────────────────────────────────────────────────────

_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe",
                          "Ü": "ue", "ß": "ss", "×": "x", "+": "-plus-"})


def slug(text: str) -> str:
    """ASCII, klein, Bindestriche: ``"LED PAR-64 COB RGB"`` -> ``led-par-64-cob-rgb``."""
    t = (text or "").translate(_UMLAUTE)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return t or "unbenannt"


def dateiname(hersteller: str, modell: str) -> str:
    """Relativer Pfad einer Datei in der Bibliothek: ``<hersteller>/<modell>.json``."""
    return f"{slug(hersteller)}/{slug(modell)}.json"


# ── Pruefen ──────────────────────────────────────────────────────────────────

def _ist_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _text_pflicht(d: dict, feld: str, wo: str, out: list[str],
                  max_len: int | None = None) -> None:
    v = d.get(feld)
    if not isinstance(v, str) or not v.strip():
        out.append(f"{wo}{feld}: Pflichtfeld fehlt oder ist leer")
    elif max_len and len(v) > max_len:
        out.append(f"{wo}{feld}: hoechstens {max_len} Zeichen (hat {len(v)})")


def _unbekannt(d: dict, erlaubt: set, wo: str, out: list[str]) -> None:
    for k in sorted(set(d) - erlaubt):
        out.append(f"{wo}{k}: unbekanntes Feld (erlaubt: {', '.join(sorted(erlaubt))})")


def _form(v, wo: str, out: list[str]) -> None:
    if not isinstance(v, dict):
        out.append(f"{wo}: muss ein Objekt {{\"rows\": n, \"cols\": n}} sein")
        return
    _unbekannt(v, _FORM_FELDER, wo + ".", out)
    from .models import GEO_MAX
    for k in ("rows", "cols"):
        n = v.get(k, 0)
        if not _ist_int(n) or not 0 <= n <= GEO_MAX:
            out.append(f"{wo}.{k}: ganze Zahl 0..{GEO_MAX} erwartet (ist {n!r})")


def pruefe(daten, datei: str = "") -> list[str]:
    """Alle Befunde einer geladenen Datei; leer = gueltig."""
    from src.core.dimmer_segmente import ist_dimmer
    p = f"{datei}: " if datei else ""
    out: list[str] = []
    if not isinstance(daten, dict):
        return [f"{p}Datei muss ein JSON-Objekt sein"]
    _unbekannt(daten, _KOPF_FELDER, p, out)
    for f in _KOPF_PFLICHT:
        if f not in daten:
            out.append(f"{p}{f}: Pflichtfeld fehlt")
    if "format_version" in daten and daten["format_version"] != FORMAT_VERSION:
        out.append(f"{p}format_version: {FORMAT_VERSION} erwartet "
                   f"(ist {daten['format_version']!r})")
    _text_pflicht(daten, "hersteller", p, out, 120)
    _text_pflicht(daten, "modell", p, out, 120)
    _text_pflicht(daten, "kurzname", p, out, 40)
    _text_pflicht(daten, "autor", p, out)
    if "hersteller_kurz" in daten:
        hk = daten["hersteller_kurz"]
        if not isinstance(hk, str) or not hk.strip() or len(hk) > 20:
            out.append(f"{p}hersteller_kurz: Text mit 1..20 Zeichen erwartet")
    if daten.get("typ") not in TYPEN:
        out.append(f"{p}typ: unbekannt {daten.get('typ')!r} "
                   f"(erlaubt: {', '.join(TYPEN)})")
    lw = daten.get("leistung_w", 0)
    if not _ist_int(lw) or lw < 0:
        out.append(f"{p}leistung_w: ganze Zahl >= 0 erwartet (ist {lw!r})")
    for f, n in (("notizen", None), ("viz_model", 40)):
        if f in daten and (not isinstance(daten[f], str)
                           or (n and len(daten[f]) > n)):
            out.append(f"{p}{f}: Text erwartet" + (f" (hoechstens {n} Zeichen)" if n else ""))

    q = daten.get("quelle")
    if "quelle" in daten:
        if not isinstance(q, dict):
            out.append(f"{p}quelle: Objekt erwartet")
        else:
            _unbekannt(q, _QUELLE_FELDER, f"{p}quelle.", out)
            _text_pflicht(q, "titel", f"{p}quelle.", out)
            for k in ("version", "datum", "url"):
                if k in q and not isinstance(q[k], str):
                    out.append(f"{p}quelle.{k}: Text erwartet")

    h = daten.get("herkunft")
    if "herkunft" in daten:
        if not isinstance(h, dict):
            out.append(f"{p}herkunft: Objekt erwartet")
        else:
            _unbekannt(h, _HERKUNFT_FELDER, f"{p}herkunft.", out)
            art = h.get("art")
            if art not in HERKUNFT_ARTEN:
                out.append(f"{p}herkunft.art: unbekannt {art!r} "
                           f"(erlaubt: {', '.join(HERKUNFT_ARTEN)})")
            elif h.get("lizenz") not in HERKUNFT_ARTEN[art]:
                out.append(f"{p}herkunft.lizenz: bei art {art!r} nur "
                           f"{' / '.join(HERKUNFT_ARTEN[art])} (ist {h.get('lizenz')!r})")
            if art in FREMD_ARTEN:
                for k in ("urheber", "original", "geaendert"):
                    _text_pflicht(h, k, f"{p}herkunft.", out)
            for k in ("urheber", "original", "geaendert"):
                if k in h and not isinstance(h[k], str):
                    out.append(f"{p}herkunft.{k}: Text erwartet")

    g = daten.get("geprueft")
    if "geprueft" in daten:
        if not isinstance(g, dict):
            out.append(f"{p}geprueft: Objekt {{\"ok\": bool, \"wie\": Text}} erwartet")
        else:
            _unbekannt(g, _GEPRUEFT_FELDER, f"{p}geprueft.", out)
            if not isinstance(g.get("ok"), bool):
                out.append(f"{p}geprueft.ok: true/false erwartet")
            _text_pflicht(g, "wie", f"{p}geprueft.", out)

    modi = daten.get("modi")
    if "modi" in daten and (not isinstance(modi, list) or not modi):
        out.append(f"{p}modi: Liste mit mindestens einem Modus erwartet")
        modi = []
    namen: set[str] = set()
    for mi, m in enumerate(modi or ()):
        wo = f"{p}modi[{mi}]"
        if not isinstance(m, dict):
            out.append(f"{wo}: Objekt erwartet")
            continue
        wo_n = f"{wo} ({m.get('name')!r})" if isinstance(m.get("name"), str) else wo
        _unbekannt(m, _MODUS_FELDER, wo_n + ".", out)
        _text_pflicht(m, "name", wo + ".", out, 80)
        if isinstance(m.get("name"), str):
            if m["name"] in namen:
                out.append(f"{wo_n}.name: Modusname doppelt")
            namen.add(m["name"])
        if "beschreibung" in m and not isinstance(m["beschreibung"], str):
            out.append(f"{wo_n}.beschreibung: Text erwartet")
        for f in ("raster", "weiss"):
            if f in m:
                _form(m[f], f"{wo_n}.{f}", out)
        kanaele = m.get("kanaele")
        if not isinstance(kanaele, list) or not kanaele:
            out.append(f"{wo_n}.kanaele: Liste mit mindestens einem Kanal erwartet")
            continue
        n_weiss = sum(1 for c in kanaele
                      if isinstance(c, dict) and c.get("attribut") == "color_w")
        for ki, c in enumerate(kanaele):
            wk = f"{wo_n}.kanaele[{ki}] (Kanal {ki + 1})"
            if not isinstance(c, dict):
                out.append(f"{wk}: Objekt erwartet")
                continue
            _unbekannt(c, _KANAL_FELDER, wk + ".", out)
            _text_pflicht(c, "name", wk + ".", out, 80)
            if c.get("attribut") not in ATTRIBUTE:
                out.append(f"{wk}.attribut: unbekannt {c.get('attribut')!r} "
                           f"(Liste in SCHEMA.md)")
            for f in ("default", "highlight"):
                v = c.get(f)
                if not _ist_int(v) or not 0 <= v <= 255:
                    out.append(f"{wk}.{f}: Pflichtfeld, ganze Zahl 0..255 (ist {v!r})")
            if "invert" in c and not isinstance(c["invert"], bool):
                out.append(f"{wk}.invert: true/false erwartet")
            if "aufloesung" in c and c["aufloesung"] not in AUFLOESUNGEN:
                out.append(f"{wk}.aufloesung: {' / '.join(AUFLOESUNGEN)} erwartet")
            if "segment" in c:
                s = c["segment"]
                if not _ist_int(s) or s < 0:
                    out.append(f"{wk}.segment: ganze Zahl >= 0 erwartet (0 = erstes "
                               f"Weiss-Segment)")
                elif not ist_dimmer(c.get("attribut")):
                    out.append(f"{wk}.segment: nur an Dimmer-Kanaelen erlaubt")
                elif s >= n_weiss:
                    out.append(f"{wk}.segment: Weiss-Segment {s} gibt es nicht "
                               f"({n_weiss} color_w-Kanaele, 0-basiert)")
            bereiche = c.get("bereiche", [])
            if not isinstance(bereiche, list):
                out.append(f"{wk}.bereiche: Liste erwartet")
                continue
            for bi, b in enumerate(bereiche):
                wb = f"{wk}.bereiche[{bi}]"
                if not isinstance(b, dict):
                    out.append(f"{wb}: Objekt erwartet")
                    continue
                _unbekannt(b, _BEREICH_FELDER, wb + ".", out)
                von, bis = b.get("von"), b.get("bis")
                if not (_ist_int(von) and _ist_int(bis) and 0 <= von <= bis <= 255):
                    out.append(f"{wb}: von/bis ganze Zahlen mit 0 <= von <= bis <= 255 "
                               f"(ist {von!r}..{bis!r})")
                if not isinstance(b.get("name"), str):
                    out.append(f"{wb}.name: Pflichtfeld (Text)")
                elif len(b["name"]) > 80:
                    out.append(f"{wb}.name: hoechstens 80 Zeichen")
                if "art" in b and b["art"] not in RANGE_ARTEN:
                    out.append(f"{wb}.art: unbekannt {b['art']!r} "
                               f"(erlaubt: {', '.join(repr(a) for a in RANGE_ARTEN)})")
    return out


def lade_datei(pfad: str) -> dict:
    """Datei lesen und pruefen. Wirft :class:`ProfilFehler` mit allen Befunden."""
    try:
        with open(pfad, encoding="utf-8") as fh:
            daten = json.load(fh)
    except json.JSONDecodeError as e:
        raise ProfilFehler([f"{pfad}: kein gueltiges JSON (Zeile {e.lineno}, "
                            f"Spalte {e.colno}: {e.msg})"])
    except OSError as e:
        raise ProfilFehler([f"{pfad}: nicht lesbar ({e})"])
    befunde = pruefe(daten, pfad)
    if befunde:
        raise ProfilFehler(befunde)
    return daten


def bibliothek_dateien(verzeichnis: str | None = None, *,
                       mit_beispielen: bool = False) -> list[str]:
    """Alle ``*.json`` der Bibliothek, sortiert. Ordner mit ``_``/``.`` am Anfang
    (``_beispiele``) gehoeren nicht zur ausgelieferten Bibliothek."""
    wurzel = verzeichnis or BIBLIOTHEK_DIR
    out = []
    for ordner, unter, dateien in os.walk(wurzel):
        unter[:] = sorted(u for u in unter if mit_beispielen
                          or not u.startswith(("_", ".")))
        out += [os.path.join(ordner, d) for d in dateien if d.endswith(".json")]
    return sorted(out)


def pruefe_bibliothek(verzeichnis: str | None = None, *,
                      mit_beispielen: bool = True) -> list[str]:
    """Waechter fuer einen ganzen Ordner: jede Datei gueltig, liegt unter ihrem
    Namen (:func:`dateiname`), keine Doppelung Hersteller+Modell."""
    wurzel = verzeichnis or BIBLIOTHEK_DIR
    out: list[str] = []
    gesehen: dict[tuple[str, str, str], str] = {}
    for pfad in bibliothek_dateien(wurzel, mit_beispielen=mit_beispielen):
        rel = os.path.relpath(pfad, wurzel).replace(os.sep, "/")
        try:
            d = lade_datei(pfad)
        except ProfilFehler as e:
            out += [b.replace(pfad, rel, 1) for b in e.befunde]
            continue
        teile = rel.split("/")
        bereich = teile[0] if teile[0].startswith("_") else ""
        soll = (f"{bereich}/" if bereich else "") + dateiname(d["hersteller"], d["modell"])
        if rel != soll:
            out.append(f"{rel}: Dateiname passt nicht zu hersteller/modell — "
                       f"erwartet {soll}")
        schluessel = (bereich, d["hersteller"].strip().casefold(),
                      d["modell"].strip().casefold())
        if schluessel in gesehen:
            out.append(f"{rel}: {d['hersteller']} / {d['modell']} steht schon in "
                       f"{gesehen[schluessel]}")
        else:
            gesehen[schluessel] = rel
    return out


# ── DB -> Daten (Export) ─────────────────────────────────────────────────────

def _modus_zu_daten(m) -> dict:
    d: dict = {"name": m.name}
    if m.description:
        d["beschreibung"] = m.description
    if (m.grid_rows or 0) or (m.grid_cols or 0):
        d["raster"] = {"rows": int(m.grid_rows or 0), "cols": int(m.grid_cols or 0)}
    if (m.white_rows or 0) or (m.white_cols or 0):
        d["weiss"] = {"rows": int(m.white_rows or 0), "cols": int(m.white_cols or 0)}
    kanaele = []
    for c in sorted(m.channels, key=lambda c: c.channel_number):
        k: dict = {"name": c.name, "attribut": c.attribute,
                   "default": int(c.default_value), "highlight": int(c.highlight_value)}
        if c.invert:
            k["invert"] = True
        if (c.resolution or "8bit") != "8bit":
            k["aufloesung"] = c.resolution
        if c.segment is not None:
            k["segment"] = int(c.segment)
        if c.ranges:
            # ★ Reihenfolge nach Wert, nicht nach Einfuegung: die DB kennt keine
            # Reihenfolge der Bereiche, und eine Datei, die bei jedem Export
            # anders sortiert waere, gaebe sinnlose Diffs.
            k["bereiche"] = [
                {"von": int(r.range_from), "bis": int(r.range_to), "name": r.name,
                 "art": r.kind or ""}
                for r in sorted(c.ranges, key=lambda r: (r.range_from, r.range_to,
                                                         r.name, r.kind or ""))]
        kanaele.append(k)
    d["kanaele"] = kanaele
    return d


def _standard_herkunft(prof) -> tuple[dict, dict, dict, str]:
    """quelle, herkunft, geprueft, autor fuer ein Profil ohne eigene Datei."""
    src = (prof.source or "").lower()
    if src == "qlcplus":
        urheber = "QLC+-Beitragende (Heikki Junnila, Massimo Callegari u. a.)"
        if prof.provenance:
            urheber += f"; Datei: {prof.provenance}"
        return ({"titel": f"QLC+-Geraetedefinition {prof.manufacturer.name} / {prof.name}"},
                {"art": "qlcplus", "lizenz": "Apache-2.0", "urheber": urheber,
                 "original": "unbekannt (aus der lokalen Bibliothek exportiert)",
                 "geaendert": "durch den LightOS-QXF-Import ins LightOS-Format umgebaut "
                              "(Attribute, Bereichs-Arten, Rasterform)"},
                {"ok": False, "wie": "nicht geprueft (QLC+-Import)"},
                "LightOS (Export)")
    if src == "builtin":
        return ({"titel": "LightOS-Bestand (fixture_db.py)"},
                {"art": "lightos", "lizenz": "eigen"},
                {"ok": False, "wie": "aus dem eingebauten Bestand uebernommen"},
                "LightOS")
    return ({"titel": "eigenes Profil"},
            {"art": "lightos", "lizenz": "eigen"},
            {"ok": False, "wie": "eigenes Profil, nicht geprueft"},
            "eigenes Profil")


def profil_zu_daten(prof, *, quelle: dict | None = None,
                    herkunft: dict | None = None, geprueft: dict | None = None,
                    autor: str | None = None) -> dict:
    """Ein ``FixtureProfile`` (mit geladenen Modi/Kanaelen/Bereichen) als
    LightOS-Profil. Fehlende Herkunftsangaben werden aus ``source`` abgeleitet;
    ein ``lightos``-Profil nimmt sie aus seiner Bibliotheksdatei."""
    q, h, g, a = _standard_herkunft(prof)
    if (prof.source or "") == SOURCE_LIGHTOS:
        pfad = os.path.join(BIBLIOTHEK_DIR, dateiname(prof.manufacturer.name, prof.name))
        try:
            alt = lade_datei(pfad)
            q, h, g, a = alt["quelle"], alt["herkunft"], alt["geprueft"], alt["autor"]
        except ProfilFehler:
            pass
    d: dict = {
        "format_version": FORMAT_VERSION,
        "hersteller": prof.manufacturer.name,
    }
    if prof.manufacturer.short_name:
        d["hersteller_kurz"] = prof.manufacturer.short_name[:20]
    d.update({
        "modell": prof.name,
        "kurzname": prof.short_name or prof.name[:40],
        "typ": prof.fixture_type if prof.fixture_type in TYPEN else "other",
        "leistung_w": int(prof.power_w or 0),
    })
    if prof.notes:
        d["notizen"] = prof.notes
    if prof.viz_model:
        d["viz_model"] = prof.viz_model
    d.update({
        "quelle": quelle or q,
        "herkunft": herkunft or h,
        "autor": autor or a,
        "geprueft": geprueft or g,
        "modi": [_modus_zu_daten(m) for m in prof.modes],
    })
    return d


def daten_aus_feldern(*, hersteller: str, modell: str, kurzname: str, typ: str,
                      leistung_w: int, modi) -> dict:
    """LightOS-Profil aus dem, was der Fixture-Editor gerade zeigt (auch
    ungespeichert). ``modi`` = ``[(name, kanaele, beschreibung, raster, weiss)]``
    mit Kanaelen wie in ``_ModeTab.channels`` (``attribute``/``default``/
    ``highlight``/``invert``/``resolution``/``segment``/``ranges``)."""
    from src.core.dimmer_segmente import ist_dimmer
    from .fixture_db import segment_wert
    md = []
    for name, kanaele, beschreibung, raster, weiss in modi:
        m: dict = {"name": name}
        if beschreibung:
            m["beschreibung"] = beschreibung
        if tuple(raster or (0, 0)) != (0, 0):
            m["raster"] = {"rows": int(raster[0]), "cols": int(raster[1])}
        if tuple(weiss or (0, 0)) != (0, 0):
            m["weiss"] = {"rows": int(weiss[0]), "cols": int(weiss[1])}
        ks = []
        for c in kanaele:
            k: dict = {"name": str(c.get("name", "")), "attribut": c.get("attribute", "raw"),
                       "default": int(c.get("default", 0)),
                       "highlight": int(c.get("highlight", 255))}
            if c.get("invert"):
                k["invert"] = True
            if (c.get("resolution") or "8bit") != "8bit":
                k["aufloesung"] = c["resolution"]
            seg = segment_wert(c.get("segment"))
            if seg is not None and ist_dimmer(c.get("attribute")):
                k["segment"] = seg
            rs = c.get("ranges") or []
            if rs:
                k["bereiche"] = [{"von": int(r.get("range_from", 0)),
                                  "bis": int(r.get("range_to", 255)),
                                  "name": str(r.get("name", "") or ""),
                                  "art": str(r.get("kind", "") or "")}
                                 for r in sorted(rs, key=lambda r: (
                                     int(r.get("range_from", 0)),
                                     int(r.get("range_to", 255))))]
            ks.append(k)
        m["kanaele"] = ks
        md.append(m)
    return {
        "format_version": FORMAT_VERSION, "hersteller": hersteller.strip(),
        "modell": modell.strip(), "kurzname": (kurzname or modell[:8].upper()).strip(),
        "typ": typ, "leistung_w": int(leistung_w),
        "quelle": {"titel": "eigenes Profil"},
        "herkunft": {"art": "lightos", "lizenz": "eigen"},
        "autor": "eigenes Profil",
        "geprueft": {"ok": False, "wie": "eigenes Profil, nicht geprueft"},
        "modi": md,
    }


def _profil_laden(s, profil_id: int):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from .models import FixtureChannel, FixtureMode, FixtureProfile
    return s.execute(
        select(FixtureProfile)
        .options(selectinload(FixtureProfile.manufacturer),
                 selectinload(FixtureProfile.modes)
                 .selectinload(FixtureMode.channels)
                 .selectinload(FixtureChannel.ranges))
        .where(FixtureProfile.id == profil_id)).scalars().first()


def _json(wert, tiefe: int) -> str:
    einzeilig = json.dumps(wert, ensure_ascii=False)
    # Objekte nur mit einfachen Werten (Kanal ohne Bereiche, Bereich, Raster)
    # kommen auf EINE Zeile — so bleibt ein 150-Kanal-Modus lesbar und ein Diff
    # zeigt den geaenderten Kanal statt sieben Zeilen Klammern.
    if not isinstance(wert, (dict, list)) or (
            isinstance(wert, dict)
            and all(not isinstance(v, (dict, list)) for v in wert.values())
            and len(einzeilig) + 2 * tiefe <= 120):
        return einzeilig
    if not wert:
        return einzeilig
    ein = "  " * (tiefe + 1)
    if isinstance(wert, dict):
        teile = [f"{ein}{json.dumps(k, ensure_ascii=False)}: {_json(v, tiefe + 1)}"
                 for k, v in wert.items()]
        return "{\n" + ",\n".join(teile) + "\n" + "  " * tiefe + "}"
    teile = [f"{ein}{_json(v, tiefe + 1)}" for v in wert]
    return "[\n" + ",\n".join(teile) + "\n" + "  " * tiefe + "]"


def als_json(daten: dict) -> str:
    """Kanonische Schreibweise: eingerueckt, einfache Objekte (Kanal, Bereich)
    auf einer Zeile, Umlaute lesbar, Zeilenende am Schluss."""
    return _json(daten, 0) + "\n"


def schreibe(daten: dict, pfad: str) -> None:
    befunde = pruefe(daten, pfad)
    if befunde:
        raise ProfilFehler(befunde)
    os.makedirs(os.path.dirname(os.path.abspath(pfad)), exist_ok=True)
    with open(pfad, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(als_json(daten))


def exportiere(profil_id: int, pfad: str | None = None, *, engine=None, **herkunft) -> dict:
    """Profil ``profil_id`` als LightOS-Profil; mit ``pfad`` auch als Datei."""
    from sqlalchemy.orm import Session
    from . import fixture_db
    eng = engine if engine is not None else fixture_db.engine()
    with Session(eng) as s:
        prof = _profil_laden(s, profil_id)
        if prof is None:
            raise ValueError(f"Profil {profil_id} gibt es nicht")
        daten = profil_zu_daten(prof, **herkunft)
    if pfad:
        schreibe(daten, pfad)
    return daten


def code_builtins_daten() -> dict[str, dict]:
    """Alle Builtins, wie der CODE sie heute definiert, als LightOS-Profile —
    ``{kurzname: daten}``. In einer Speicher-DB gebaut (``_seed`` +
    ``_ensure_builtins_in``), die echte Bibliothek bleibt unberuehrt."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from .fixture_db import _ensure_builtins_in, _seed
    from .models import FixtureProfile, create_all_idempotent
    eng = create_engine("sqlite://")
    create_all_idempotent(eng)
    try:
        with Session(eng) as s:
            _seed(s)
            s.flush()
            _ensure_builtins_in(s)
            s.flush()
            ids = s.execute(select(FixtureProfile.id)
                            .where(FixtureProfile.source == "builtin")).scalars().all()
            out = {}
            for pid in ids:
                prof = _profil_laden(s, pid)
                out[prof.short_name] = profil_zu_daten(prof)
            return out
    finally:
        eng.dispose()


# ── Daten -> DB ──────────────────────────────────────────────────────────────

def _modes_data(daten: dict) -> list:
    """Die Modi als ``modes_data`` fuer ``fixture_db._add_modes`` — derselbe
    Weg wie die Builtins. Eine fehlende ``art`` leitet ``_add_modes`` dort
    genauso aus dem Namen ab wie bei den Tupeln."""
    out = []
    for m in daten["modi"]:
        kanaele = []
        for c in m["kanaele"]:
            bereiche = [((b["von"], b["bis"], b["name"], b["art"]) if "art" in b
                         else (b["von"], b["bis"], b["name"]))
                        for b in c.get("bereiche", ())]
            kanaele.append((c["name"], c["attribut"], c["default"], c["highlight"],
                            bereiche))
        r, w = m.get("raster", {}), m.get("weiss", {})
        out.append((m["name"], kanaele,
                    (r.get("rows", 0), r.get("cols", 0)),
                    (w.get("rows", 0), w.get("cols", 0))))
    return out


def _modi_anlegen(s, prof, daten: dict) -> None:
    """Modi ueber ``_add_modes`` anlegen und danach die Felder nachtragen, die
    die Builtin-Tupel nicht kennen (Beschreibung, Invert, Aufloesung, Segment)."""
    from .fixture_db import _add_modes
    vorher = set(id(m) for m in prof.modes)
    _add_modes(s, prof, _modes_data(daten))
    s.flush()
    neu = [m for m in prof.modes if id(m) not in vorher]
    for m, md in zip(neu, daten["modi"]):
        m.description = md.get("beschreibung", "")
        for ch, cd in zip(sorted(m.channels, key=lambda c: c.channel_number),
                          md["kanaele"]):
            ch.invert = bool(cd.get("invert", False))
            ch.resolution = cd.get("aufloesung", "8bit")
            ch.segment = cd.get("segment")


def _provenance(daten: dict) -> str:
    h = daten["herkunft"]
    teile = [f"LightOS-Profil v{daten['format_version']}", h["art"], h["lizenz"]]
    if h.get("urheber"):
        teile.append(h["urheber"])
    return " · ".join(teile)[:200]


def _hersteller(s, daten: dict):
    from sqlalchemy import select
    from .models import Manufacturer
    name = daten["hersteller"].strip()
    # ★ NUR ueber den Namen (der ist eindeutig). ``_get_or_create_mfr`` sucht
    # zuerst das Kuerzel — ein abgeleitetes Kuerzel koennte dort einen fremden
    # Hersteller treffen und das Profil still unter falschem Namen ablegen.
    m = s.execute(select(Manufacturer).where(Manufacturer.name == name)).scalar_one_or_none()
    if m is None:
        kurz = (daten.get("hersteller_kurz") or slug(name).replace("-", "")[:8]).upper()
        m = Manufacturer(name=name, short_name=kurz[:20])
        s.add(m)
        s.flush()
    return m


def _kopf_setzen(prof, daten: dict) -> None:
    prof.name = daten["modell"].strip()
    prof.short_name = daten["kurzname"].strip()
    prof.fixture_type = daten["typ"]
    prof.power_w = int(daten.get("leistung_w", 0))
    prof.notes = daten.get("notizen", "")
    prof.viz_model = daten.get("viz_model", "")
    prof.provenance = _provenance(daten)


def _anlegen(s, daten: dict, source: str):
    from .models import FixtureProfile
    prof = FixtureProfile(manufacturer=_hersteller(s, daten), source=source)
    _kopf_setzen(prof, daten)
    s.add(prof)
    s.flush()
    _modi_anlegen(s, prof, daten)
    s.flush()
    return prof


def _vergleichsform(prof) -> tuple:
    """Alles, was eine Datei ueber ein Profil sagt — fuer „hat sich etwas geaendert?“."""
    return (prof.name, prof.short_name, prof.fixture_type, int(prof.power_w or 0),
            prof.notes or "", prof.viz_model or "", prof.provenance or "",
            tuple((m.name, m.description or "", m.grid_rows or 0, m.grid_cols or 0,
                   m.white_rows or 0, m.white_cols or 0, m.channel_count,
                   tuple((c.channel_number, c.name, c.attribute, c.default_value,
                          c.highlight_value, bool(c.invert), c.resolution or "8bit",
                          c.segment,
                          tuple(sorted((r.range_from, r.range_to, r.name, r.kind or "")
                                       for r in c.ranges)))
                         for c in sorted(m.channels, key=lambda c: c.channel_number)))
                  for m in sorted(prof.modes, key=lambda m: m.name)))


#: Was der letzte Lauf von :func:`einspielen` getan hat (Log/Tests).
LETZTES_EINSPIELEN: dict = {"neu": [], "aktualisiert": [], "verdeckt": [], "fehler": []}


def einspielen(s, verzeichnis: str | None = None) -> bool:
    """Alle Dateien der Bibliothek in die DB (``source='lightos'``).

    * neu -> anlegen;
    * vorhanden (gleicher Hersteller + Modell + ``source='lightos'``) und
      anders -> Kopf aktualisieren und die Modi aus der Datei neu aufbauen. Die
      Profil-ID bleibt stabil; gepatchte Geraete haengen an ID + Modusname.
      Die Datei ist hier die Wahrheit: eine Korrektur in der Datei ist eine
      bewusste Entscheidung (wie die Signatur-Migrationen der Builtins);
    * gibt es Hersteller + Modell schon als **Builtin**, bleibt die Datei
      draussen (``verdeckt``) — sonst stuende das Geraet zweimal als
      mitgeliefert da (QA-68). Die Uebernahme eines Builtins in eine Datei ist
      ein eigener Migrationsschritt;
    * ungueltige Dateien werden gemeldet und uebersprungen, nie halb eingespielt.

    Eigene Profile (``user``) und QLC+-Importe fasst die Funktion nie an.
    Liefert, ob etwas geaendert wurde."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from .models import (FixtureChannel, FixtureMode, FixtureProfile, Manufacturer)
    bericht = {"neu": [], "aktualisiert": [], "verdeckt": [], "fehler": []}
    geaendert = False
    gesehen: set[tuple[str, str]] = set()
    for pfad in bibliothek_dateien(verzeichnis):
        try:
            daten = lade_datei(pfad)
        except ProfilFehler as e:
            bericht["fehler"] += e.befunde
            continue
        name_h, modell = daten["hersteller"].strip(), daten["modell"].strip()
        schluessel = (name_h.casefold(), modell.casefold())
        if schluessel in gesehen:
            bericht["fehler"].append(f"{pfad}: {name_h} / {modell} doppelt in der Bibliothek")
            continue
        gesehen.add(schluessel)
        vorhanden = s.execute(
            select(FixtureProfile)
            .join(Manufacturer, FixtureProfile.manufacturer_id == Manufacturer.id)
            .options(selectinload(FixtureProfile.modes)
                     .selectinload(FixtureMode.channels)
                     .selectinload(FixtureChannel.ranges))
            .where(Manufacturer.name == name_h, FixtureProfile.name == modell,
                   FixtureProfile.source.in_(("builtin", SOURCE_LIGHTOS)))
            .order_by(FixtureProfile.id)).scalars().all()
        if any(p.source == "builtin" for p in vorhanden):
            bericht["verdeckt"].append(f"{name_h} / {modell}")
            continue
        if not vorhanden:
            with s.begin_nested():
                _anlegen(s, daten, SOURCE_LIGHTOS)
            bericht["neu"].append(f"{name_h} / {modell}")
            geaendert = True
            continue
        prof = vorhanden[0]
        ist = _vergleichsform(prof)
        # Soll ueber DENSELBEN Weg bauen wie das Anlegen (Savepoint, danach
        # zurueckgerollt) — eine zweite Normalisierung der Datei koennte von
        # `_add_modes` abweichen (abgeleitete Bereichs-Arten) und dann bei jedem
        # Start „aktualisieren“.
        sp = s.begin_nested()
        soll = _vergleichsform(_anlegen(s, daten, SOURCE_LIGHTOS))
        sp.rollback()
        if soll == ist:
            continue
        _kopf_setzen(prof, daten)
        prof.modes.clear()          # cascade loescht Kanaele + Ranges
        s.flush()
        _modi_anlegen(s, prof, daten)
        s.flush()
        bericht["aktualisiert"].append(f"{name_h} / {modell}")
        geaendert = True
    LETZTES_EINSPIELEN.clear()
    LETZTES_EINSPIELEN.update(bericht)
    if bericht["fehler"]:
        print(f"[bibliothek] {len(bericht['fehler'])} Befund(e) in der Geraete-"
              f"Bibliothek, Dateien uebersprungen:\n  " + "\n  ".join(bericht["fehler"]))
    if bericht["neu"] or bericht["aktualisiert"] or bericht["verdeckt"]:
        print(f"[bibliothek] LightOS-Profile: neu {len(bericht['neu'])}, "
              f"aktualisiert {bericht['aktualisiert']}, von Builtins verdeckt "
              f"{bericht['verdeckt']}")
    return geaendert


def bibliothek_stand(verzeichnis: str | None = None) -> str:
    """Fingerabdruck aller Dateien (Pfad + Inhalt) — aendert sich eine Datei,
    laeuft :func:`einspielen` beim naechsten Start einmal."""
    wurzel = verzeichnis or BIBLIOTHEK_DIR
    h = hashlib.sha256(f"v{FORMAT_VERSION}".encode())
    for pfad in bibliothek_dateien(wurzel):
        h.update(os.path.relpath(pfad, wurzel).replace(os.sep, "/").encode())
        try:
            with open(pfad, "rb") as fh:
                h.update(fh.read())
        except OSError:
            pass
    return h.hexdigest()[:16]


def einspielen_wenn_noetig(s, verzeichnis: str | None = None) -> bool:
    """:func:`einspielen`, aber nur wenn sich die Bibliothek seit dem letzten
    Lauf in DIESER DB geaendert hat (Stempel in ``bibliothek_stand``)."""
    from sqlalchemy import text
    soll = bibliothek_stand(verzeichnis)
    s.execute(text("CREATE TABLE IF NOT EXISTS bibliothek_stand (stand TEXT)"))
    row = s.execute(text("SELECT stand FROM bibliothek_stand LIMIT 1")).first()
    if row and row[0] == soll:
        return False
    einspielen(s, verzeichnis)
    s.execute(text("DELETE FROM bibliothek_stand"))
    s.execute(text("INSERT INTO bibliothek_stand (stand) VALUES (:s)"), {"s": soll})
    return True


def importiere(pfad_oder_daten, *, engine=None) -> int:
    """Eine LightOS-Profil-Datei als EIGENES Profil (``source='user'``) anlegen.
    Gibt die neue Profil-ID zurueck. Gibt es Hersteller + Modell schon, wird
    nichts angelegt (``ValueError``) — eine stille Dublette waere beim Laden
    einer Show genau die Mehrdeutigkeit, die FM-43 meldet."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from . import fixture_db
    from .models import FixtureProfile, Manufacturer
    if isinstance(pfad_oder_daten, dict):
        daten = pfad_oder_daten
        befunde = pruefe(daten, "Import")
        if befunde:
            raise ProfilFehler(befunde)
    else:
        daten = lade_datei(pfad_oder_daten)
    eng = engine if engine is not None else fixture_db.engine()
    with Session(eng) as s:
        da = s.execute(
            select(FixtureProfile.id, FixtureProfile.source)
            .join(Manufacturer, FixtureProfile.manufacturer_id == Manufacturer.id)
            .where(Manufacturer.name == daten["hersteller"].strip(),
                   FixtureProfile.name == daten["modell"].strip())).first()
        if da is not None:
            raise ValueError(
                f"„{daten['hersteller']} / {daten['modell']}“ steht schon in der "
                f"Bibliothek (Profil {da[0]}, {da[1]}). Modellnamen in der Datei "
                f"aendern, um es als eigenes Profil daneben anzulegen.")
        prof = _anlegen(s, daten, "user")
        s.commit()
        return prof.id


# ── Fremdformate -> LightOS-Profil ───────────────────────────────────────────

_QLC_URL = "https://github.com/mcallegari/qlcplus/blob/master/"


def qxf_zu_daten(pfad: str, original: str | None = None) -> dict:
    """Eine QLC+-``.qxf`` ueber den vorhandenen Importer (``qxf_import``) ins
    LightOS-Format. Der Importer laeuft in einer Speicher-DB — dieselben
    Regeln wie beim Bibliotheks-Import (Attribute, Bereichs-Arten, Rasterform,
    FM-46-Segmente aus ``<Head>``), nichts doppelt implementiert.

    ``herkunft`` wird gesetzt: art ``qlcplus``, Apache-2.0, Urheber aus dem
    ``<Creator>``-Block, ``original`` = Pfad in QLC+ (``resources/fixtures/…``,
    sonst der Dateiname), ``geaendert`` = was der Umbau getan hat (§4b)."""
    import xml.etree.ElementTree as ET
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from .models import FixtureProfile, create_all_idempotent
    from .qxf_import import herkunft_aus_creator, import_qxf_file

    try:
        root = ET.parse(pfad).getroot()
    except (ET.ParseError, OSError) as e:
        raise ProfilFehler([f"{pfad}: keine lesbare .qxf ({e})"])
    eng = create_engine("sqlite://")
    create_all_idempotent(eng)
    try:
        with Session(eng) as s:
            if not import_qxf_file(pfad, s, {}):
                raise ProfilFehler([f"{pfad}: der QXF-Import hat kein Profil erzeugt "
                                    f"(Hersteller/Modell fehlt?)"])
            s.flush()
            prof = s.query(FixtureProfile).first()
            prof = _profil_laden(s, prof.id)
            if original is None:
                norm = os.path.abspath(pfad).replace(os.sep, "/")
                i = norm.find("resources/fixtures/")
                original = norm[i:] if i >= 0 else os.path.basename(pfad)
            creator = herkunft_aus_creator(root)
            urheber = "QLC+-Beitragende (Heikki Junnila, Massimo Callegari u. a.)"
            if creator:
                urheber += f"; Datei: {creator}"
            n_seg = sum(1 for m in prof.modes for c in m.channels if c.segment is not None)
            n_raster = sum(1 for m in prof.modes if m.grid_rows or m.grid_cols)
            n_bereiche = sum(len(c.ranges) for m in prof.modes for c in m.channels)
            geaendert = ["ins LightOS-Format umgebaut (JSON statt QXF)",
                         "Kanal-Attribute auf LightOS-Namen abgebildet",
                         "Default-/Highlight-Werte von LightOS gesetzt"]
            if n_bereiche:
                geaendert.append(f"{n_bereiche} Wertebereiche mit Art (kind) versehen")
            if n_raster:
                geaendert.append(f"Rasterform in {n_raster} Modus/Modi aus <Physical> uebernommen")
            if n_seg:
                geaendert.append(f"{n_seg} Dimmer-Weiss-Segment-Zuordnung(en) aus <Head> abgeleitet")
            daten = profil_zu_daten(
                prof,
                quelle={"titel": f"QLC+-Geraetedefinition {os.path.basename(pfad)}",
                        "url": _QLC_URL + original if original.startswith("resources/")
                        else ""},
                herkunft={"art": "qlcplus", "lizenz": "Apache-2.0", "urheber": urheber,
                          "original": original, "geaendert": "; ".join(geaendert)},
                geprueft={"ok": False, "wie": "automatisch aus QLC+ konvertiert, "
                                              "nicht gegen das Handbuch geprueft"},
                autor="LightOS (QXF-Konverter)")
            if not daten["quelle"]["url"]:
                del daten["quelle"]["url"]
            return daten
    finally:
        eng.dispose()


def ofl_zu_daten(pfad: str, original: str | None = None) -> dict:
    """Open Fixture Library (MIT) -> LightOS-Profil.

    TODO(FM-56): noch nicht gebaut. OFL-Dateien (``fixtures/<hersteller>/<modell>.json``
    im OFL-Repo) haben ein eigenes Capability-Modell; ein Konverter muss es auf
    ATTRIBUTE/RANGE_ARTEN abbilden und ``herkunft`` = {art "ofl", lizenz "MIT",
    urheber aus ``meta.authors``, original = OFL-Pfad, geaendert = Umbauliste}
    setzen. Vor dem ersten OFL-Profil: MIT-Lizenztext der OFL unter
    ``licenses/`` ablegen und in THIRD_PARTY_NOTICES.md („Geräte-Bibliothek“)
    verlinken — der Waechter verlangt das."""
    raise NotImplementedError("OFL-Konverter ist noch nicht gebaut (FM-56, TODO)")
