// VIZ-104: Strobe im 3D — wann ist ein blitzendes Geraet AN, wann AUS?
//
// Die Lichtdaten kommen nur 15/30/44-mal je Sekunde (quality_tiers.js). Ein
// Strobe mit 20 Hz laesst sich darueber nicht abbilden. Python schickt deshalb
// nur die Blitzfrequenz mit (`strobe_hz` im Payload, 0 = Dauerlicht;
// src/core/strobe.py) und die Szene schaltet selbst im Bildtakt.
//
// Grundsaetze:
//  * Kurzer Blitz: an fuer STROBE_TAST (25 %) der Periode, sonst dunkel — so
//    wirkt ein echter Strobe; halb an/halb aus saehe aus wie ein Blinker.
//  * Phase aus der laufenden UHR, nicht aus dem Zeitpunkt des Updates: ein
//    Push startet den Blitz nicht neu, und Geraete gleicher Frequenz blitzen
//    gemeinsam.
//  * Ehrlich bei niedriger Bildrate: dargestellt werden hoechstens
//    STROBE_DECKEL_HZ und hoechstens ein Drittel der Bildrate (ein Bild an,
//    zwei aus). Darueber wuerde die Abtastung zufaellig Blitze treffen oder
//    verfehlen (Schwebung); genau die halbe Bildrate waere rechnerisch die
//    Grenze, kippt aber schon bei leicht schwankenden Bildabstaenden. Der
//    Blitz dauert ausserdem mindestens ein Bild, damit ihn jedes Raster trifft.
//  * 'weich' (gedaempft): kein An/Aus, sondern ein langsames, flaches Pulsieren
//    (hoechstens WEICH_MAX_HZ, nie dunkler als WEICH_MIN) — fuer Menschen, die
//    schnelle Lichtblitze nicht vertragen.
//  * 'aus': Dauerlicht wie vor VIZ-104.
//  * Nur die Helligkeit wird getaktet. Farbe, Dimmerwert und Kopplungen
//    bleiben unberuehrt; Dimmer-Effekte der Engine kommen weiter ueber die
//    Helligkeit und werden hier nicht noch einmal moduliert.
//
// Rein (keine Imports, Zeit wird hereingereicht): Node-Tests laden das Modul
// direkt (tests/test_viz104_strobe_im_3d.py). Die Konstanten haben ein
// Gegenstueck in src/ui/visualizer/strobe_prefs.py — der Test haelt beide gleich.
"use strict";

export const STROBE_MODI = Object.freeze(['flash', 'soft', 'off']);
export const STROBE_MODUS_VORGABE = 'flash';
/** Anteil der Periode, in dem das Geraet leuchtet. */
export const STROBE_TAST = 0.25;
/** Hoechste dargestellte Blitzfrequenz (Hz). */
export const STROBE_DECKEL_HZ = 12;
/** So viele Bilder braucht ein Blitz mindestens (eins an, der Rest aus). */
export const BILDER_JE_BLITZ = 3;
/** 'weich': hoechste Pulsfrequenz (Hz) und dunkelster Anteil. */
export const WEICH_MAX_HZ = 2;
export const WEICH_MIN = 0.55;
/** Stufen des weichen Pulsierens (begrenzt die Zahl der Neuberechnungen). */
export const WEICH_STUFEN = 8;
/** Angenommene Bildrate, bis eine gemessen ist. */
export const FPS_VORGABE = 60;

export function strobeModus(m) {
  return STROBE_MODI.indexOf(m) >= 0 ? m : STROBE_MODUS_VORGABE;
}

/** Frequenz, die wirklich gezeigt wird: min(hz, deckel, fps/3). 0 = kein Strobe. */
export function strobeAnzeigeHz(hz, fps = FPS_VORGABE, deckelHz = STROBE_DECKEL_HZ) {
  if (!(hz > 0)) return 0;
  let h = Math.min(hz, deckelHz);
  if (fps > 0) h = Math.min(h, fps / BILDER_JE_BLITZ);
  return h > 0 ? h : 0;
}

/** Tastverhaeltnis, das mindestens ein Bild lang an ist (hoechstens ein Drittel). */
export function strobeTast(anzeigeHz, fps = FPS_VORGABE, tast = STROBE_TAST) {
  if (!(anzeigeHz > 0) || !(fps > 0)) return tast;
  return Math.max(tast, Math.min(1 / BILDER_JE_BLITZ, anzeigeHz / fps));
}

/**
 * Die Blitz-Funktion: leuchtet das Geraet zum Zeitpunkt `zeitMs`?
 * `hz` = gemeldete Frequenz, `tast` = Tastverhaeltnis, `deckelHz` = hoechste
 * dargestellte Frequenz. hz <= 0 -> immer an (Dauerlicht).
 */
export function strobeAn(zeitMs, hz, tast = STROBE_TAST, deckelHz = STROBE_DECKEL_HZ) {
  if (!(hz > 0)) return true;
  const h = Math.min(hz, deckelHz);
  if (!(h > 0)) return true;
  const phase = (zeitMs / 1000 * h) % 1;
  return (phase < 0 ? phase + 1 : phase) < tast;
}

/**
 * Helligkeitsfaktor 0..1 je Modus — damit wird die gemeldete Helligkeit des
 * Geraets multipliziert. `fps` = gemessene Bildrate.
 */
export function strobeFaktor(zeitMs, hz, modus = STROBE_MODUS_VORGABE, fps = FPS_VORGABE) {
  if (!(hz > 0) || modus === 'off') return 1;
  if (modus === 'soft') {
    const h = Math.min(hz, WEICH_MAX_HZ);
    const welle = 0.5 + 0.5 * Math.cos(zeitMs / 1000 * h * 2 * Math.PI);
    const stufe = Math.round(welle * WEICH_STUFEN) / WEICH_STUFEN;
    return WEICH_MIN + (1 - WEICH_MIN) * stufe;
  }
  const h = strobeAnzeigeHz(hz, fps);
  return strobeAn(zeitMs, h, strobeTast(h, fps), h) ? 1 : 0;
}

/** Geglaettete Bildrate aus dem Abstand zweier Bilder (ms). */
export function fpsNachfuehren(fps, dtMs) {
  if (!(dtMs >= 2 && dtMs <= 500)) return fps;     // Pause/Tab im Hintergrund
  const neu = 1000 / dtMs;
  return fps + (neu - fps) * 0.1;
}
