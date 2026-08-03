import unittest

from engine.updates import select_update, version_key


class UpdateSelectionTests(unittest.TestCase):
    def test_semantic_prerelease_order(self):
        self.assertLess(version_key("v4.0.0-beta.1"),
                        version_key("v4.0.0-beta.2"))
        self.assertLess(version_key("v4.0.0-beta.9"),
                        version_key("v4.0.0"))
        self.assertLess(version_key("v4.0.9"), version_key("v4.1.0"))

    def test_beta_channel_receives_new_beta(self):
        info = select_update([{
            "tag_name": "v4.0.1-beta.1",
            "name": "ScriptureSoundQC v4.0.1 Beta",
            "prerelease": True,
            "draft": False,
            "html_url": "https://example.test/release",
            "body": "Update notes",
            "assets": [{
                "name": "ScriptureSoundQC-Setup-v4.0.1-Beta.exe",
                "browser_download_url": "https://example.test/setup.exe",
            }],
        }], "4.0.0-beta", "beta")
        self.assertTrue(info.update_available)
        self.assertEqual(info.version, "v4.0.1-beta.1")
        self.assertEqual(info.download_url, "https://example.test/setup.exe")

    def test_stable_channel_ignores_beta(self):
        info = select_update([{
            "tag_name": "v4.1.0-beta.1",
            "prerelease": True,
            "draft": False,
            "html_url": "https://example.test/beta",
        }], "4.0.0", "stable")
        self.assertFalse(info.update_available)

    def test_draft_is_never_offered(self):
        info = select_update([{
            "tag_name": "v9.0.0",
            "draft": True,
            "prerelease": False,
        }], "4.0.0-beta", "beta")
        self.assertFalse(info.update_available)


if __name__ == "__main__":
    unittest.main()
