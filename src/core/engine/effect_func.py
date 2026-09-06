"""LayeredEffect: Function-Typ der EffectLayers auf Fixtures anwendet."""
from __future__ import annotations
from .function import Function, FunctionType
from .effect_layers import EffectLayer
from .function import gibt_ueber_dmx_aus as _gibt_ueber_dmx_aus


class LayeredEffect(Function):
    """Function-Subtyp: wendet eine Liste von EffectLayers auf Fixtures an.

    Nutzt den bestehenden EFX-Typ als FunctionType-Tag.
    Wird in Serialisierung durch das Vorhandensein des "layers"-Schluessels
    vom klassischen EFX unterschieden.
    """
    function_type = FunctionType.EFX

    def __init__(self, name: str = "Neuer Effekt", fid: int | None = None):
        super().__init__(name, fid)
        self.layers: list[EffectLayer] = []
        self.fixture_ids: list[int] = []     # Fixtures die der Effekt steuert
        self.target_attribute: str = "intensity"
        self.base_value: float = 0.5         # Startwert (0-1, wird *255 ausgegeben)
        # Marker fuer FunctionManager.from_dict-Routing
        self.is_layered_effect = True

    def write(self, universes, patch_cache, dt, function_registry=None):
        if not self._running or not self.layers:
            return
        self._elapsed += dt * self.speed   # Per-Effekt-Speed-Master (Block B)
        t = self._elapsed

        # Lookup
        try:
            patch = {f.fid: f for f in patch_cache}
        except Exception as exc:
            print(f"[LayeredEffect] patch_cache error: {exc}")
            return

        for idx, fid in enumerate(self.fixture_ids):
            fixture = patch.get(fid)
            if fixture is None:
                continue
            # QA-78: gemessen erreichbar — ein Laser auf Platzhalter-Adresse 1
            # schrieb hier auf DMX-Adresse 1.
            if not _gibt_ueber_dmx_aus(fixture):
                continue
            universe = universes.get(fixture.universe)
            if universe is None:
                continue

            # Layers anwenden
            val = self.base_value
            for layer in self.layers:
                try:
                    val = layer.process(val, t, idx)
                except Exception as exc:
                    print(f"[LayeredEffect] layer process error: {exc}")

            # In DMX-Range konvertieren (val erwartet 0..1)
            try:
                dmx_val = max(0, min(255, int(val * 255)))
            except Exception:
                dmx_val = 0

            # Channel finden
            try:
                from src.core.app_state import get_channels_for_patched
                channels = get_channels_for_patched(fixture)
            except Exception as exc:
                print(f"[LayeredEffect] channel lookup error: {exc}")
                continue

            # ENG-16: die Geraete-Flags anwenden lassen, statt sie zu ignorieren.
            # `apply_pan_tilt_orientation` ist die EINE Stelle, die invert_pan/
            # invert_tilt/swap_pan_tilt umsetzt — Programmer-Flush und Render-Pfad
            # gehen durch sie, dieser Schreiber ging als einziger daran vorbei.
            # Gemessen an einem Geraet mit `invert_pan`: Programmer schrieb 55,
            # der Layer-Effekt 200; bei `swap` schrieb der Programmer auf den
            # Tilt-Kanal, der Layer-Effekt weiter auf Pan.
            #
            # ★ Deshalb wird das ERGEBNIS-dict geschrieben und nicht das
            # Ziel-Attribut: bei `swap` wandert der Wert auf einen ANDEREN
            # Schluessel (`{'pan': v}` -> `{'tilt': v}`). Wer stur auf
            # `target_attribute` schreibt, verliert ihn genau dann.
            try:
                from src.core.app_state import apply_pan_tilt_orientation
                werte = apply_pan_tilt_orientation(
                    fixture, {self.target_attribute: dmx_val})
            except Exception as exc:
                print(f"[LayeredEffect] orientation error: {exc}")
                werte = {self.target_attribute: dmx_val}

            # ENG-17: ALLE Vorkommen des Attributs bedienen, nicht nur das erste.
            # Ein `break` nach dem ersten Treffer liess an einer Vierkopf-Bar drei
            # Koepfe stehen (gemessen: Layer [200,0,0,0] gegen Programmer
            # [200,200,200,200]) — die Aufschrift des Effekts versprach das Geraet
            # und traf einen Kopf.
            for ch in channels:
                if ch.attribute not in werte:
                    continue
                try:
                    addr = fixture.address + ch.channel_number - 1
                    if 1 <= addr <= 512:
                        universe.set_channel(addr, werte[ch.attribute])
                except Exception as exc:
                    print(f"[LayeredEffect] set_channel error: {exc}")

    def to_dict(self):
        d = super().to_dict()
        d.update({
            "fixture_ids": list(self.fixture_ids),
            "target_attribute": self.target_attribute,
            "base_value": self.base_value,
            "layers": [l.to_dict() for l in self.layers],
        })
        return d

    @classmethod
    def from_dict(cls, d):
        e = cls(d.get("name", "Effekt"), fid=d.get("id"))
        e.fixture_ids = list(d.get("fixture_ids", []))
        e.target_attribute = d.get("target_attribute", "intensity")
        try:
            e.base_value = float(d.get("base_value", 0.5))
        except (TypeError, ValueError):
            e.base_value = 0.5
        e.layers = []
        for ld in d.get("layers", []):
            try:
                e.layers.append(EffectLayer.from_dict(ld))
            except Exception as exc:
                print(f"[LayeredEffect] from_dict layer skip: {exc}")
        return e
