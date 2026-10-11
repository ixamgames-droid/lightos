// LAS-32 (Slice S1): Geometrie fuer die Sperrzonen-ANZEIGE — nur Zahlen.
//
// Bewusst importfrei (kein THREE, kein state), wie optics.js/beam_stop.js:
// so laesst sich jede Funktion ohne 3D-Szene aufrufen.
//
// Alles hier rechnet im KOORDINATENSYSTEM DES LASERS: Ursprung im
// Austrittsfenster, +Z = Strahlachse, +X = links aus Sicht des Geraets,
// +Y = oben. Die Feld-Pyramide ist dort
//     z >= 0,  x <= tl*z,  -x <= tr*z,  y <= to*z,  -y <= tu*z
// mit tl/tr/to/tu = tan(Randwinkel + Zuschlag) — dieselben fuenf Halbraeume
// wie feld_ebenen() in Python (src/core/laser/sperrzonen.py). Auch die
// Beschneidung (schneide) ist dieselbe Vorschrift wie dort (_schneide:
// „<= 0 ist innen", Beruehren zaehlt), damit Bild und Meldung nicht
// auseinanderlaufen. Massgeblich bleibt die Rechnung in Python.

export const WINKEL_GESAMT_MAX = 89.0;
export const ZUSCHLAG_MIN = 2.0;
/** Fester Rand um jede Zone (Meter) — wie ZONEN_RAND_M in Python. */
export const ZONEN_RAND_M = 0.10;

function zahl(v, def) {
  const n = Number(v);
  return isFinite(n) ? n : def;
}

/** tan(Randwinkel [+ Zuschlag]) je Seite. */
export function tanWerte(d, mitZuschlag) {
  const z = (mitZuschlag === false) ? 0 : Math.max(ZUSCHLAG_MIN, zahl(d.zuschlag, 5));
  const tan = w => Math.tan(Math.min(WINKEL_GESAMT_MAX, zahl(w, 0) + z) * Math.PI / 180);
  return { l: tan(d.links), r: tan(d.rechts), o: tan(d.oben), u: tan(d.unten) };
}

/** Polygon (Liste von [x,y,z]) am Halbraum f(p) <= 0 beschneiden. */
export function schneide(polygon, f) {
  if (!polygon || !polygon.length) return [];
  const aus = [];
  const abst = polygon.map(f);
  const n = polygon.length;
  for (let i = 0; i < n; i++) {
    const a = polygon[i], b = polygon[(i + 1) % n];
    const da = abst[i], db = abst[(i + 1) % n];
    if (da <= 0) aus.push(a);
    if ((da < 0 && 0 < db) || (db < 0 && 0 < da)) {
      const t = da / (da - db);
      aus.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2])]);
    }
  }
  return aus;
}

/** Die fuenf Halbraeume der Pyramide (Laser-Koordinaten). */
export function feldEbenen(t) {
  return [
    p => -p[2],
    p => -p[0] - t.r * p[2],
    p => p[0] - t.l * p[2],
    p => p[1] - t.o * p[2],
    p => -p[1] - t.u * p[2],
  ];
}

/** Polygon (Laser-Koordinaten) auf die Pyramide beschneiden; `zMax` begrenzt
 *  NUR die Darstellung nach vorn (die Rechnung kennt keine Reichweite). */
export function schneideFeld(polygon, t, zMax) {
  let p = polygon;
  for (const f of feldEbenen(t)) {
    p = schneide(p, f);
    if (!p.length) return p;
  }
  if (typeof zMax === 'number' && isFinite(zMax)) p = schneide(p, q => q[2] - zMax);
  return p;
}

/** Die 8 Ecken eines Quaders um den Ursprung. Reihenfolge wie zonen_ecken()
 *  in Python: Bit 0 = x, Bit 1 = y, Bit 2 = z (jeweils -/+). */
export function quaderEcken(hb, hh, ht) {
  const e = [];
  for (let i = 0; i < 8; i++) {
    e.push([(i & 1) ? hb : -hb, (i & 2) ? hh : -hh, (i & 4) ? ht : -ht]);
  }
  return e;
}

/** Die sechs Flaechen (Ecken-Indizes) und ihre Aussen-Normalen. */
export const FLAECHEN = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
                         [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]];
export const NORMALEN = [[0, 0, -1], [0, 0, 1], [0, -1, 0],
                         [0, 1, 0], [-1, 0, 0], [1, 0, 0]];
/** Die zwoelf Kanten (Ecken-Indizes). */
export const KANTEN = [[0, 1], [2, 3], [4, 5], [6, 7], [0, 2], [1, 3],
                       [4, 6], [5, 7], [0, 4], [1, 5], [2, 6], [3, 7]];

/** Polygon am Quader (um den Ursprung, Halbmasse hb/hh/ht) beschneiden. */
export function schneideQuader(polygon, hb, hh, ht) {
  let p = polygon;
  const h = [hb, hh, ht];
  for (let a = 0; a < 3 && p.length; a++) {
    p = schneide(p, q => q[a] - h[a]);
    p = schneide(p, q => -q[a] - h[a]);
  }
  return p;
}

export function punktImQuader(p, hb, hh, ht) {
  return Math.abs(p[0]) <= hb && Math.abs(p[1]) <= hh && Math.abs(p[2]) <= ht;
}

/** Die vier Kanten-Richtungen der Pyramide (nicht normiert, z = 1):
 *  links-oben, rechts-oben, rechts-unten, links-unten. */
export function kantenRichtungen(t) {
  return [[t.l, t.o, 1], [-t.r, t.o, 1], [-t.r, -t.u, 1], [t.l, -t.u, 1]];
}

/** Die vier Seitenflaechen der Pyramide als (sehr lange) Dreiecke. */
export function seitenDreiecke(t, laenge) {
  const k = kantenRichtungen(t).map(r => [r[0] * laenge, r[1] * laenge, laenge]);
  const s = [0, 0, 0];
  return [[s, k[0], k[1]], [s, k[1], k[2]], [s, k[2], k[3]], [s, k[3], k[0]]];
}

/** Blick des Lasers: Punkt (Laser-Koordinaten, z > 0) -> Bildebene.
 *  u waechst nach RECHTS (aus Sicht des Geraets), v nach oben; Einheit tan. */
export function blick(p) {
  return [-p[0] / p[2], p[1] / p[2]];
}
