"""VC-IMG Galerie (PR A): eingebaute Button-Grafiken + Runtime-Zugriff + Builder-
`bg_image`-Kwarg + Lint-Check. Alles headless.

Die Galerie-Grafiken werden von tools/gen_vc_gallery.py erzeugt + committed. Wir
pruefen hier NICHT die Byte-Gleichheit der GIFs (Pillow-Encoder-Ausgabe ist nicht
versionsstabil), sondern Existenz/Gueltigkeit + die Verdrahtung.
"""
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.show import vc_gallery, vc_assets

_app = QApplication.instance() or QApplication([])

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_GIF_MAGIC = (b"GIF87a", b"GIF89a")


class TestGalleryData(unittest.TestCase):
    def test_manifest_and_files_exist_and_valid(self):
        ents = vc_gallery.entries()
        self.assertGreaterEqual(len(ents), 10, "Galerie sollte >=10 Grafiken haben")
        for e in ents:
            self.assertTrue(os.path.isfile(e["path"]), f"fehlt: {e['file']}")
            with open(e["path"], "rb") as f:
                head = f.read(8)
            if e["kind"] == "png":
                self.assertTrue(head.startswith(_PNG_MAGIC), f"{e['file']} kein PNG")
            else:
                self.assertTrue(head.startswith(_GIF_MAGIC), f"{e['file']} kein GIF")

    def test_expected_names_present(self):
        names = set(vc_gallery.names())
        for n in ("pulse", "strobe", "rainbow_scroll", "color_wheel", "spectrum", "hot_white"):
            self.assertIn(n, names)


class TestGalleryRuntime(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="vcgal_")
        vc_assets.set_cache_dir_for_test(self._tmp)

    def tearDown(self):
        vc_assets.set_cache_dir_for_test(None)

    def test_import_to_cache_yields_valid_resolvable_key(self):
        key = vc_gallery.import_to_cache("pulse")
        self.assertTrue(vc_assets.is_valid_key(key))
        self.assertTrue(os.path.isfile(vc_assets.resolve(key)))

    def test_unknown_name_raises(self):
        with self.assertRaises(KeyError):
            vc_gallery.import_to_cache("does_not_exist")


class TestBuilderBgImage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="vcgal2_")
        vc_assets.set_cache_dir_for_test(self._tmp)

    def tearDown(self):
        vc_assets.set_cache_dir_for_test(None)

    def _builder(self):
        # _gen_env-freier Import: der ShowBuilder liegt im Core.
        from src.core.show.showbuilder.builder import ShowBuilder
        return ShowBuilder(reset=True)

    def test_resolve_gallery_name_and_key_passthrough(self):
        b = self._builder()
        key = b._resolve_bg_image("pulse")               # Galerie-Name -> Key
        self.assertTrue(vc_assets.is_valid_key(key))
        self.assertEqual(b._resolve_bg_image(key), key)  # gueltiger Key bleibt

    def test_unknown_gallery_name_raises_builderror(self):
        from src.core.show.showbuilder.builder import BuildError
        b = self._builder()
        with self.assertRaises(BuildError):
            b._resolve_bg_image("kein_gobo_der_welt")

    def test_button_embeds_asset_in_lshow(self):
        from src.core.show.showbuilder.builder import ShowBuilder
        from src.ui.virtualconsole.vc_button import ButtonAction
        b = ShowBuilder(reset=True)
        b.button("Puls", action=ButtonAction.BLACKOUT, bg_image="pulse")
        out = os.path.join(self._tmp, "gal.lshow")
        b.save(out, name="gallery-test")               # save() bettet Assets ein
        with zipfile.ZipFile(out) as zf:
            assets = [n for n in zf.namelist() if n.startswith("assets/vc/")]
        self.assertEqual(len(assets), 1, f"genau ein Asset erwartet: {assets}")


class TestLintBgImage(unittest.TestCase):
    def _codes(self, bg_image):
        from src.core.capability.validate import _check_widget
        from src.core.capability.reflect import get_capabilities
        from src.ui.virtualconsole.vc_button import VCButton
        vc_assets.set_cache_dir_for_test(tempfile.mkdtemp(prefix="vclint_"))
        try:
            b = VCButton("X")
            b.bg_image = bg_image
            findings = _check_widget(b.to_dict(), "test", get_capabilities(), set())
            return [f.code for f in findings]
        finally:
            vc_assets.set_cache_dir_for_test(None)

    def test_bogus_bg_image_warns(self):
        self.assertIn("VC-BGIMAGE", self._codes("roher_galerie_name"))

    def test_valid_key_no_warning(self):
        key = vc_gallery.import_to_cache("pulse")
        self.assertNotIn("VC-BGIMAGE", self._codes(key))

    def test_empty_no_warning(self):
        self.assertNotIn("VC-BGIMAGE", self._codes(""))


if __name__ == "__main__":
    unittest.main()
