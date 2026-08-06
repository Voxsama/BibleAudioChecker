import unittest

from engine.updates import select_update, version_key


class UpdateSelectionTests(unittest.TestCase):
    @staticmethod
    def release_with_installers(tag="v4.0.1-beta.1"):
        return {
            "tag_name": tag,
            "name": "ScriptureSoundQC %s" % tag,
            "prerelease": "beta" in tag,
            "draft": False,
            "html_url": "https://example.test/release",
            "body": "Update notes",
            "assets": [{
                "name": "ScriptureSoundQC-Setup-v4.0.1-Beta.exe",
                "browser_download_url": "https://example.test/setup.exe",
            }, {
                "name": "ScriptureSoundQC-v4.0-Beta-macOS-intel.pkg",
                "browser_download_url": "https://example.test/intel.pkg",
            }, {
                "name": (
                    "ScriptureSoundQC-v4.0-Beta-macOS-"
                    "apple-silicon.pkg"),
                "browser_download_url": "https://example.test/arm.pkg",
            }],
        }

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
        }], "4.0.0-beta", "beta", "win32", "AMD64")
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

    def test_intel_mac_ignores_windows_only_release(self):
        release = self.release_with_installers()
        release["assets"] = release["assets"][:1]
        info = select_update(
            [release], "4.0.0-beta.1", "beta", "darwin", "x86_64")
        self.assertFalse(info.update_available)

    def test_intel_mac_selects_only_intel_package(self):
        info = select_update(
            [self.release_with_installers()], "4.0.0-beta.1", "beta",
            "darwin", "x86_64")
        self.assertTrue(info.update_available)
        self.assertEqual(info.download_url, "https://example.test/intel.pkg")

    def test_apple_silicon_selects_only_arm_package(self):
        info = select_update(
            [self.release_with_installers()], "4.0.0-beta.1", "beta",
            "darwin", "arm64")
        self.assertTrue(info.update_available)
        self.assertEqual(info.download_url, "https://example.test/arm.pkg")

    def test_windows_selects_only_setup_executable(self):
        info = select_update(
            [self.release_with_installers()], "4.0.0-beta.1", "beta",
            "win32", "AMD64")
        self.assertTrue(info.update_available)
        self.assertEqual(info.download_url, "https://example.test/setup.exe")

    def test_installed_beta_one_does_not_offer_same_release(self):
        info = select_update(
            [self.release_with_installers("v4.0.0-beta.1")],
            "4.0.0-beta.1", "beta", "darwin", "x86_64")
        self.assertFalse(info.update_available)


if __name__ == "__main__":
    unittest.main()
