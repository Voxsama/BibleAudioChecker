import unittest

from engine.config import Config


class MasteringChainSettingsTest(unittest.TestCase):
    def test_every_chain_field_reaches_mastering_settings(self):
        try:
            from engine.mastering import MasteringSettings
        except ImportError:
            self.skipTest("mastering engine unavailable")
        cfg = Config(master_comp_ratio=3.5, master_highpass_freq=0.0)
        settings = MasteringSettings(**cfg.mastering_chain_settings())
        self.assertEqual(settings.comp_ratio, 3.5)
        self.assertEqual(settings.highpass_freq, 0.0)
        self.assertEqual(settings.pre_normalize_lufs, -28.0)

    def test_old_config_without_chain_fields_gets_defaults(self):
        import json, os, tempfile
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "config.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"target_lufs": -18.0, "vst_eq_path": ""}, stream)
            cfg = Config.load(path)
        self.assertEqual(cfg.master_noise_gate_threshold_db, -60.0)
        self.assertTrue(cfg.master_apply_noise_gate)


if __name__ == "__main__":
    unittest.main()
