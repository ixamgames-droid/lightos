// VIZ-92: Pan, Tilt und Gobo-Drehung zwischen zwei DMX-Updates glaetten.
//
// Die Lichtdaten kommen im Push-Takt der Qualitaetsstufe (15/30/44 Hz,
// quality_tiers.js), gerendert wird aber im Bildschirmtakt. Bis VIZ-92 stand
// der Kopf zwischen zwei Updates still und sprang dann — bei einem Gobo-Fade
// (8 Bit, 1,4 Grad je Schritt) sah man das Muster ruckeln, beim Schwenken
// hing der Bodenfleck sichtbar in Stufen hinter der Bewegung her.
//
// Jetzt fuehrt jedes Geraet je Kanal (pan, tilt, gobo) ein kleines Stueck
// Interpolation: von dem Wert, der IM MOMENT DES UPDATES zu sehen waere, zum
// neuen Ziel, ueber genau den Abstand, mit dem die letzten beiden Aenderungen
// ankamen. Bei gleichmaessigem Takt ergibt das eine gleichmaessige Bewegung
// (eine Update-Periode Nachlauf, bei 30 Hz 33 ms).
// ⚠️ Nicht vom zuletzt GEZEICHNETEN Wert starten: das Bild liegt bis zu einem
// Bildabstand vor dem Update, das Stueck wuerde dadurch laenger als sein
// Zeitfenster, und die Schritte je Bild wechselten 1/3 : 2/3 (gemessen im
// Node-Test, bevor es so gebaut war).
//
// Was NICHT geglaettet wird (es bleibt ein Sprung wie bisher):
//   * eine Aenderung nach einer Pause (> GLATT_MAX_MS seit der letzten) —
//     ein Preset-Sprung, ein Cue-Wechsel, das erste Update;
//   * ein Schritt groesser als SPRUNG_RAD — so schnell faehrt kein Kopf,
//     das ist ein bewusster Positionssprung (und haelt Tests deterministisch,
//     die einzelne grosse Schritte schicken);
//   * Helligkeit/Farbe — die gehen nie durch dieses Modul (Blackout bleibt
//     sofort dunkel).
//
// Rein (keine Imports, Zeit wird hereingereicht): Node-Tests laden das Modul
// direkt (tests/test_viz92_gobo_glaettung.py).
"use strict";

/** Laengster Abstand zweier Aenderungen, der noch als laufende Bewegung gilt.
 *  Reicht fuer langsame Fades (ein Gobo-Schritt alle ~1/4 s). */
export const GLATT_MAX_MS = 400;
/** Kuerzester: zwei Aenderungen im selben Moment (ein Batch, ein Test, der
 *  hintereinander schreibt) sind keine Bewegung. */
export const GLATT_MIN_MS = 4;
/** Groesster Schritt je Update, der noch geglaettet wird (~23 Grad). */
export const SPRUNG_RAD = 0.4;

const ZWEI_PI = Math.PI * 2;

/** Winkel-Differenz auf (-pi, pi] falten (kuerzester Weg auf dem Kreis). */
export function kreisDelta(d) {
  let x = d % ZWEI_PI;
  if (x > Math.PI) x -= ZWEI_PI;
  if (x <= -Math.PI) x += ZWEI_PI;
  return x;
}

/** Neuer Kanalzustand. `kreis` = Winkel ohne Anschlag (Gobo-Drehung). */
export function glattKanal(kreis = false) {
  return { kreis: !!kreis, nach: undefined, von: 0, delta: 0, t0: 0, dauer: 0,
           letzt: -Infinity, aktiv: false };
}

/** Neues Ziel melden (Zeit `jetzt` in ms). Liefert true, wenn ab jetzt
 *  interpoliert wird. */
export function glattZiel(k, wert, jetzt) {
  if (typeof wert !== 'number' || !isFinite(wert)) {
    k.nach = undefined; k.aktiv = false; return false;
  }
  if (k.nach === undefined) {                 // erstes Ziel: einfach setzen
    k.nach = wert; k.letzt = jetzt; k.aktiv = false; return false;
  }
  if (wert === k.nach) return k.aktiv;        // unveraendert: laufendes Stueck weiter
  const dt = jetzt - k.letzt;
  k.letzt = jetzt;
  const schritt = k.kreis ? Math.abs(kreisDelta(wert - k.nach)) : Math.abs(wert - k.nach);
  // Startpunkt: was zum Zeitpunkt des Updates zu sehen ist (s. Modulkopf).
  const a = glattWert(k, jetzt);
  k.nach = wert;
  if (!(dt >= GLATT_MIN_MS && dt <= GLATT_MAX_MS) || !(schritt <= SPRUNG_RAD)) {
    k.aktiv = false;                          // Sprung: sofort am Ziel
    return false;
  }
  k.von = a;
  k.delta = k.kreis ? kreisDelta(wert - a) : (wert - a);
  // Liegt die Anzeige weit weg (z. B. nach einem verpassten Bild), lieber
  // springen als durch den halben Kreis fahren.
  if (!(Math.abs(k.delta) <= 2 * SPRUNG_RAD)) { k.aktiv = false; return false; }
  k.t0 = jetzt;
  k.dauer = dt;
  k.aktiv = true;
  return true;
}

/** Wert, der zum Zeitpunkt `jetzt` angezeigt wird. Am Ende genau das Ziel
 *  (kein Rundungsrest), und das Stueck ist danach erledigt. */
export function glattWert(k, jetzt) {
  if (!k.aktiv) return k.nach;
  const p = (jetzt - k.t0) / k.dauer;
  if (!(p < 1)) { k.aktiv = false; return k.nach; }
  if (p <= 0) return k.von;
  return k.von + k.delta * p;
}

// ── Bild-Deckel (Codex #965) ────────────────────────────────────────────────
// Die Glaettung rechnet hoechstens alle `bildMs` einen Schritt fuer ALLE
// bewegten Geraete. Ausnahme: ein Geraet, dessen Ziel ein DMX-Update gerade
// neu gesetzt hat (der DMX-Pfad hat es aufs Ziel gestellt), muss im naechsten
// Bild zurueck auf den Zwischenstand — sonst zeigte das Bild kurz das Ziel.
// Diese Ausnahme gilt nur fuer DIESES Geraet und nur fuer das erste Bild; den
// Takt der uebrigen setzt sie nicht zurueck. Frueher setzte jedes Update den
// Deckel ganz zurueck: bei laufenden 44-Hz-Updates fiel er damit praktisch weg.
//
// tick(jetzt) -> {alle: true} (voller Schritt) | {alle: false, neu: [...]}
// (nur frisch gezielte Geraete) | null (nichts zu tun).
export function glattDeckel(bildMs) {
  let letzter = -Infinity;
  const neu = new Set();
  return {
    neuesZiel(x) { neu.add(x); },
    zuruecksetzen() { letzter = -Infinity; neu.clear(); },
    vergessen() { neu.clear(); },
    tick(jetzt) {
      // `jetzt < letzter`: Uhr sprang zurueck (Test-Uhr) -> nicht festhaengen.
      if (!(jetzt - letzter < bildMs && jetzt >= letzter)) {
        letzter = jetzt;
        neu.clear();
        return { alle: true };
      }
      if (!neu.size) return null;
      const liste = [...neu];
      neu.clear();
      return { alle: false, neu: liste };
    },
  };
}
