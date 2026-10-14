// VIZ-104: Strobe im 3D — wann ist ein blitzendes Geraet AN, wann AUS?
//
// Die Lichtdaten kommen nur 15/30/44-mal je Sekunde (quality_tiers.js). Ein
// Strobe mit 20 Hz laesst sich darueber nicht abbilden. Python schickt deshalb
// nur die Blitzfrequenz mit (`strobe_hz` im Payload, 0 = Dauerlicht;
// src/core/strobe.py) und die Szene schaltet selbst im Bildtakt.
//
// Grundsaetze:
//  * In GANZEN BILDERN gerechnet, nicht aus der Uhr abgetastet. Blitzlaenge und
//    Periode sind eine feste Zahl von Bildern (`strobeBilder`), geschaltet wird
//    nach einem BILDZAEHLER. Die erste Sichtprobe (Intel UHD 630) hat gezeigt,
//    was die Abtastung einer Uhr-Phase gegen eine schwankende Bildrate macht:
//    Doppelblitze mit ungleichen Luecken ('..##....##..##....##'), 7-10 statt
//    12 Blitze je Sekunde und ein An-Anteil zwischen 14 und 33 % — eine
//    Schwebung. Im Bildraster gibt es die nicht: die Folge ist exakt periodisch.
//  * Kurzer Blitz: an fuer rund STROBE_TAST (25 %) der Periode, mindestens ein
//    Bild; eine Periode hat mindestens BILDER_JE_BLITZ (3) Bilder — eins an,
//    zwei aus. Halb an/halb aus saehe aus wie ein Blinker.
//  * EIN Zaehler fuer alle Geraete: gleiche Frequenz -> gleiche Periode ->
//    gleiche Phase (sie blitzen gemeinsam); verschiedene Frequenzen laufen
//    unabhaengig. Ein DMX-Update fasst den Zaehler nicht an.
//  * Ehrlich: dargestellt werden hoechstens STROBE_DECKEL_HZ. 10 Hz, weil das
//    bei drei Bildern je Blitz genau 30 Bilder/s braucht — die untere Grenze
//    dessen, was der gemessene Rechner beim Blitzen liefert (34-52 Bilder/s);
//    12 Hz braeuchten 36 und wurden dort nie erreicht. 10 teilt ausserdem 30
//    und 60 glatt. Zwischen diesen Bildraten weicht die gezeigte Frequenz um
//    eine halbe Bildlaenge je Periode ab (`strobeAnzeigeHz` nennt sie).
//  * Die Bildrate, aus der die Periode entsteht, wird gemessen
//    (`fpsNachfuehren`, Mittel der BildABSTAENDE) und traege gehalten
//    (`taktFps`): eine leicht schwankende Messung darf die Periode nicht hin-
//    und herschalten — genau das waere wieder ein stolpernder Takt.
//  * 'weich' (gedaempft): kein An/Aus, sondern ein langsames, flaches Pulsieren
//    (hoechstens WEICH_MAX_HZ, nie dunkler als WEICH_MIN) in WEICH_STUFEN
//    gleich langen Schritten je Welle — acht Aenderungen je Welle, nicht eine
//    je Bild (jede Aenderung kostet ein neu gezeichnetes Bild).
//  * 'aus': Dauerlicht wie vor VIZ-104.
//  * Nur die Helligkeit wird getaktet. Farbe, Dimmerwert und Kopplungen
//    bleiben unberuehrt; Dimmer-Effekte der Engine kommen weiter ueber die
//    Helligkeit und werden hier nicht noch einmal moduliert.
//
// Rein (keine Imports, Bildzaehler und Bildrate werden hereingereicht):
// Node-Tests laden das Modul direkt (tests/test_viz104_strobe_im_3d.py). Die
// Konstanten haben ein Gegenstueck in src/core/strobe.py (dieselbe Rechnung
// fuer die 2D-Live-Ansicht) — der Test haelt beide gleich.
"use strict";

export const STROBE_MODI = Object.freeze(['flash', 'soft', 'off']);
export const STROBE_MODUS_VORGABE = 'flash';
/** Anteil der Periode, in dem das Geraet leuchtet (auf ganze Bilder gerundet). */
export const STROBE_TAST = 0.25;
/** Hoechste dargestellte Blitzfrequenz (Hz). */
export const STROBE_DECKEL_HZ = 10;
/** So viele Bilder hat eine Periode mindestens (eins an, der Rest aus). */
export const BILDER_JE_BLITZ = 3;
/** 'weich': hoechste Pulsfrequenz (Hz) und dunkelster Anteil. */
export const WEICH_MAX_HZ = 2;
export const WEICH_MIN = 0.55;
/** Schritte je Welle des weichen Pulsierens (= Aenderungen je Welle). */
export const WEICH_STUFEN = 8;
/** Angenommene Bildrate, bis eine gemessen ist. */
export const FPS_VORGABE = 60;
/** Erst ab dieser Abweichung gilt eine neue Bildrate fuer den Takt. */
export const TAKT_TRAEGHEIT = 0.12;

export function strobeModus(m) {
  return STROBE_MODI.indexOf(m) >= 0 ? m : STROBE_MODUS_VORGABE;
}

/**
 * Periode und Blitzlaenge in ganzen Bildern: { periode, an }.
 * Zielfrequenz = min(hz, deckel); periode = max(runde(fps / ziel), 3);
 * an = max(1, runde(periode * tast)). Kein Strobe -> { periode: 0, an: 0 }.
 */
export function strobeBilder(hz, fps = FPS_VORGABE, deckelHz = STROBE_DECKEL_HZ,
                             tast = STROBE_TAST) {
  if (!(hz > 0) || !(deckelHz > 0)) return { periode: 0, an: 0 };
  const ziel = Math.min(hz, deckelHz);
  const f = (fps > 0) ? fps : FPS_VORGABE;
  const periode = Math.max(Math.round(f / ziel), BILDER_JE_BLITZ);
  const an = Math.min(periode - 1, Math.max(1, Math.round(periode * tast)));
  return { periode, an };
}

/** Frequenz, die wirklich gezeigt wird: fps / Periode. 0 = kein Strobe. */
export function strobeAnzeigeHz(hz, fps = FPS_VORGABE, deckelHz = STROBE_DECKEL_HZ) {
  const p = strobeBilder(hz, fps, deckelHz).periode;
  return p > 0 ? ((fps > 0) ? fps : FPS_VORGABE) / p : 0;
}

function _rest(bild, periode) {
  const r = Math.floor(bild) % periode;
  return r < 0 ? r + periode : r;
}

/**
 * Die Blitz-Funktion: leuchtet das Geraet im Bild Nummer `bild`?
 * hz <= 0 -> immer an (Dauerlicht).
 */
export function strobeAn(bild, hz, fps = FPS_VORGABE, deckelHz = STROBE_DECKEL_HZ,
                         tast = STROBE_TAST) {
  const b = strobeBilder(hz, fps, deckelHz, tast);
  if (!b.periode) return true;
  return _rest(bild, b.periode) < b.an;
}

/** 'weich': Bilder je Welle — ein Vielfaches von WEICH_STUFEN, nie schneller als WEICH_MAX_HZ. */
export function weichBilder(hz, fps = FPS_VORGABE) {
  if (!(hz > 0)) return 0;
  const h = Math.min(hz, WEICH_MAX_HZ);
  const f = (fps > 0) ? fps : FPS_VORGABE;
  return WEICH_STUFEN * Math.max(1, Math.ceil(f / h / WEICH_STUFEN - 1e-9));
}

/**
 * Helligkeitsfaktor 0..1 je Modus — damit wird die gemeldete Helligkeit des
 * Geraets multipliziert. `bild` = Bildzaehler, `fps` = Bildrate des Takts.
 */
export function strobeFaktor(bild, hz, modus = STROBE_MODUS_VORGABE, fps = FPS_VORGABE) {
  if (!(hz > 0) || modus === 'off') return 1;
  if (modus === 'soft') {
    const periode = weichBilder(hz, fps);
    const schritt = Math.floor(_rest(bild, periode) * WEICH_STUFEN / periode);
    const welle = 0.5 + 0.5 * Math.cos(schritt / WEICH_STUFEN * 2 * Math.PI);
    return WEICH_MIN + (1 - WEICH_MIN) * (Math.round(welle * 1e6) / 1e6);
  }
  return strobeAn(bild, hz, fps) ? 1 : 0;
}

/**
 * Geglaettete Bildrate aus dem Abstand zweier Bilder (ms). Gemittelt wird der
 * ABSTAND, nicht sein Kehrwert: wechseln lange und kurze Bilder (ein
 * gezeichnetes Bild dauert laenger als ein uebersprungenes), ergibt nur das
 * die Zahl der Bilder je Sekunde, mit der eine Periode aus N Bildern auch
 * wirklich N / fps Sekunden dauert.
 */
export function fpsNachfuehren(fps, dtMs) {
  if (!(dtMs >= 2 && dtMs <= 500)) return fps;     // Pause/Tab im Hintergrund
  const alt = 1000 / ((fps > 0) ? fps : FPS_VORGABE);
  return 1000 / (alt + (dtMs - alt) * 0.1);
}

/**
 * Bildrate, aus der die Perioden entstehen: folgt der gemessenen erst, wenn
 * sie um mehr als TAKT_TRAEGHEIT abweicht. Sonst bleibt sie stehen — und mit
 * ihr jede Periode.
 */
export function taktFps(takt, fps) {
  if (!(fps > 0)) return (takt > 0) ? takt : FPS_VORGABE;
  if (!(takt > 0)) return fps;
  return Math.abs(fps - takt) > takt * TAKT_TRAEGHEIT ? fps : takt;
}
