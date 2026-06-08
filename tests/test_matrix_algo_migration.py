"""Tests fuer die Rueckwaerts-Migration alter Algorithmus-Namen (Phase 3, #18).

Alte Shows speichern entfernte Algorithmen als String (z. B. "Bounce H"). Beim
Laden (apply_dict/from_dict) muessen sie auf (Grundalgorithmus, params) gemappt
werden — ohne ValueError, mit korrekten Default-Parametern, und renderbar.
"""
import unittest

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, _LEGACY_ALGO_MAP


# (alter String, erwarteter Grundalgorithmus, erwartete Teil-Parameter)
CASES = [
    ("Chase Horizontal",    RgbAlgorithm.CHASE,    {"axis": "H", "movement": "normal"}),
    ("Chase Vertical",      RgbAlgorithm.CHASE,    {"axis": "V"}),
    ("Chase Diagonal",      RgbAlgorithm.CHASE,    {"axis": "Diag"}),
    ("Bounce H",            RgbAlgorithm.CHASE,    {"axis": "H", "movement": "bounce"}),
    ("Bounce V",            RgbAlgorithm.CHASE,    {"axis": "V", "movement": "bounce"}),
    ("Center→Außen",        RgbAlgorithm.CHASE,    {"movement": "center_out"}),
    ("Außen→Center",        RgbAlgorithm.CHASE,    {"movement": "outside_in"}),
    ("Komet Horizontal",    RgbAlgorithm.CHASE,    {"axis": "H", "after_fade": 30.0}),
    ("Chase Multicolor",    RgbAlgorithm.CHASE,    {"color_cycle": True}),
    ("Wipe Horizontal",     RgbAlgorithm.WIPE,     {"axis": "H"}),
    ("Wipe Vertical",       RgbAlgorithm.WIPE,     {"axis": "V"}),
    ("Welle Horizontal",    RgbAlgorithm.WAVE,     {"origin": "left"}),
    ("Diagonal Welle",      RgbAlgorithm.WAVE,     {"origin": "diag"}),
    ("Ripple (Ringe)",      RgbAlgorithm.WAVE,     {"origin": "radial"}),
    ("Gradient Horizontal", RgbAlgorithm.GRADIENT, {"axis": "H", "blend": "smooth"}),
    ("Gradient Vertikal",   RgbAlgorithm.GRADIENT, {"axis": "V"}),
    ("Color Scroll",        RgbAlgorithm.GRADIENT, {"blend": "steps"}),
    ("Sparkle",             RgbAlgorithm.RANDOM,   {"mode": "sparkle"}),
]


class AlgoMigrationTest(unittest.TestCase):

    def test_all_legacy_strings_map_and_render(self):
        for old, want_algo, want_params in CASES:
            with self.subTest(old=old):
                m = RgbMatrixInstance.from_dict({
                    "algorithm": old, "cols": 5, "rows": 3,
                    "fixture_grid": list(range(15)),
                })
                self.assertEqual(m.algorithm, want_algo, f"{old}: falscher Grundalgorithmus")
                for k, v in want_params.items():
                    self.assertEqual(m.params.get(k), v,
                                     f"{old}: params[{k}]={m.params.get(k)!r}, erwartet {v!r}")
                # rendert ohne Exception, volle Laenge
                m.start()
                px = m._render(2.5)
                self.assertEqual(len(px), 15)

    def test_explicit_params_take_precedence_over_migration_defaults(self):
        """Explizit gespeicherte params haben Vorrang vor Migrations-Defaults.
        Der alte Schweif-Wert (fade 0..1) wird dabei eindeutig auf After Fade
        (%, 0..100) migriert: explizit 0.9 -> 90 %, nicht der Default 0.3 -> 30 %."""
        m = RgbMatrixInstance.from_dict({
            "algorithm": "Komet Horizontal",     # Migrations-Default fade=0.3
            "cols": 4, "rows": 1, "fixture_grid": [1, 2, 3, 4],
            "params": {"fade": 0.9},              # explizit -> gewinnt
        })
        self.assertEqual(m.algorithm, RgbAlgorithm.CHASE)
        self.assertEqual(m.params.get("after_fade"), 90.0)
        self.assertNotIn("fade", m.params)        # eindeutig migriert

    def test_unknown_algorithm_falls_back_to_plain(self):
        m = RgbMatrixInstance.from_dict({"algorithm": "Voll-Quatsch-XY", "cols": 2, "rows": 1})
        self.assertEqual(m.algorithm, RgbAlgorithm.PLAIN)

    def test_new_algorithm_names_load_unchanged(self):
        """Neue Shows (bereits neue Namen) laden unveraendert, keine Migration."""
        for algo in (RgbAlgorithm.CHASE, RgbAlgorithm.WIPE, RgbAlgorithm.WAVE,
                     RgbAlgorithm.GRADIENT, RgbAlgorithm.RAINBOW):
            m = RgbMatrixInstance.from_dict({"algorithm": algo.value, "cols": 3, "rows": 1})
            self.assertEqual(m.algorithm, algo)

    def test_legacy_roundtrip_then_resave_uses_new_name(self):
        """Alt-String laden -> erneut speichern schreibt den neuen Grundalgorithmus."""
        m = RgbMatrixInstance.from_dict({"algorithm": "Bounce H", "cols": 5, "rows": 1})
        d = m.to_dict()
        self.assertEqual(d["algorithm"], "Chase")
        # Re-Load des neuen Dicts ergibt identischen Zustand.
        m2 = RgbMatrixInstance.from_dict(d)
        self.assertEqual(m2.algorithm, RgbAlgorithm.CHASE)
        self.assertEqual(m2.params.get("movement"), "bounce")

    def test_legacy_map_targets_are_valid_enum_values(self):
        """Jedes Migrationsziel ist ein gueltiger (neuer) Enum-Wert."""
        valid = {a.value for a in RgbAlgorithm}
        for old, (new_value, _params) in _LEGACY_ALGO_MAP.items():
            self.assertIn(new_value, valid, f"{old} -> {new_value} ist kein gueltiger Algorithmus")


if __name__ == "__main__":
    unittest.main()
