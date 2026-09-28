"""Einmessen eines Moving Heads am echten Rig (VIZ-55 Stufe A + B).

Die Bedienung (so vom Rig-Betreiber formuliert): „Moving Head 2 zeigt ein
bisschen zu weit oben, dann schieb ich ihn ein bisschen runter." Darunter liegen
zwei Stufen, beide 2026-08-26 entschieden, in dieser Reihenfolge:

**Stufe A — Korrektur-Versatz.** Die erste Korrektur wird als Pan/Tilt-Versatz
je Geraet gemerkt (``aim_offset_pan``/``aim_offset_tilt`` in
``patched_fixtures``, DMX-Einheiten als Kommazahl, also 16-Bit-genau). Er wirkt
wie eine Verschiebung des Nullpunkts: :func:`effektive_nullpunkte` ist die EINE
Stelle, an der Nullpunkt und Versatz zusammenkommen — Zielen, Nachfahren, 3D und
2D lesen sie alle ueber diese Funktion, damit Bild und Geraet nicht wieder
auseinanderlaufen (die Lehre aus VIZ-55 Slice 1). Sofort wirksam, reicht fuer den
Abend — **gilt aber streng nur fuer den einen Zielpunkt**: haengt der Kopf in
Wahrheit 40 cm woanders, ist der Fehler bei nahem Ziel gross und bei fernem klein.

**Stufe B — echte Position.** Ab vier Korrekturen an verschiedenen Punkten
rechnet :func:`loese_position` zurueck, wo der Kopf wirklich haengt und wie er
gedreht ist. Danach stimmt es UEBERALL, auch an nie angetippten Punkten, und das
3D-Bild stimmt mit. Der Versatz aus Stufe A wird dabei auf 0 gesetzt — er war nur
die Notloesung fuer einen falschen Standort.

Alles hier ist reine Geometrie: pruefbar, indem man eine bekannte Abweichung
kuenstlich einbaut und nachsieht, ob sie herausgerechnet wird
(``tests/test_viz55_einmessen.py``). Die Abnahme am Rig steht aus.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from src.core.stage.aim import _aim_dmx

#: Mindestabstand zweier Messpunkte, damit sie als VERSCHIEDEN zaehlen (Meter).
#: Zwei fast gleiche Punkte liefern dem Loeser keine neue Information.
MIN_ABSTAND_M = 0.30

#: So viele verschiedene Messpunkte braucht Stufe B. Drei reichen zum Rechnen
#: (6 Unbekannte, je Punkt 2 Gleichungen), aber nicht zum PRUEFEN — ab vier gibt
#: es die Gegenprobe (:func:`_gegenprobe_cm`). Weniger -> keine Loesung.
MIN_PUNKTE = 4


def normiere_versatz(value) -> float:
    """Einmess-Versatz als endliche Kommazahl, sonst 0 (nie eingemessen); auf
    +-64 DMX begrenzt — groesser ist kein Versatz mehr, sondern ein falscher
    Standort, und dafuer gibt es die Positions-Loesung. Die EINE Normalisierung
    fuer Show-Datei und ``update_fixture``."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v or v in (float("inf"), float("-inf")):
        return 0.0
    return max(-64.0, min(64.0, v))


def effektive_nullpunkte(f) -> tuple[float, float]:
    """Pan/Tilt-Nullpunkt (DMX, Kommazahl) inkl. gemerktem Einmess-Versatz.

    Geraete ohne Versatz (Alt-Shows, frisch gepatcht) liefern exakt den
    konfigurierten Nullpunkt — byte-gleiches Verhalten fuer alle, die nie
    eingemessen haben."""
    def _f(name, default):
        try:
            v = getattr(f, name, default)
            return float(default if v is None else v)
        except (TypeError, ValueError):
            return float(default)
    # Nur ein FEHLENDER Wert wird 128; eine echte 0 bleibt 0. Bis 2026-09-28 las
    # das Zielen hier ``or 128`` (0 -> 128), 3D und 2D liessen die 0 stehen —
    # dasselbe Geraet stand in beiden Welten verschieden. Jetzt eine Regel fuer alle.
    pz = _f("pan_zero_dmx", 128)
    tz = _f("tilt_zero_dmx", 128)
    return (pz + _f("aim_offset_pan", 0.0), tz + _f("aim_offset_tilt", 0.0))


def aim_kw(f) -> dict:
    """Die Geraete-Parameter fuer ``aim_pan_tilt``/``aim_pan_tilt_16`` — mit
    effektivem Nullpunkt. Dieselben Defaults wie bisher im Visualizer-Handler."""
    pz, tz = effektive_nullpunkte(f)
    return dict(
        pan_range_deg=float(getattr(f, "pan_range_deg", 540) or 540),
        tilt_range_deg=float(getattr(f, "tilt_range_deg", 270) or 270),
        pan_zero_dmx=pz,
        tilt_zero_dmx=tz,
    )


@dataclass(frozen=True)
class Messpunkt:
    """Eine Korrektur: bei diesen Pan/Tilt-Werten (16 Bit, MODELL-Werte wie im
    Programmer) trifft der echte Kopf ``ziel`` (Meter)."""
    ziel: tuple[float, float, float]
    pan16: int
    tilt16: int


def versatz_aus_korrektur(ist16: tuple[int, int], soll16_ohne_versatz: tuple[int, int]
                          ) -> tuple[float, float]:
    """Stufe A: der Versatz (DMX, Kommazahl), der das Zielen fuer diesen Punkt
    genau auf ``ist16`` bringt. ``soll16_ohne_versatz`` ist, was das Zielen OHNE
    Versatz geliefert haette — sonst wuerde eine zweite Korrektur die erste
    aufaddieren statt ersetzen."""
    return ((ist16[0] - soll16_ohne_versatz[0]) / 256.0,
            (ist16[1] - soll16_ohne_versatz[1]) / 256.0)


def verschiedene(messpunkte: list[Messpunkt]) -> list[Messpunkt]:
    """Messpunkte, die mindestens :data:`MIN_ABSTAND_M` auseinanderliegen. Bei
    zwei nahen Punkten gilt der JUENGERE — er ist die spaetere, bessere Korrektur."""
    out: list[Messpunkt] = []
    for m in reversed(messpunkte):
        if all(math.dist(m.ziel, o.ziel) >= MIN_ABSTAND_M for o in out):
            out.append(m)
    out.reverse()
    return out


@dataclass(frozen=True)
class Loesung:
    pos: tuple[float, float, float]
    rot: tuple[float, float, float]
    modus: str                # "voll" (Position + ganze Drehung) | "gierung" (Position + Hochachse)
    punkte: int               # so viele verschiedene Messpunkte gingen ein
    rest_grad: float          # groesster Restfehler ueber alle Messpunkte (Grad)
    gegenprobe_cm: float      # schlimmster Fehler an einem jeweils weggelassenen Punkt
    verschiebung_m: float     # wie weit die Loesung vom bisherigen Standort liegt
    drehung_grad: float       # Winkel der Gesamtdrehung gegenueber der bisherigen Montage


#: Groesster erlaubter Restfehler (Grad): passen die Korrekturen ueberhaupt zu
#: EINEM Standort? Die eigentliche Guete sichert die Gegenprobe.
MAX_REST_GRAD = 0.5


def _drehung(p_rot, R0, modus):
    from src.core.stage.aim import _matmul, _mount_matrix, _ry
    if modus == "gierung":
        D = _ry(math.radians(p_rot[0]))
    else:
        D = _mount_matrix(*p_rot)
    return _matmul(D, R0)


def _strahl(R, pan16: int, tilt16: int, kw) -> tuple[float, float, float]:
    """Welt-Richtung des Strahls bei diesen 16-Bit-Werten — die Vorwaertsrechnung
    zu ``aim._aim_dmx`` (dieselbe Winkelformel wie das 3D)."""
    p, t = pan16 / 256.0, tilt16 / 256.0
    pr = math.radians((p - kw["pan_zero_dmx"]) / 128.0 * kw["pan_range_deg"] / 2.0)
    tr = math.radians((t - kw["tilt_zero_dmx"]) / 128.0 * kw["tilt_range_deg"] / 2.0)
    d = (-math.sin(tr) * math.sin(pr), -math.cos(tr), -math.sin(tr) * math.cos(pr))
    return tuple(R[i][0] * d[0] + R[i][1] * d[1] + R[i][2] * d[2] for i in range(3))


def _residuen(pos, R, messpunkte, kw):
    """Je Messpunkt: wie weit verfehlt der Strahl bei den EINGESTELLTEN Werten,
    vom angenommenen Standort aus, das Ziel? Als Richtungsdifferenz in Grad
    (3 Komponenten, Rang 2).

    Bewusst NICHT als Pan/Tilt-Differenz in DMX: zeigt der Strahl fast senkrecht
    (Tilt ~ 0), ist Pan dort bedeutungslos — eine grosse Pan-Differenz waere dann
    kaum ein Richtungsfehler, und der Loeser blieb an solchen Punkten haengen
    (gemessen: 8,8 Grad Rest bei rauschfreien Daten). Und es braucht so keine
    Rueckrechnung (IK) mit ihren Bereichsgrenzen."""
    out = []
    for m in messpunkte:
        d = _strahl(R, m.pan16, m.tilt16, kw)
        s = [m.ziel[k] - pos[k] for k in range(3)]
        n = math.sqrt(s[0] * s[0] + s[1] * s[1] + s[2] * s[2]) or 1e-9
        out.extend(math.degrees(d[k] - s[k] / n) for k in range(3))
    return out


def _rest_grad(pos, R, messpunkte, kw) -> float:
    """Groesster Winkel (Grad) zwischen Strahl und Zielrichtung ueber alle Punkte."""
    worst = 0.0
    for m in messpunkte:
        d = _strahl(R, m.pan16, m.tilt16, kw)
        s = [m.ziel[k] - pos[k] for k in range(3)]
        n = math.sqrt(sum(x * x for x in s)) or 1e-9
        c = max(-1.0, min(1.0, sum(d[k] * s[k] / n for k in range(3))))
        worst = max(worst, math.degrees(math.acos(c)))
    return worst


def _loese(pts, start_pos, R0, kw, modus, iterationen=200):
    """Levenberg-Marquardt ueber Position + Zusatzdrehung IN WELTKOORDINATEN auf
    die bisherige Montage ``R0`` — so ist „Hochachse" bei stehenden, haengenden
    und Wand-Geraeten dieselbe, und es gibt keine Euler-Singularitaet am Start."""
    n_rot = 1 if modus == "gierung" else 3
    p0 = [float(v) for v in start_pos] + [0.0] * n_rot
    h = [1e-3] * 3 + [1e-2] * n_rot
    # Leichte Bindung an den Start: die KLEINSTE Aenderung, die alles trifft.
    w = [0.01] * 3 + [0.0001] * n_rot

    def res(q):
        R = _drehung(q[3:], R0, modus)
        return (_residuen((q[0], q[1], q[2]), R, pts, kw)
                + [wi * (qi - si) for wi, qi, si in zip(w, q, p0)])

    def kosten(q):
        return sum(x * x for x in res(q))

    p = list(p0)
    c = kosten(p)
    lam = 1e-2
    m = len(p)
    for _ in range(iterationen):
        r = res(p)
        J = []
        for j in range(m):
            q = list(p)
            q[j] += h[j]
            J.append([(a - b) / h[j] for a, b in zip(res(q), r)])
        JTJ = [[sum(J[a][k] * J[b][k] for k in range(len(r))) for b in range(m)] for a in range(m)]
        JTr = [sum(J[a][k] * r[k] for k in range(len(r))) for a in range(m)]
        verbessert = False
        for _v in range(12):
            A = [[JTJ[a][b] + (lam * JTJ[a][a] + 1e-12 if a == b else 0.0) for b in range(m)]
                 for a in range(m)]
            dp = _loese_linear(A, [-x for x in JTr])
            if dp is None:
                lam *= 10.0
                continue
            q = [pi + di for pi, di in zip(p, dp)]
            cq = kosten(q)
            if cq < c:
                p, c = q, cq
                lam = max(lam / 10.0, 1e-9)
                verbessert = True
                break
            lam *= 10.0
        if not verbessert or c < 1e-14:
            break
    R = _drehung(p[3:], R0, modus)
    return (p[0], p[1], p[2]), R, _rest_grad((p[0], p[1], p[2]), R, pts, kw)


#: Mindest-Faecherbreite (Grad) der Zielrichtungen QUER zur Hauptrichtung — s.
#: :func:`faecher_grad`.
MIN_FAECHER_GRAD = 8.0


def faecher_grad(pts, pos) -> tuple[float, float]:
    """Wie weit faechern die Richtungen vom Kopf zu den Messpunkten auf (Grad) —
    entlang der Hauptrichtung und QUER dazu (Wurzeln der zwei groessten
    Eigenwerte der Kovarianz der Einheitsvektoren; geschlossene 3x3-Formel).

    Warum: liegen die Punkte auf einer LINIE (Buehnenkante, Bodenlinie) oder in
    einem schmalen Streifen, passt eine ganze Schar von Standorten gleich gut — und
    die Gegenprobe merkt das grundsaetzlich nicht, weil jede Teilmenge dieselbe
    Mehrdeutigkeit traegt (Befund der Review 2026-09-28: Gegenprobe 0,02 cm, an
    neuen Punkten 18-31 cm daneben). Gemessen (316 Faelle, 4-6 Punkte, 1 cm
    Einstellrauschen, Pruefpunkte im ganzen 55-Grad-Kegel auf 4 m): Linie und
    schmale Streifen (quer 4-6 Grad) bis 130 cm daneben; mit quer >= 8 Grad UND
    Gegenprobe Median 3,1 cm, 95 % < 9,4 cm, max 14,6 cm — der Rest ist
    Extrapolation weit ausserhalb der Messpunkte."""
    us = []
    for m in pts:
        v = [m.ziel[k] - pos[k] for k in range(3)]
        n = math.sqrt(sum(x * x for x in v)) or 1e-9
        us.append([x / n for x in v])
    n = len(us)
    mu = [sum(u[k] for u in us) / n for k in range(3)]
    C = [[sum((u[i] - mu[i]) * (u[j] - mu[j]) for u in us) / n for j in range(3)] for i in range(3)]
    ev = sorted(_eig3_sym(C), reverse=True)
    return (math.degrees(math.sqrt(max(ev[0], 0.0))), math.degrees(math.sqrt(max(ev[1], 0.0))))


def _eig3_sym(A) -> list[float]:
    """Eigenwerte einer symmetrischen 3x3-Matrix (trigonometrische Formel)."""
    p1 = A[0][1] ** 2 + A[0][2] ** 2 + A[1][2] ** 2
    q = (A[0][0] + A[1][1] + A[2][2]) / 3.0
    if p1 < 1e-30:
        return [A[0][0], A[1][1], A[2][2]]
    p2 = (A[0][0] - q) ** 2 + (A[1][1] - q) ** 2 + (A[2][2] - q) ** 2 + 2.0 * p1
    p = math.sqrt(p2 / 6.0)
    B = [[(A[i][j] - (q if i == j else 0.0)) / p for j in range(3)] for i in range(3)]
    detB = (B[0][0] * (B[1][1] * B[2][2] - B[1][2] * B[2][1])
            - B[0][1] * (B[1][0] * B[2][2] - B[1][2] * B[2][0])
            + B[0][2] * (B[1][0] * B[2][1] - B[1][1] * B[2][0]))
    r = max(-1.0, min(1.0, detB / 2.0))
    phi = math.acos(r) / 3.0
    e1 = q + 2.0 * p * math.cos(phi)
    e3 = q + 2.0 * p * math.cos(phi + 2.0 * math.pi / 3.0)
    return [e1, 3.0 * q - e1 - e3, e3]


#: Groesster erlaubter Fehler der Gegenprobe (cm), damit eine Loesung angeboten
#: wird — s. :func:`_gegenprobe_cm`.
MAX_GEGENPROBE_CM = 5.0


def _gegenprobe_cm(pts, start_pos, R0, kw, modus) -> float:
    """Gegenprobe (leave-one-out): jeden Punkt einmal weglassen, die Position aus
    den uebrigen rechnen und nachsehen, wie weit sie den weggelassenen verfehlt
    (cm, in dessen Entfernung). Groesster Wert ueber alle Punkte.

    Das misst genau das Versprechen der Stufe B — nie benutzte Punkte treffen —
    statt es aus einem Modell zu schaetzen. Gemessen (2026-09-28, 600 zufaellige
    Aufbauten, stehend/haengend/Wand, 4-8 Punkte, Montage bis +-3 Grad geneigt):

    ============== ========== =============================== ================
    Einstellfehler angeboten  an NEUEN Punkten                ohne Einmessen
    ============== ========== =============================== ================
    1 cm           79 %       Median 1,6 cm, 95 % < 4,4, max 8,5  Median 46 cm
    2 cm           24 %       Median 3,0 cm, max 12,9             Median 44 cm
    ============== ========== =============================== ================

    Ohne Gegenprobe lagen einzelne Loesungen bis 46 cm daneben. Restfehler und
    eine aus der Ableitungsmatrix geschaetzte Standort-Unsicherheit trennten diese
    Ausreisser NICHT ab (ebenfalls gemessen). ~30 ms je Aufruf."""
    schlimmster = 0.0
    for i in range(len(pts)):
        rest = pts[:i] + pts[i + 1:]
        pos, R, _ = _loese(rest, start_pos, R0, kw, modus)
        m = pts[i]
        d = _strahl(R, m.pan16, m.tilt16, kw)
        s = [m.ziel[k] - pos[k] for k in range(3)]
        n = math.sqrt(sum(x * x for x in s)) or 1e-9
        c = max(-1.0, min(1.0, sum(d[k] * s[k] / n for k in range(3))))
        schlimmster = max(schlimmster, math.acos(c) * n * 100.0)
    return schlimmster


def loese_position(messpunkte: list[Messpunkt], start_pos, start_rot, kw: dict
                   ) -> Loesung | None:
    """Stufe B: Standort + Montage-Drehung, bei denen das Zielen alle Messpunkte
    trifft — nur angeboten, wenn die Gegenprobe haelt.

    ``kw`` sind die Geraete-Parameter OHNE Einmess-Versatz (``pan_zero_dmx`` =
    konfigurierter Nullpunkt): der Versatz ist genau das, was die Loesung ersetzt.

    * Zuerst Position + ganze Drehung („voll"); besteht das die Pruefung nicht,
      Position + Drehung um die Hochachse („gierung", die Neigung der Montage
      gilt dann als bekannt — weniger Unbekannte, weniger Rauschverstaerkung).
    * **Mindestens vier Punkte** (:data:`MIN_PUNKTE`). Aus genau drei laesst sich
      eine Loesung rechnen, aber nicht PRUEFEN: mit realistischem Einstellrauschen
      lag sie gelegentlich 25 cm daneben, ohne dass ein Mass es vorher zeigte.
    * Die Punkte muessen quer aufgefaechert sein (:data:`MIN_FAECHER_GRAD`) —
      eine Linie ist mehrdeutig, das zeigt keine Gegenprobe.
    * Angeboten wird nur mit Restfehler <= :data:`MAX_REST_GRAD` UND Gegenprobe
      <= :data:`MAX_GEGENPROBE_CM`; sonst ``None`` — lieber keine Position als
      eine geratene. Verlaesslich ist sie im BEREICH der Messpunkte; weit
      ausserhalb extrapoliert jede Rechnung."""
    from src.core.stage.aim import _euler_xyz_from_matrix, _mount_matrix
    pts = verschiedene(messpunkte)
    if len(pts) < MIN_PUNKTE:
        return None
    if faecher_grad(pts, start_pos)[1] < MIN_FAECHER_GRAD:
        return None                     # Linie/Streifen: mehrdeutig, s. faecher_grad
    R0 = _mount_matrix(*start_rot)
    for modus in ("voll", "gierung"):
        pos, R, rest = _loese(pts, start_pos, R0, kw, modus)
        if rest > MAX_REST_GRAD:
            continue
        probe = _gegenprobe_cm(pts, start_pos, R0, kw, modus)
        if probe > MAX_GEGENPROBE_CM:
            continue
        D = [[sum(R[i][k] * R0[j][k] for k in range(3)) for j in range(3)] for i in range(3)]
        spur = max(-1.0, min(1.0, (D[0][0] + D[1][1] + D[2][2] - 1.0) / 2.0))
        return Loesung(pos=pos, rot=_euler_xyz_from_matrix(R), modus=modus, punkte=len(pts),
                       rest_grad=rest, gegenprobe_cm=probe,
                       verschiebung_m=math.dist(pos, tuple(start_pos)),
                       drehung_grad=math.degrees(math.acos(spur)))
    return None


def _loese_linear(A, b):
    """Gauss mit Spaltenpivot fuer das kleine 6x6-System; ``None`` bei singulaer."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-15:
            return None
        M[col], M[piv] = M[piv], M[col]
        for r in range(col + 1, n):
            f = M[r][col] / M[col][col]
            for k in range(col, n + 1):
                M[r][k] -= f * M[col][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][k] * x[k] for k in range(i + 1, n))) / M[i][i]
    return x


# ── Die Sitzung: was die Bedienung braucht, ohne Qt ─────────────────────────────

def _kw_ohne_versatz(f) -> dict:
    """Geraete-Parameter mit dem KONFIGURIERTEN Nullpunkt (ohne Einmess-Versatz) —
    der Massstab, gegen den Versatz und Positions-Loesung gerechnet werden."""
    kw = aim_kw(f)
    kw["pan_zero_dmx"] -= float(getattr(f, "aim_offset_pan", 0.0) or 0.0)
    kw["tilt_zero_dmx"] -= float(getattr(f, "aim_offset_tilt", 0.0) or 0.0)
    return kw


def _hat_fein(kanaele, achse: str) -> bool:
    return any((getattr(c, "attribute", "") or "") == f"{achse}_fine" for c in kanaele)


def wert16(state, fid: int, kanaele, achse: str) -> int | None:
    """Aktueller Programmer-Wert einer Achse als 16 Bit (Grob*256 + Fein).
    ``None``, wenn der Programmer die Achse gar nicht fuehrt."""
    grob = state.get_programmer_value(fid, achse)
    if grob is None:
        return None
    fein = state.get_programmer_value(fid, f"{achse}_fine") if _hat_fein(kanaele, achse) else 0
    return int(grob) * 256 + int(fein or 0)


def setze16(state, fid: int, kanaele, achse: str, v16: int) -> None:
    """16-Bit-Wert in den Programmer; ohne Feinkanal auf den naechsten ganzen
    DMX-Schritt gerundet (dann ist ein Schritt eben ein Schritt)."""
    v16 = max(0, min(65535, int(v16)))
    if _hat_fein(kanaele, achse):
        state.set_programmer_value(fid, achse, v16 >> 8)
        state.set_programmer_value(fid, f"{achse}_fine", v16 & 0xFF)
    else:
        state.set_programmer_value(fid, achse, min(255, int(round(v16 / 256.0))))


@dataclass
class Merken:
    """Ergebnis von :meth:`EinmessSitzung.merken`."""
    versatz: tuple[float, float]
    punkte: int                       # verschiedene Messpunkte dieses Geraets
    loesung: "Loesung | None"


class EinmessSitzung:
    """Merkt je Geraet den zuletzt angezielten Punkt und die gesammelten
    Korrekturen. Bewusst NUR im Speicher: eine Einmess-Runde ist ein Abend am
    Rig; was bleiben soll, ist der Versatz bzw. die uebernommene Position — beide
    liegen in Patch bzw. Show. Nach einem Neustart beginnt das Sammeln neu.

    ``punkte[fid]`` ist die ROHE Liste in Reihenfolge; ``_versatz[fid]`` haelt
    parallel den Versatz, den der jeweilige Punkt gesetzt hat. Stimmt der
    aktuelle Versatz des Geraets nicht mehr mit dem des letzten Punkts, wurde das
    „Merken" rueckgaengig gemacht — der Punkt faellt dann aus der Sammlung
    (Review B6: vorher blockierte ein falscher Punkt Stufe B bis zum Zuruecksetzen)."""

    def __init__(self):
        self.ziel: dict[int, tuple[float, float, float]] = {}
        self.punkte: dict[int, list[Messpunkt]] = {}
        self._versatz: dict[int, list[tuple[float, float]]] = {}

    def ziel_gesetzt(self, fid: int, ziel) -> None:
        self.ziel[fid] = (float(ziel[0]), float(ziel[1]), float(ziel[2]))

    def _bereinigen(self, f) -> None:
        jetzt = (float(getattr(f, "aim_offset_pan", 0.0) or 0.0),
                 float(getattr(f, "aim_offset_tilt", 0.0) or 0.0))
        pts = self.punkte.get(f.fid, [])
        vs = self._versatz.get(f.fid, [])
        while pts and vs and (abs(vs[-1][0] - jetzt[0]) > 1e-9 or abs(vs[-1][1] - jetzt[1]) > 1e-9):
            pts.pop()
            vs.pop()

    def anzahl(self, f) -> int:
        """Verschiedene, noch gueltige Messpunkte dieses Geraets."""
        self._bereinigen(f)
        return len(verschiedene(self.punkte.get(f.fid, [])))

    def schiebe(self, state, fid: int, kanaele, achse: str, schritt16: int) -> bool:
        v = wert16(state, fid, kanaele, achse)
        if v is None:
            return False
        if not _hat_fein(kanaele, achse):
            schritt16 = 256 if schritt16 > 0 else -256        # kleiner geht ohne Fein nicht
        setze16(state, fid, kanaele, achse, v + schritt16)
        return True

    def merken(self, state, f, kanaele, pos, rot) -> Merken | None:
        """„Sitzt — merken": der aktuelle Programmer-Wert trifft das zuletzt
        angezielte Ziel. Setzt den Versatz (Stufe A, sofort wirksam, undo-faehig
        ueber ``update_fixture``) und sammelt den Punkt fuer Stufe B.
        ``None``, wenn fuer dieses Geraet noch kein Ziel angetippt wurde.

        Achse OHNE Feinkanal: der Versatz wird auf ganze DMX-Schritte gerundet.
        Der Programmer kennt dort nur ganze Schritte; ohne Rundung speicherte ein
        „Merken" ohne Schieben das Rundungsrauschen (bis +-0,5 Schritt) als
        Versatz, und das Zielen lag danach an anderen Punkten oft einen Schritt
        daneben (Review B3: 1833 von 4000 Faellen)."""
        ziel = self.ziel.get(f.fid)
        if ziel is None:
            return None
        ist = (wert16(state, f.fid, kanaele, "pan"), wert16(state, f.fid, kanaele, "tilt"))
        if None in ist:
            return None
        self._bereinigen(f)
        from src.core.stage.aim import aim_pan_tilt_16
        kw0 = _kw_ohne_versatz(f)
        soll = aim_pan_tilt_16(pos, ziel, rot, **kw0)
        versatz = list(versatz_aus_korrektur(ist, soll))
        for i, achse in enumerate(("pan", "tilt")):
            if not _hat_fein(kanaele, achse):
                versatz[i] = float(round(versatz[i]))
        versatz = (versatz[0], versatz[1])
        state.update_fixture(f.fid, aim_offset_pan=versatz[0], aim_offset_tilt=versatz[1])
        # Mit dem Wert merken, den update_fixture speichert (dieselbe Normalisierung) —
        # NICHT von ``f`` zuruecklesen: im echten AppState aendert update_fixture die
        # Datenbank, nicht das Objekt in der Hand. So gelesen stand hier 0, und beim
        # naechsten Blick fiel der eben gemerkte Punkt wieder heraus (Sichtpruefung
        # 2026-09-28: „0 Punkt(e)" direkt nach dem Merken).
        gesetzt = (normiere_versatz(versatz[0]), normiere_versatz(versatz[1]))
        self.punkte.setdefault(f.fid, []).append(Messpunkt(ziel, ist[0], ist[1]))
        self._versatz.setdefault(f.fid, []).append(gesetzt)
        pts = verschiedene(self.punkte[f.fid])
        return Merken(versatz=versatz, punkte=len(pts),
                      loesung=loese_position(pts, pos, rot, kw0))

    def vergessen(self, state, fid: int) -> None:
        """Versatz auf 0 und gesammelte Punkte weg („Korrektur zuruecksetzen")."""
        state.update_fixture(fid, aim_offset_pan=0.0, aim_offset_tilt=0.0)
        self.punkte.pop(fid, None)
        self._versatz.pop(fid, None)

    def punkte_verwerfen(self, fid: int) -> None:
        """Nur die Sammlung verwerfen (nach „Position uebernehmen", das den Versatz
        selbst im selben Undo-Schritt setzt)."""
        self.punkte.pop(fid, None)
        self._versatz.pop(fid, None)
