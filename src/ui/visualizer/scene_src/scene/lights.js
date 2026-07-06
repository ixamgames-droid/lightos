// VIZ-13 Schritt 3a-4: Lichter + applyBrightness (ehem. stage_scene.html:255-290).
// Reines Verschieben - Funktionssignaturen/Bodies unveraendert.
import * as THREE from '../three/three.js';
import { scene } from './renderer.js';
import { settings, view } from '../state.js';
import { requestRender } from './render_loop.js';  // VIZ-13 3c-2

// Grundhelligkeit angehoben (VIZ-10): vorher wirkten Fixtures/Raum bei
// Default-Brightness als "winzige Kloetzchen im Nichts". Werte hier sind die
// Basis bei brightness=0 - applyBrightness() skaliert weiterhin linear drauf.
export const ambient = new THREE.AmbientLight(0x282838, 0.55);
scene.add(ambient);
export const hemi = new THREE.HemisphereLight(0x50607a, 0x18181c, 0.35);
scene.add(hemi);
// Additional directional light only used when brightness > 0.4 (edit mode helper)
export const editLight = new THREE.DirectionalLight(0xffffff, 0);
editLight.position.set(10, 20, 10);
scene.add(editLight);

// Map brightness (0..1) -> ambient/hemi intensities, scene bg color
export function applyBrightness(b) {
  b = Math.max(0, Math.min(1, b));
  settings.brightness = b;
  // Background colour: from #080808 (dark) to #b0b8c0 (bright neutral)
  const bg = Math.round(8 + (176 - 8) * b);
  const bgColor = new THREE.Color(bg / 255, bg / 255, (bg + 8) / 255);
  scene.background = bgColor;
  // Fog matches background so distant objects fade nicely
  if (settings.showFog && view.mode === '3D') {
    scene.fog = new THREE.FogExp2(bgColor.getHex(), Math.max(0.005, 0.025 * (1 - b)));
  }
  // Ambient: 0.55 (default dark) -> 1.6 (very bright) - Basis angehoben (VIZ-10),
  // damit Fixtures/Raum auch bei niedriger brightness klar erkennbar bleiben.
  ambient.intensity = 0.55 + b * 1.05;
  // Hemisphere: 0.35 -> 1.15
  hemi.intensity = 0.35 + b * 0.8;
  // Edit-helper directional light kicks in above 40% brightness
  editLight.intensity = Math.max(0, (b - 0.4) * 1.5);
  // Beam visibility: in bright mode beams become less visible naturally
  // so we keep them but they look more washed out (which is realistic)
  requestRender();  // 3c-2 Dirty-Quelle 6 (Brightness: BG/Fog/Lichter)
}
