// FM-13: EINE Quelle fuer die Pixel-Reihenfolge eines Matrix-Panels (JS-Seite).
//
// Ein Panel adressiert seine Pixel ueber die DMX-Reihenfolge — WO sie sitzen,
// sagt das Profil nicht. Die ADJ Dotz Matrix nummeriert im Werkszustand in
// Schlangenlinien (1-2-3-4 / 8-7-6-5 / ...), der Renderer legte sie dagegen
// zeilenweise an: eine horizontale Lauflicht-Figur laeuft am echten Geraet im
// Zickzack, im 3D aber geradeaus.
//
// Die Python-Seite hat dieselbe Regel in `src/core/pixel_order.py`; ein Test
// haelt beide Fassungen gegeneinander, damit sie nicht auseinanderlaufen
// (zwei parallele Regeln sind eine Drift-Quelle, Lehre FM16E).
//
// WICHTIG: Diese Funktion ist die einzige Stelle, die den DMX-Index in eine
// Rasterposition uebersetzt — sowohl das 3D-Panel (`buildMatrixPanel`) als auch
// das 2D-Top-Down-Icon (`addGridCells`) gehen hier durch. Frueher rechneten
// beide dieselbe Formel getrennt aus.

export const PIXEL_ORDERS = ['rowwise', 'serpentine', 'mirrored'];
export const DEFAULT_PIXEL_ORDER = 'rowwise';

export function normalizePixelOrder(value) {
  const v = String(value || '').trim().toLowerCase();
  return PIXEL_ORDERS.indexOf(v) >= 0 ? v : DEFAULT_PIXEL_ORDER;
}

/**
 * ★ VIZ-51: Pixelzahl -> Rasterform {count, cols, rows, explizit}.
 *
 * Die Formel stand ZWEIMAL — in `buildMatrixPanel` (3D) und in `addGridCells`
 * (2D-Icon), jeweils mit eigener Klemmung auf 1..256. Die FM-13-Zusage „nur
 * eine Stelle rechnet" galt damit fuer die ZELLE (`pixelCell`), nicht fuer die
 * FORM. Zwei Formeln fuer dieselbe Frage sind genau die Drift-Quelle, gegen die
 * dieses Modul angetreten ist: waere eine der beiden je angefasst worden,
 * haetten 2D und 3D dasselbe Panel verschieden geschnitten.
 *
 * ★★ VIZ-50a: `gridCols`/`gridRows` sind die HINTERLEGTE Form aus dem
 * Fixture-Modus (`FixtureMode.grid_cols/grid_rows`). Ohne sie blieb nur der
 * near-square-Rateweg — und der macht aus Robins 4x12-Balken ein 7x7-Quadrat
 * mit 49 Feldern. Fehlt die Angabe (0/undefined), aendert sich nichts:
 * dieselbe Wurzelformel wie bisher, `explizit: false`.
 *
 * `explizit` ist kein Beiwerk, sondern die Bedingung fuer die Panel-MASSE:
 * eine geratene Form darf keine physische Behauptung tragen (s. builders.js).
 */
export function panelGrid(n, gridCols, gridRows) {
  const count = Math.max(1, Math.min(256, Math.floor(n || 16)));
  let c = Math.floor(gridCols || 0);
  let r = Math.floor(gridRows || 0);
  if (c > 0 || r > 0) {
    // Eine der beiden Zahlen genuegt — die andere folgt aus der Pixelzahl.
    if (c <= 0) c = Math.ceil(count / r);
    if (r <= 0) r = Math.ceil(count / c);
    // Das Raster MUSS alle Pixel fassen. Passt die hinterlegte Form nicht zur
    // Pixelzahl des Modus (falsch gepatcht, Profil nachtraeglich geaendert),
    // waeren die ueberzaehligen Pixel sonst ausserhalb des Panels gelandet —
    // sichtbar als Zeilen, die neben dem Gehaeuse schweben.
    r = Math.max(r, Math.ceil(count / c));
    return { count, cols: c, rows: r, explizit: true };
  }
  const cols = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / cols);
  return { count, cols, rows, explizit: false };
}

/** DMX-Pixelindex -> {r, c} im sichtbaren Raster. */
export function pixelCell(index, cols, order) {
  const nc = Math.max(1, Math.floor(cols || 1));
  const i = Math.max(0, Math.floor(index || 0));
  const r = Math.floor(i / nc);
  let c = i % nc;
  const o = normalizePixelOrder(order);
  if (o === 'serpentine' && r % 2 === 1) c = nc - 1 - c;
  else if (o === 'mirrored') c = nc - 1 - c;
  return { r, c };
}


// ── ORIENT (2026-08-05): Zwilling zu core/pixel_order.py ────────────────────
//
// `pixelCell` sagt, wie das GERAET nummeriert. Das hier sagt, wie es HAENGT —
// zwei unabhaengige Aussagen. Ein Panel kann in Schlangenlinien zaehlen UND
// hochkant montiert sein.
//
// Bei 90°/270° tauschen Zeilen und Spalten die Rollen; das Raster selbst
// aendert seine Form. Deshalb gibt `placeElement` `rows`/`cols` MIT zurueck —
// sonst rechnet jeder Aufrufer es wieder selbst, und genau daran laufen zwei
// Fassungen auseinander (FM16E-Lehre).

export const ELEMENT_ROTATIONS = [0, 90, 180, 270];

export function normalizeElementRotation(value) {
  let v = Number(value || 0);
  if (!Number.isFinite(v)) return 0;
  v = ((Math.round(v) % 360) + 360) % 360;
  return ELEMENT_ROTATIONS.indexOf(v) >= 0 ? v : 0;
}

/**
 * ★ VIZ-50b: dieselbe Drehung fuer einen Punkt ZWISCHEN den Rasterzellen.
 *
 * Die Warmweiss-Leiste des ZQ06121 liegt NICHT auf dem Farbraster: sie laeuft
 * mittig zwischen Reihe 2 und 3 (also auf einer halben Zellhoehe) und ihre acht
 * Segmente decken je anderthalb Spalten ab. Ihre Mittelpunkte sind damit
 * GEBROCHENE Rasterkoordinaten — und `rotateCell` floort seine Eingaben, was
 * fuer einen Pixel-Index richtig und fuer 1.5 toedlich ist.
 *
 * Die Drehformel steht deshalb hier EINMAL und `rotateCell` floort davor,
 * statt sie ein zweites Mal hinzuschreiben (FM16E-Lehre: zwei Fassungen
 * derselben Regel laufen auseinander, und zwar genau dann, wenn eine angefasst
 * wird). Die Abbildung ist affin — sie gilt fuer Bruchteile unveraendert.
 *
 * `quer` sagt, ob Zeilen und Spalten die Rollen getauscht haben (90°/270°).
 * Wer eine AUSDEHNUNG mitdrehen muss — das Band ist breit und flach, nach der
 * Drehung schmal und hoch — braucht diese Auskunft; sie aus dem Winkel neu
 * abzuleiten waere wieder die zweite Formel.
 */
export function rotatePoint(row, col, rows, cols, rotation, flip) {
  let r = row, c = col;
  let nr = Math.max(1, Math.floor(rows || 1));
  let nc = Math.max(1, Math.floor(cols || 1));
  const rot = normalizeElementRotation(rotation);
  let quer = false;
  if (rot === 90) {
    const r2 = c, c2 = nr - 1 - r;
    r = r2; c = c2; const t = nr; nr = nc; nc = t; quer = true;
  } else if (rot === 180) {
    r = nr - 1 - r; c = nc - 1 - c;
  } else if (rot === 270) {
    const r2 = nc - 1 - c, c2 = r;
    r = r2; c = c2; const t = nr; nr = nc; nc = t; quer = true;
  }
  if (flip) c = nc - 1 - c;
  return { r: r, c: c, rows: nr, cols: nc, quer: quer };
}

/** (r, c) im gedrehten Raster + dessen neue Groesse. */
export function rotateCell(row, col, rows, cols, rotation, flip) {
  return rotatePoint(Math.floor(row), Math.floor(col), rows, cols, rotation, flip);
}

/** DMX-Index -> endgueltige Position + Rastergroesse.
 *  Reihenfolge wie in Python: erst nummerieren, dann drehen. */
export function placeElement(index, cols, rows, order, rotation, flip) {
  const nc = Math.max(1, Math.floor(cols || 1));
  const nr = Math.max(1, Math.floor(rows || 1));
  const z = pixelCell(index, nc, order);
  return rotateCell(z.r, z.c, nr, nc, rotation, flip);
}
