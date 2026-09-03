"""STAB-DEDUP-OPT: verwaiste ``patched_fixtures``-Zeilen finden und in Quarantäne
verschieben — nutzer-ausgelöst, nie automatisch, nie gelöscht.

Davids Show-DB trägt Altlasten: Zeilen aus früheren Patches, die niemand mehr
benutzt, teils mit überlappenden Adressen. Sie stören nicht ständig, aber sie
machen den Patch unlesbar und produzieren im Adress-Audit Rauschen.

★ **DIE ASYMMETRIE IST DER GANZE ENTWURF.** Ein Gerät fälschlich zu verschieben
ist ein Datenverlust in Davids Show; ein echtes Waisen-Gerät fälschlich zu
behalten ist ein Schönheitsfehler. Deshalb ist jede Unsicherheit hier eine
Referenz:

* **Reine Adress-Überlappung ist NIE ein Grund.** Zwei Geräte auf derselben
  Adresse können beide gewollt sein (Ersatzgerät, absichtlicher Parallelbetrieb).
  Überlappungen werden nur ausgewiesen, nie gewertet.
* **Opake Blobs werden über-approximiert.** Im VC-Layout und in den Bühnen-Daten
  steckt Struktur, die dieses Modul nicht kennt. Statt sie zu deuten, wird
  stumpf gesucht, ob die fid dort als Zahl irgendwo vorkommt. Das findet zu
  viel — und zwar in die harmlose Richtung.
* **Ein Scan-Ort, der nicht erreichbar ist, bricht ab** (``ScanUnvollstaendig``).
  Ein nicht ladbarer Snap-Speicher darf nicht als „keine Referenzen" durchgehen;
  genau so entstehen Datenverluste, die niemand mehr zuordnen kann.

Nichts hier läuft von selbst. Aufruf über ``tools/patch_quarantaene.py``, und
der zeigt ohne ``--anwenden`` nur an.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


class ScanUnvollstaendig(RuntimeError):
    """Ein Referenz-Ort war nicht erreichbar — es wird NICHT geraten."""


@dataclass
class Befund:
    fid: int
    label: str = ""
    universe: int = 1
    address: int = 1
    channel_count: int = 0
    #: Wo die fid überall vorkommt. Leer = Waisen-Kandidat.
    fundstellen: list[str] = field(default_factory=list)
    #: Rein informativ. Überlappung ist NIE ein Grund zur Quarantäne.
    ueberlappt_mit: list[int] = field(default_factory=list)

    @property
    def ist_kandidat(self) -> bool:
        return not self.fundstellen


# Die Orte, die ``referenzen`` prüft. Als Konstante, damit ein Test sie gegen
# die tatsächlich geprüften Orte halten kann — ein stillschweigend entfernter
# Ort wäre sonst genau der Datenverlust, den dieses Modul verhindern soll.
SCAN_ORTE = (
    "programmer",
    "base_levels",
    "auswahl",
    "funktionen",
    "cuelisten",
    "geraetegruppen",
    "snap-bibliothek",
    "visualizer-positionen",
    "visualizer-drehungen",
    "2d-positionen",
    "virtuelle-konsole",
    "buehnen-objekte",
)


def _als_ints(objekt) -> set[int]:
    """Jede ganze Zahl, die irgendwo in einer JSON-artigen Struktur steckt.

    Die Über-Approximation für opake Blobs: hier wird ausdrücklich NICHT
    verstanden, was die Struktur bedeutet — nur, ob die fid darin vorkommt.
    Auch Ziffern-Strings zählen, weil JSON-Schlüssel Strings sind.
    """
    treffer: set[int] = set()
    stapel = [objekt]
    while stapel:
        o = stapel.pop()
        if isinstance(o, bool):
            continue
        if isinstance(o, int):
            treffer.add(o)
        elif isinstance(o, str):
            if o.lstrip("-").isdigit():
                try:
                    treffer.add(int(o))
                except ValueError:
                    pass
        elif isinstance(o, dict):
            stapel.extend(o.keys())
            stapel.extend(o.values())
        elif isinstance(o, (list, tuple, set)):
            stapel.extend(o)
    return treffer


def _pflicht(ort: str, fn):
    """Einen Scan-Ort auswerten — oder abbrechen, statt ihn zu überspringen."""
    try:
        return fn()
    except ScanUnvollstaendig:
        raise                                    # schon praezise — nicht neu verpacken
    except Exception as e:                       # noqa: BLE001
        raise ScanUnvollstaendig(
            f"Referenz-Ort '{ort}' war nicht auswertbar ({e!r}). Es wird NICHT "
            f"geraten — ohne diesen Ort kann keine Waise sicher bestimmt werden."
        ) from e


def _pruefe_gruppen_lesbar(state, gruppen) -> None:
    """Wirft, wenn ``list_fixture_groups`` einen Lesefehler VERSCHLUCKT hat.

    ★ Die zweite Haelfte von STAB-22. ``AppState.list_fixture_groups`` endet auf
    ``except Exception: return []`` — fuer den Preset-Browser ist das richtig
    (eine leere Liste ist dort ein ertraeglicher Anzeigefehler), fuer ein
    Werkzeug, das daraufhin GERAETE VERSCHIEBT, ist es das Gegenteil: ein
    unlesbarer Gruppen-Bestand sieht exakt aus wie "keine Gruppen", und die
    Abbruch-Regel dieses Moduls kann an dieser Stelle prinzipiell nie greifen.

    Statt die Abfrage nachzubauen — das waere die zweite Quelle, und die zweite
    ist immer die veraltete — wird nur GEZAEHLT: stehen Zeilen in der Tabelle,
    darf die Liste nicht leer sein. Die Auswertung selbst bleibt allein bei
    ``list_fixture_groups``.

    Ohne Show-DB (Test-Attrappen) gibt es nichts gegenzupruefen; dann still
    zurueck — das ist kein verschluckter Fehler, sondern kein Bestand.
    """
    engine = getattr(state, "_show_engine", None)
    if engine is None:
        return
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            anzahl = conn.execute(
                text("SELECT count(*) FROM fixture_groups")).scalar() or 0
    except Exception as e:                       # noqa: BLE001
        raise ScanUnvollstaendig(
            f"Der Gruppen-Bestand war nicht zaehlbar ({e!r}). Ohne ihn kann "
            f"keine Waise sicher bestimmt werden — es wird NICHT geraten."
        ) from e
    if anzahl and not gruppen:
        raise ScanUnvollstaendig(
            f"{anzahl} Gruppe(n) stehen in der Show-DB, aber "
            f"list_fixture_groups() liefert keine — der Lesefehler wurde dort "
            f"verschluckt (except Exception: return []). Es wird NICHT geraten."
        )


def referenzen(state, fid: int) -> list[str]:
    """Alle Stellen, an denen ``fid`` vorkommt. Leere Liste = Waise.

    Wirft ``ScanUnvollstaendig``, sobald ein Ort nicht auswertbar ist.
    """
    fid = int(fid)
    gefunden: list[str] = []

    def _melde(ort: str, bedingung) -> None:
        if _pflicht(ort, bedingung):
            gefunden.append(ort)

    _melde("programmer", lambda: fid in (getattr(state, "programmer", {}) or {}))
    _melde("base_levels", lambda: fid in (getattr(state, "base_levels", {}) or {}))
    _melde("auswahl", lambda: fid in (getattr(state, "selected_fids", []) or []))

    # Funktionen: EFX/Matrix/Scene/Carousel/Chaser/Collection — die Auflösung
    # (inkl. Rekursion und Zyklusschutz) leistet der FunctionManager selbst.
    # Sie hier nachzubauen hiesse, eine zweite Quelle fuer dieselbe Frage zu
    # pflegen, und die zweite waere die veraltete.
    def _funktionen():
        fm = getattr(state, "function_manager", None)
        if fm is None:
            return False
        # `all()` und `f.id` — NICHT `functions()`/`f.fid`. Der erste Entwurf
        # griff daneben, und der Trockenlauf brach dadurch sofort mit
        # ScanUnvollstaendig ab statt jedes Geraet als Waise auszuweisen.
        # Genau dafuer ist die Abbruch-Regel da.
        for f in fm.all():
            if fid in fm.affected_fids(getattr(f, "id", -1)):
                return True
        return False
    _melde("funktionen", _funktionen)

    def _cuelisten():
        for stack in (getattr(state, "cue_stacks", []) or []):
            for cue in (getattr(stack, "cues", []) or []):
                if fid in _als_ints(getattr(cue, "values", {}) or {}):
                    return True
        return False
    _melde("cuelisten", _cuelisten)

    def _gruppen():
        # ★ STAB-22: Dieser Ort hat seit PR #535 NIE angeschlagen. Er las
        # ``positions_json``/``positions`` — Felder, die ``list_fixture_groups``
        # gar nicht liefert; sie gibt ``{id, name, folder, fids}`` zurueck. Der
        # Wert war also immer ``None``, die Suche immer leer, und ein Geraet,
        # das NUR in einer Gruppe steckt, galt als Waise. Ein ``--anwenden``
        # haette es aus dem Patch entfernt.
        #
        # ``fids`` ist zugleich die RICHTIGE Quelle, nicht nur die vorhandene:
        # es entsteht aus ``base_fids_in_grid_order``, der einen Parse-Quelle
        # des Hauses, und loest Kopf-Zellen ("7:0") bereits auf ihre Basis-fid
        # auf. Ein Rueckfall auf das rohe ``positions_json`` waere genau dort
        # blind, weil ``_als_ints`` nur reine Ziffernfolgen akzeptiert — er
        # ist deshalb ersatzlos gestrichen statt "sicherheitshalber" behalten.
        gruppen = state.list_fixture_groups()
        _pruefe_gruppen_lesbar(state, gruppen)
        for g in gruppen:
            if not isinstance(g, dict):
                continue
            # ★★ FM-41: hier ist `ref_fids` die richtige Frage, nicht `fids`.
            # Dieses Modul fragt "wird das Geraet irgendwo ERWAEHNT" und
            # verschiebt bei Nein Geraete aus dem Patch — also ist Uebertreiben
            # die sichere Richtung. `fids` sagt dagegen, was die Gruppe FAEHRT,
            # und laesst eine Weiss-Zelle bewusst weg, solange der Renderer sie
            # nicht bedient. Gemessen fiel ein Geraet, das NUR ueber
            # Weiss-Zellen in einer Gruppe steckt, sonst als Waise durch —
            # wortgleich der Fehler, den STAB-22 fuer Kopf-Zellen behoben hat.
            # Rueckfall auf `fids`, wenn die Quelle den Schluessel nicht
            # kennt (aeltere Attrappe): dann gilt wieder der alte Stand,
            # nie weniger.
            for x in (g.get("ref_fids") or g.get("fids") or ()):
                try:
                    if int(x) == fid:
                        return True
                except (TypeError, ValueError):
                    continue
        return False
    _melde("geraetegruppen", _gruppen)

    def _snaps():
        from src.core.engine.snap_library import get_snap_library
        for snap in get_snap_library().snaps():
            if fid in _als_ints(getattr(snap, "values", {}) or {}):
                return True
        return False
    _melde("snap-bibliothek", _snaps)

    _melde("visualizer-positionen",
           lambda: fid in (getattr(state, "visualizer_positions", {}) or {}))
    _melde("visualizer-drehungen",
           lambda: fid in (getattr(state, "visualizer_rotations", {}) or {}))
    _melde("2d-positionen",
           lambda: fid in (getattr(state, "live_view_positions", {}) or {}))

    # Opake Blobs: nicht deuten, nur suchen (s. Modulkopf).
    _melde("virtuelle-konsole",
           lambda: fid in _als_ints(getattr(state, "_vc_layout", {}) or {}))
    _melde("buehnen-objekte",
           lambda: fid in _als_ints(getattr(state, "stage_objects", []) or []))

    return gefunden


def wirkt_unbeladen(state) -> bool:
    """Sieht der Zustand so aus, als sei die Show gar nicht geladen?

    ★ DAS GEFAEHRLICHSTE LOCH DIESES WERKZEUGS, im Sandbox-Lauf entdeckt: der
    PATCH kommt aus ``current_show.db``, die Referenzen aber groesstenteils aus
    der SHOW-DATEI (Funktionen, Cuelisten, VC-Layout, Snaps). Startet man den
    Scan ohne geladene Show, ist der Patch voll und jede Referenzquelle leer —
    also gilt JEDES Geraet als Waise. Ein ``--anwenden`` haette damit den
    kompletten Patch in die Quarantaene geraeumt.

    Der Test darauf ist keine Heuristik ueber einzelne Orte, sondern ihre
    Kombination: Geraete im Patch, aber NIRGENDS auch nur eine Funktion, Cue,
    ein VC-Widget oder ein Snap. Eine echte Show in diesem Zustand ist denkbar
    (frisch gepatcht, noch nichts gebaut) — deshalb blockiert der Aufrufer mit
    einer bewussten Ausnahme, statt dass hier stumm entschieden wird.
    """
    if not (getattr(state, "_patch_cache", None) or []):
        return False        # kein Patch, nichts zu verlieren
    fm = getattr(state, "function_manager", None)
    hat_funktionen = bool(fm and fm.all())
    hat_cues = any((getattr(st, "cues", []) or [])
                   for st in (getattr(state, "cue_stacks", []) or []))
    hat_vc = bool(getattr(state, "_vc_layout", {}) or {})
    try:
        from src.core.engine.snap_library import get_snap_library
        hat_snaps = bool(get_snap_library().snaps())
    except Exception:                                    # noqa: BLE001
        hat_snaps = True     # im Zweifel als "da" werten -> blockiert eher
    return not (hat_funktionen or hat_cues or hat_vc or hat_snaps)


def _ueberlappungen(patch) -> dict[int, list[int]]:
    """Wer belegt mit wem dieselbe Adresse? Rein informativ."""
    belegt: dict[tuple[int, int], list[int]] = {}
    for f in patch:
        n = max(1, int(getattr(f, "channel_count", 1) or 1))
        for a in range(int(f.address), int(f.address) + n):
            belegt.setdefault((int(f.universe), a), []).append(int(f.fid))
    raus: dict[int, set[int]] = {}
    for fids in belegt.values():
        if len(fids) < 2:
            continue
        for x in fids:
            raus.setdefault(x, set()).update(y for y in fids if y != x)
    return {k: sorted(v) for k, v in raus.items()}


def analysiere(state) -> list[Befund]:
    """Jede gepatchte Zeile mit ihren Fundstellen und Überlappungen."""
    patch = list(getattr(state, "_patch_cache", []) or [])
    ueberlappt = _ueberlappungen(patch)
    raus = []
    for f in patch:
        fid = int(f.fid)
        raus.append(Befund(
            fid=fid,
            label=str(getattr(f, "label", "") or ""),
            universe=int(getattr(f, "universe", 1) or 1),
            address=int(getattr(f, "address", 1) or 1),
            channel_count=int(getattr(f, "channel_count", 0) or 0),
            fundstellen=referenzen(state, fid),
            ueberlappt_mit=ueberlappt.get(fid, []),
        ))
    return raus


def finde_kandidaten(state) -> list[Befund]:
    """Nur die Waisen — Geräte ohne jede Fundstelle."""
    return [b for b in analysiere(state) if b.ist_kandidat]


def in_quarantaene(state, fids, *, grund: str = "manuell") -> list[int]:
    """Verschiebt die genannten Geräte in die Quarantäne-Tabelle.

    **Verschieben, nicht löschen:** die vollständige Zeile wandert als JSON in
    ``quarantined_fixtures`` und lässt sich verlustfrei zurückholen — auch dann
    noch, wenn ``patched_fixtures`` später Spalten dazubekommt. Genau deshalb
    ein JSON-Feld statt gespiegelter Spalten: eine gespiegelte Tabelle driftet,
    und gemerkt wird das erst beim Zurückholen.

    Prüft jeden Kandidaten NOCH EINMAL gegen ``referenzen`` — zwischen Anzeige
    und Bestätigung kann der Nutzer das Gerät längst wieder benutzt haben.
    """
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from src.core.database.models import PatchedFixture, QuarantinedFixture

    ziel = {int(x) for x in fids}
    if not ziel:
        return []
    engine = getattr(state, "_show_engine", None)
    if engine is None:
        raise RuntimeError("keine Show-DB verbunden")

    verschoben: list[int] = []
    with Session(engine) as s:
        for fid in sorted(ziel):
            noch_frei = referenzen(state, fid)
            if noch_frei:
                continue                      # inzwischen wieder in Benutzung
            zeile = s.scalar(select(PatchedFixture).where(PatchedFixture.fid == fid))
            if zeile is None:
                continue
            daten = {c.name: getattr(zeile, c.name)
                     for c in PatchedFixture.__table__.columns}
            s.add(QuarantinedFixture(
                fid=fid,
                label=str(zeile.label or ""),
                universe=int(zeile.universe or 1),
                address=int(zeile.address or 1),
                grund=grund,
                verschoben_am=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                daten_json=json.dumps(daten, default=str, ensure_ascii=False),
            ))
            s.delete(zeile)
            verschoben.append(fid)
        s.commit()
    return verschoben


def zurueckholen(state, fid: int) -> bool:
    """Holt ein Gerät aus der Quarantäne in den Patch zurück."""
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from src.core.database.models import PatchedFixture, QuarantinedFixture

    engine = getattr(state, "_show_engine", None)
    if engine is None:
        raise RuntimeError("keine Show-DB verbunden")
    with Session(engine) as s:
        q = s.scalar(select(QuarantinedFixture)
                     .where(QuarantinedFixture.fid == int(fid)))
        if q is None:
            return False
        daten = json.loads(q.daten_json or "{}")
        daten.pop("id", None)
        gueltig = {c.name for c in PatchedFixture.__table__.columns}
        s.add(PatchedFixture(**{k: v for k, v in daten.items() if k in gueltig}))
        s.delete(q)
        s.commit()
    return True


def liste_quarantaene(state) -> list[dict]:
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from src.core.database.models import QuarantinedFixture

    engine = getattr(state, "_show_engine", None)
    if engine is None:
        return []
    with Session(engine) as s:
        return [{"fid": q.fid, "label": q.label, "universe": q.universe,
                 "address": q.address, "grund": q.grund,
                 "verschoben_am": q.verschoben_am}
                for q in s.scalars(select(QuarantinedFixture)).all()]
