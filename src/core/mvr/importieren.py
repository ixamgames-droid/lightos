"""VIZ-56: MVR-Import — Plan (Zuordnung, Adressen, Konflikte) und Anwenden.

Nach dem Vorbild des Tabellen-Imports (``src/core/patch_tabelle.py``):
:func:`baue_plan` rechnet aus der gelesenen Datei, der Bibliothek und dem
vorhandenen Patch je Geraet einen :class:`Eintrag`; :func:`wende_an` legt die
anlegbaren an — ueber ``AppState.add_fixture`` wie beim Patchen von Hand —
und setzt Position und Drehung im 3D. Alles ist EIN Rueckgaengig-Schritt.

★ Regeln:

1. **Nie still ein falsches Profil.** Zugeordnet wird ueber Hersteller +
   Modell + Kanalzahl des Modus (ohne Gross/Klein und Leerzeichen). Ein
   GDTF-Typ, den die Bibliothek nicht kennt, wird **neu aus der GDTF**
   angelegt (:mod:`.gdtf_profil`) — nie verworfen, nie ein Abbruch. Ein
   Geraet ohne lesbaren Typ bleibt „nicht zugeordnet“, bis jemand ein Profil
   waehlt.
2. **Vorhandenes wird nie veraendert.** Trifft ein Geraet einen belegten
   Bereich, wird es uebersprungen — oder, wenn man das im Dialog waehlt, auf
   die naechste freie Adresse gelegt. Ein unadressiertes Geraet kennt LightOS
   nicht; „freie Adresse“ ist der Ersatz dafuer (die Adresse steht in der
   Vorschau und im Patch und laesst sich dort aendern).
3. **Alles oder nichts.** Scheitert unterwegs ein Schritt, wird alles
   zurueckgenommen — auch die neu angelegten Bibliotheksprofile. Der Patch
   bleibt dann, wie er war.
"""
from __future__ import annotations

import bisect
from contextlib import nullcontext
from dataclasses import dataclass, field

from src.core import patch_tabelle as T

from . import gdtf_profil as GP
from .achsen import ist_gespiegelt, mvr_zu_lightos
from .lesen import GdtfModus, GdtfTyp, MvrDatei, MvrGeraet

UNIVERSUM_MAX = T.UNIVERSUM_MAX
UNIVERSUM_GROESSE = T.UNIVERSUM_GROESSE

# Art der Zuordnung
BIBLIOTHEK, NEU, GEWAEHLT, NICHT_ZUGEORDNET = ("bibliothek", "neu", "gewaehlt",
                                               "nicht_zugeordnet")
# Status
ANLEGBAR, OFFEN, UEBERSPRUNGEN = "anlegbar", "offen", "uebersprungen"
# Wahl bei Konflikt / fehlender Adresse
UEBERSPRINGEN, FREIE_ADRESSE = "ueberspringen", "frei"

AKTION_TEXT = {UEBERSPRINGEN: "überspringen", FREIE_ADRESSE: "auf freie Adresse"}


@dataclass
class Eintrag:
    index: int
    geraet: MvrGeraet
    typ: GdtfTyp | None = None
    gdtf_modus: GdtfModus | None = None
    art: str = NICHT_ZUGEORDNET
    profil: T.Profil | None = None
    modus: T.Modus | None = None
    kanaele: int | None = None
    #: Wo das Geraet angelegt wird (nach Konfliktwahl).
    universum: int | None = None
    adresse: int | None = None
    #: Konflikt/fehlende Adresse im Klartext ("" = keiner).
    konflikt: str = ""
    #: Gewaehlte Aktion fuer den Konflikt (nur wenn ``konflikt``).
    aktion: str = ""
    status: str = OFFEN
    gruende: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    name: str = ""
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def typ_text(self) -> str:
        g = self.geraet
        if self.typ is not None:
            modus = self.gdtf_modus.name if self.gdtf_modus else (g.gdtf_modus or "?")
            return f"{self.typ.anzeige} · {modus}"
        return g.gdtf_datei or "— ohne GDTF —"

    @property
    def profil_text(self) -> str:
        if self.art == NEU:
            return (f"neu aus GDTF: {self.typ.anzeige} · {self.gdtf_modus.name} "
                    f"({self.kanaele} Kanäle)")
        if self.profil is not None and self.modus is not None:
            return f"{self.profil.anzeige} · {self.modus.name} ({self.modus.kanaele} Kanäle)"
        return "nicht zugeordnet"

    @property
    def adresse_text(self) -> str:
        if self.status == ANLEGBAR and self.universum is not None:
            return f"{self.universum}.{self.adresse}"
        g = self.geraet
        if g.hat_adresse:
            return f"{g.universum}.{g.adresse}"
        return g.adresse_text or "—"

    @property
    def status_text(self) -> str:
        if self.status == ANLEGBAR:
            text = "wird angelegt"
            if self.konflikt:
                text += f" auf {self.universum}.{self.adresse} — {self.konflikt}"
        elif self.status == UEBERSPRUNGEN:
            text = "wird übersprungen — " + " ".join(self.gruende)
        else:
            text = "offen — " + " ".join(self.gruende)
        if self.hinweise:
            text += "  Hinweis: " + " ".join(self.hinweise)
        return text


@dataclass
class Plan:
    datei: MvrDatei
    eintraege: list[Eintrag]
    wahl: dict[int, tuple]
    konflikt_wahl: dict[int, str]

    def anlegbare(self) -> list[Eintrag]:
        return [e for e in self.eintraege if e.status == ANLEGBAR]

    def neue_typen(self) -> list[GdtfTyp]:
        """GDTF-Typen, aus denen beim Anwenden ein Profil entsteht (je einmal)."""
        gesehen, aus = set(), []
        for e in self.anlegbare():
            if e.art == NEU and e.typ.datei not in gesehen:
                gesehen.add(e.typ.datei)
                aus.append(e.typ)
        return aus

    def zaehlerzeile(self) -> str:
        n = len(self.anlegbare())
        teile = ["Kein Gerät wird angelegt" if n == 0
                 else "1 Gerät wird angelegt" if n == 1
                 else f"{n} Geräte werden angelegt"]
        neu = len(self.neue_typen())
        if neu:
            teile.append(f"{neu} Profil{'e' if neu > 1 else ''} neu aus GDTF")
        offen = sum(1 for e in self.eintraege if e.status == OFFEN)
        if offen:
            teile.append(f"{offen} nicht zugeordnet")
        weg = sum(1 for e in self.eintraege if e.status == UEBERSPRUNGEN)
        if weg:
            teile.append(f"{weg} übersprungen")
        konflikte = sum(1 for e in self.eintraege if e.konflikt)
        if konflikte:
            teile.append(f"{konflikte} mit Adresskonflikt")
        return ", ".join(teile)


# ── Zuordnung ────────────────────────────────────────────────────────────────

def _v(text: str) -> str:
    return T._ohne_leer(text)


def finde_profil(bibliothek: T.Bibliothek, typ: GdtfTyp,
                 gmodus: GdtfModus) -> tuple[T.Profil, T.Modus, str] | None:
    """Bibliotheksprofil zu GDTF-Typ + Modus: Hersteller + Modell (Name oder
    Langname) + Kanalzahl, ohne Gross/Klein und Leerzeichen. Rueckgabe
    ``(Profil, Modus, Hinweis)`` oder ``None``."""
    h = _v(typ.hersteller)
    roh = [n for n in (typ.name, typ.langname) if n]
    if not roh:
        # Ohne Name/LongName heisst das neu angelegte Profil wie die GDTF-Datei
        # (gdtf_profil.profil_payload) — sonst entstuende bei jedem Import ein
        # weiteres, gleiches Profil.
        roh = [typ.datei] if typ.datei else []
    namen = {_v(n) for n in roh}
    if not namen:
        return None
    k = gmodus.kanalzahl
    treffer = []
    for p in bibliothek.profile:
        passt = ((_v(p.name) in namen and (not h or _v(p.hersteller) == h))
                 or _v(p.anzeige) in {_v(f"{typ.hersteller} {n}") for n in
                                      roh})
        if not passt:
            continue
        gleich = [m for m in p.modi if m.kanaele == k]
        nach_name = [m for m in gleich if _v(m.name) == _v(gmodus.name)]
        if len(nach_name) >= 1:
            treffer.append((p, nach_name[0]))
        elif len(gleich) == 1:
            treffer.append((p, gleich[0]))
    if not treffer:
        return None
    hinweis = ""
    if len(treffer) > 1:
        treffer.sort(key=lambda t: t[0].id)
        hinweis = (f"{len(treffer)} Profile passen (Hersteller, Modell, "
                   f"{k} Kanäle) — das älteste ist gewählt.")
    return treffer[0][0], treffer[0][1], hinweis


def _zuordnen(e: Eintrag, datei: MvrDatei, bibliothek: T.Bibliothek, gewaehlt,
              funde: dict | None = None) -> None:
    g = e.geraet
    e.typ = datei.typ_fuer(g)
    if e.typ is not None:
        e.gdtf_modus = e.typ.modus(g.gdtf_modus)
    if gewaehlt:
        profil = bibliothek.profil(gewaehlt[0])
        modus = profil.modus(gewaehlt[1], *(gewaehlt[2:3])) if profil else None
        if profil is not None and modus is not None:
            e.art, e.profil, e.modus, e.kanaele = GEWAEHLT, profil, modus, modus.kanaele
            return
    if e.typ is None:
        if not g.gdtf_datei:
            e.gruende.append("In der Datei steht kein Gerätetyp (GDTF) — bitte "
                             "ein Profil wählen.")
        else:
            e.gruende.append((datei.gdtf_fehler.get(g.gdtf_datei)
                              or f"Die GDTF-Datei „{g.gdtf_datei}“ fehlt.")
                             + " Bitte ein Profil wählen.")
        return
    if e.gdtf_modus is None:
        e.gruende.append(
            f"Den Modus „{g.gdtf_modus}“ gibt es in der GDTF nicht "
            f"({', '.join(m.name for m in e.typ.modi) or 'keine Modi'}) — bitte "
            "ein Profil wählen.")
        return
    if e.gdtf_modus.kanalzahl <= 0:
        e.gruende.append(f"Der Modus „{e.gdtf_modus.name}“ hat keine DMX-Kanäle "
                         "— bitte ein Profil wählen.")
        return
    # Je GDTF-Datei und Modus EINMAL suchen (sonst durchsucht jedes Geraet
    # die ganze Bibliothek — bei tausenden Geraeten Minuten).
    schluessel = (e.typ.datei, id(e.gdtf_modus))
    if funde is not None and schluessel in funde:
        fund = funde[schluessel]
    else:
        fund = finde_profil(bibliothek, e.typ, e.gdtf_modus)
        if funde is not None:
            funde[schluessel] = fund
    if fund is not None:
        e.art, e.profil, e.modus = BIBLIOTHEK, fund[0], fund[1]
        e.kanaele = fund[1].kanaele
        if fund[2]:
            e.hinweise.append(fund[2])
        return
    e.art, e.kanaele = NEU, e.gdtf_modus.kanalzahl


# ── Adressen ─────────────────────────────────────────────────────────────────

class _Belegung:
    def __init__(self, vorhandene):
        self.bereiche: dict[int, list[tuple[int, int, str]]] = {}
        #: (ab_universum, k) -> (Stelle in der Suchreihenfolge, Adresse):
        #: Belegung waechst nur, also rueckt der erste freie Platz fuer ``k``
        #: Kanaele nie nach vorn — die Suche darf dort weitermachen.
        self._ab: dict[tuple[int, int], tuple[int, int]] = {}
        for b in vorhandene:
            if getattr(b, "belegt_dmx", True) and b.kanaele > 0:
                self.dazu(b.universum, b.adresse, b.kanaele, b.name)

    def dazu(self, u, a, k, name):
        bisect.insort(self.bereiche.setdefault(u, []), (a, a + k - 1, name))

    def trifft(self, u, a, k) -> list[tuple[int, int, str]]:
        ende = a + k - 1
        return [b for b in self.bereiche.get(u, []) if b[0] <= ende and a <= b[1]]

    def frei(self, ab_universum: int, k: int) -> tuple[int, int] | None:
        # CDX-73: nie ausserhalb 1..UNIVERSUM_MAX suchen — ein Geraet auf
        # Universum 100 sucht ab dem letzten erlaubten Universum.
        start = min(max(1, ab_universum), UNIVERSUM_MAX)
        reihe = list(range(start, UNIVERSUM_MAX + 1)) + list(range(1, start))
        stelle, ab = self._ab.get((start, k), (0, 1))
        for i in range(stelle, len(reihe)):
            u = reihe[i]
            a = ab if i == stelle else 1
            for s, ende, _n in self.bereiche.get(u, []):
                if ende < a:
                    continue
                if s - a >= k:
                    break
                a = max(a, ende + 1)
            if a + k - 1 <= UNIVERSUM_GROESSE:
                self._ab[(start, k)] = (i, a)
                return u, a
        self._ab[(start, k)] = (len(reihe), 1)
        return None


def _adressieren(e: Eintrag, belegung: _Belegung, wahl: str | None) -> None:
    g, k = e.geraet, e.kanaele
    problem = ""
    if not g.hat_adresse:
        problem = "In der Datei steht keine Adresse." if not g.adresse_text else \
            f"Die Adresse „{g.adresse_text}“ ist unlesbar."
        standard = FREIE_ADRESSE
    elif g.universum > UNIVERSUM_MAX:
        problem = (f"Universum {g.universum} gibt es in LightOS nicht "
                   f"(höchstens {UNIVERSUM_MAX}).")
        standard = UEBERSPRINGEN
    elif g.adresse + k - 1 > UNIVERSUM_GROESSE:
        problem = (f"{k} Kanäle ab Adresse {g.adresse} passen nicht in das "
                   "Universum.")
        standard = UEBERSPRINGEN
    else:
        getroffen = belegung.trifft(g.universum, g.adresse, k)
        if not getroffen:
            e.universum, e.adresse, e.status = g.universum, g.adresse, ANLEGBAR
            belegung.dazu(g.universum, g.adresse, k, e.name)
            return
        namen = ", ".join(f"„{n}“ ({g.universum}.{s}–{ende})"
                          for s, ende, n in getroffen[:3])
        mehr = f" und {len(getroffen) - 3} weitere" if len(getroffen) > 3 else ""
        problem = (f"{g.universum}.{g.adresse}–{g.adresse + k - 1} überschneidet "
                   f"sich mit {namen}{mehr}.")
        standard = UEBERSPRINGEN
    e.konflikt = problem
    e.aktion = wahl if wahl in (UEBERSPRINGEN, FREIE_ADRESSE) else standard
    if e.aktion == UEBERSPRINGEN:
        e.status = UEBERSPRUNGEN
        e.gruende.append(problem)
        return
    frei = belegung.frei(g.universum or 1, k)
    if frei is None:
        e.status = UEBERSPRUNGEN
        e.gruende.append(problem + " Es gibt keine freie Adresse mehr.")
        return
    e.universum, e.adresse = frei
    e.status = ANLEGBAR
    belegung.dazu(frei[0], frei[1], k, e.name)


# ── Plan ─────────────────────────────────────────────────────────────────────

def baue_plan(datei: MvrDatei, bibliothek: T.Bibliothek, vorhandene=(),
              wahl: dict[int, tuple] | None = None,
              konflikt_wahl: dict[int, str] | None = None) -> Plan:
    """Aus Datei + Bibliothek + vorhandenem Patch den Plan rechnen.

    ``wahl``: ``{Index: (Profil-ID, Modusname[, Kanalzahl])}`` fuer Geraete,
    denen der Nutzer ein Profil gibt (auch statt einer automatischen
    Zuordnung). ``konflikt_wahl``: ``{Index: UEBERSPRINGEN|FREIE_ADRESSE}``."""
    wahl = dict(wahl or {})
    konflikt_wahl = dict(konflikt_wahl or {})
    vorhandene = list(vorhandene)
    belegung = _Belegung(vorhandene)
    namen = {T.namens_schluessel(b.name) for b in vorhandene}
    merker: dict = {}
    funde: dict = {}
    eintraege = []
    for i, g in enumerate(datei.geraete):
        e = Eintrag(index=i, geraet=g, hinweise=list(g.hinweise))
        e.position, e.rotation = mvr_zu_lightos(g.matrix)
        if ist_gespiegelt(g.matrix):
            e.hinweise.append("Die Lage ist in der Datei gespiegelt — LightOS "
                              "übernimmt nur die Strahlrichtung, nicht die "
                              "Spiegelung.")
        _zuordnen(e, datei, bibliothek, wahl.get(i), funde)
        e.name = g.name
        if e.kanaele:
            _adressieren(e, belegung, konflikt_wahl.get(i))
        if e.status == ANLEGBAR:
            if T.namens_schluessel(e.name) in namen:
                neu = T.naechster_freier_name(e.name, namen, merker)
                e.hinweise.append(f"Name gab es schon, heißt jetzt „{neu}“.")
                e.name = neu
            namen.add(T.namens_schluessel(e.name))
        eintraege.append(e)
    return Plan(datei=datei, eintraege=eintraege, wahl=wahl,
                konflikt_wahl=konflikt_wahl)


# ── Anwenden ─────────────────────────────────────────────────────────────────

@dataclass
class Ergebnis:
    fids: list[int] = field(default_factory=list)
    neue_profile: list[str] = field(default_factory=list)
    ausgelassen: int = 0
    fehler: list[str] = field(default_factory=list)
    #: True = nichts wurde veraendert (Abbruch mit Ruecknahme).
    zurueckgenommen: bool = False

    @property
    def geraete(self) -> int:
        return len(self.fids)


def _profile_anlegen(typen: list[GdtfTyp], engine=None) -> dict[str, T.Profil]:
    """Je GDTF-Typ ein Bibliotheksprofil. Rueckgabe: Dateiname -> Profil
    (mit den Modusnamen, wie sie in der DB stehen)."""
    from sqlalchemy.orm import Session

    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureMode, FixtureProfile

    eng = engine if engine is not None else fdb.engine()
    aus: dict[str, T.Profil] = {}
    try:
        for typ in typen:
            payload = GP.profil_payload(typ)
            pid = fdb.create_user_profile(payload, engine=eng)
            with Session(eng) as s:
                prof = s.get(FixtureProfile, pid)
                prof.provenance = f"{GP.HERKUNFT} · {typ.datei}"[:200]
                s.commit()
                modi = (s.query(FixtureMode).filter_by(fixture_id=pid)
                        .order_by(FixtureMode.id).all())
                profil = T.Profil(
                    id=pid, hersteller=payload["manufacturer"], name=payload["name"],
                    typ=payload["fixture_type"],
                    modi=tuple(T.Modus(m.name, int(m.channel_count or 0)) for m in modi))
            aus[typ.datei] = profil
    except Exception:
        profile_loeschen([p.id for p in aus.values()], engine=eng)
        raise
    return aus


def profile_loeschen(ids, engine=None) -> None:
    """Neu angelegte Profile wieder entfernen (Ruecknahme bei Abbruch)."""
    if not ids:
        return
    from sqlalchemy.orm import Session

    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureProfile

    eng = engine if engine is not None else fdb.engine()
    with Session(eng) as s:
        for pid in ids:
            prof = s.get(FixtureProfile, pid)
            if prof is not None:
                s.delete(prof)
        s.commit()


def _modus_zum_gdtf(profil: T.Profil, gmodus: GdtfModus, typ: GdtfTyp) -> T.Modus:
    """Der DB-Modus zu einem GDTF-Modus eines gerade angelegten Profils —
    ueber die Reihenfolge (doppelte Namen heissen in der DB „Name (2)“)."""
    angelegte = [m for m in typ.modi if m.kanalzahl > 0]
    i = next(i for i, m in enumerate(angelegte) if m is gmodus)
    return profil.modi[i]


def wende_an(state, plan: Plan, bibliothek: T.Bibliothek, *, engine=None) -> Ergebnis:
    """Die anlegbaren Geraete anlegen und im 3D platzieren — EIN
    Rueckgaengig-Schritt, alles oder nichts.

    Der Plan wird vorher gegen den JETZIGEN Patch neu gerechnet."""
    from src.core.database.models import PatchedFixture
    from src.core.undo import Command, get_undo_stack

    frisch = baue_plan(plan.datei, bibliothek, T.belegung_aus_state(state),
                       plan.wahl, plan.konflikt_wahl)
    anlegbar = frisch.anlegbare()
    ergebnis = Ergebnis(ausgelassen=len(frisch.eintraege) - len(anlegbar))
    if not anlegbar:
        return ergebnis
    try:
        neue = _profile_anlegen(frisch.neue_typen(), engine=engine)
    except Exception as e:
        ergebnis.fehler.append(f"Die neuen Profile ließen sich nicht anlegen: {e}. "
                               "Es wurde nichts verändert.")
        ergebnis.zurueckgenommen = True
        return ergebnis
    ergebnis.neue_profile = [p.anzeige for p in neue.values()]

    stack = get_undo_stack()
    oben_vorher = stack._undo[-1] if stack._undo else None
    etikett = (f"MVR-Import: {len(anlegbar)} Gerät"
               + ("e" if len(anlegbar) != 1 else ""))
    sammeln = getattr(state, "patch_sammeln", None) or nullcontext
    fehler: Exception | None = None
    angelegt: list[tuple[int, Eintrag]] = []
    try:
        with sammeln(), stack.gruppe(etikett, rahmen=sammeln):
            try:
                dual: dict[tuple[int, str], bool] = {}
                for e in anlegbar:
                    if e.art == NEU:
                        profil = neue[e.typ.datei]
                        modus = _modus_zum_gdtf(profil, e.gdtf_modus, e.typ)
                    else:
                        profil, modus = e.profil, e.modus
                    # Je Profil+Modus EINMAL in der Bibliothek nachsehen.
                    if (profil.id, modus.name) not in dual:
                        dual[(profil.id, modus.name)] = T._auto_dual_tilt(
                            profil.id, modus.name)
                    fid = state.add_fixture(PatchedFixture(
                        fid=state.next_fid(), label=e.name,
                        fixture_profile_id=profil.id, mode_name=modus.name,
                        universe=e.universum, address=e.adresse,
                        channel_count=modus.kanaele,
                        manufacturer_name=profil.hersteller,
                        fixture_name=profil.name, fixture_type=profil.typ,
                        spider_dual_tilt=dual[(profil.id, modus.name)]))
                    angelegt.append((fid, e))
                lagen = {fid: (e.position, e.rotation) for fid, e in angelegt}
                setzen = _lagen_setzer(state, lagen)
                setzen()
                stack.push(Command(label="MVR-Import: Positionen", do=setzen,
                                   undo=_lagen_entferner(state, list(lagen))),
                           execute=False)
            except Exception as e:
                fehler = e
    except Exception as e:      # Neuaufbau am Ende (patch_sammeln) scheiterte
        fehler = fehler or e
    if fehler is not None:
        if stack._undo and stack._undo[-1] is not oben_vorher:
            stack.undo()
            if stack._redo:
                stack._redo.pop()      # kein Wiederholen eines Abbruchs
        try:
            profile_loeschen([p.id for p in neue.values()], engine=engine)
        except Exception:
            pass
        ergebnis.fehler.append(f"Der Import wurde abgebrochen und ganz "
                               f"zurückgenommen: {fehler}")
        ergebnis.zurueckgenommen = True
        ergebnis.neue_profile = []
        return ergebnis
    ergebnis.fids = [fid for fid, _e in angelegt]
    return ergebnis


def _ansichts_pause(state):
    reg = getattr(state, "_view_registry", None)
    return reg.suspend() if reg is not None else nullcontext()


def _lagen_setzer(state, lagen: dict):
    def setzen():
        with _ansichts_pause(state):
            pos, rot = state.visualizer_positions, state.visualizer_rotations
            for fid, (p, r) in lagen.items():
                pos[fid] = p          # ZUERST die Position (sonst Phantom-Knoten)
                if any(abs(w) > 1e-9 for w in r):
                    rot[fid] = r
    return setzen


def _lagen_entferner(state, fids: list[int]):
    def entfernen():
        with _ansichts_pause(state):
            pos = state.visualizer_positions
            for fid in fids:
                pos.pop(fid, None)
    return entfernen
