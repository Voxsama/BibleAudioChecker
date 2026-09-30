"""Exercise installers with tiny payloads; never install into the real home."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.build_linux_installer import build as build_linux
from scripts.build_online_installer import build as build_online, sha256
from scripts.install_linux_desktop import exec_argument

BASE_URL = "https://example.test/releases/download/v4.0.1"


class InstallerEditionTests(unittest.TestCase):
    def test_packaging_failure_exits_without_a_gui_dialog(self):
        import main
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "error.txt"
            with patch.object(sys, "argv", ["app", "--packaging-self-test"]), \
                    patch.object(sys, "stderr", None), \
                    patch.dict(os.environ, BAC_SELF_TEST_OUTPUT=str(report)), \
                    patch.object(main, "_run_packaging_self_test", side_effect=RuntimeError("missing runtime")):
                with self.assertRaises(SystemExit) as error:
                    main.main()
            self.assertEqual(error.exception.code, 1)
            self.assertIn("missing runtime", report.read_text())

    def test_macos_zip_preserves_launcher_and_pins_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "ScriptureSoundQC-macOS-intel-Offline.pkg"
            payload.write_bytes(b"fake package")
            output = build_online(payload, BASE_URL, "macos")
            with zipfile.ZipFile(output) as archive:
                info, = archive.infolist()
                self.assertTrue((info.external_attr >> 16) & 0o111)
                script = archive.read(info).decode()
                self.assertIn(sha256(payload), script)
                self.assertIn(BASE_URL + "/" + payload.name, script)
                self.assertIn('/usr/bin/open -W "$download"', script)
                if sys.platform != "win32":
                    subprocess.run(["bash", "-n"], input=script, text=True, check=True)

    def test_windows_passes_size_and_hash_to_native_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "ScriptureSoundQC-Offline.exe"
            payload.write_bytes(b"offline exe")

            def compile_stub(command, **kwargs):
                self.assertIn("/DPayloadHash=" + sha256(payload), command)
                self.assertIn("/DPayloadSize=11", command)
                self.assertIn("/DPayloadURL=" + BASE_URL + "/" + payload.name, command)
                payload.with_name("ScriptureSoundQC-Online.exe").write_bytes(b"online exe")

            with patch("scripts.build_online_installer.subprocess.run", side_effect=compile_stub):
                output = build_online(payload, BASE_URL, "windows", iscc="ISCC")
            self.assertTrue(output.with_name(output.name + ".sha256").is_file())
            for url in ("http://example.test", 'https://example.test/"bad',
                        "https://secret@example.test", "https://example.test/#frag"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    build_online(payload, url, "windows", iscc="ISCC")

    @unittest.skipUnless(sys.platform == "linux" and os.geteuid() != 0,
                         "Exercises per-user Linux installation")
    def test_offline_install_upgrade_and_corruption_preserve_existing_app(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "frozen"
            app.mkdir()
            exe = app / "ScriptureSoundQC"
            exe.write_text('#!/bin/bash\nexit "${SMOKE_STATUS:-0}"\n')
            exe.chmod(0o755)
            (app / "version").write_text("one")
            # Exercise Desktop Entry escaping of spaces, %, quotes, $ and backslashes.
            data = root / 'data % " $ ` \\ with spaces'
            env = dict(os.environ, XDG_DATA_HOME=str(data))
            payload = build_linux(app, root / "ScriptureSoundQC-Offline.sh")

            def install(environment=env):
                return subprocess.run(["bash", str(payload)], env=environment,
                                      text=True, capture_output=True)

            first = install()
            self.assertEqual(first.returncode, 0, first.stderr)
            installed = data / "scripturesound-qc/app"
            desktop = (data / "applications/scripturesound-qc.desktop").read_text()
            self.assertIn("Exec=" + exec_argument(installed / "ScriptureSoundQC"), desktop)
            self.assertEqual((installed / "version").read_text(), "one")
            (app / "version").write_text("two")
            build_linux(app, payload)
            self.assertNotEqual(install(dict(env, SMOKE_STATUS="1")).returncode, 0)
            self.assertEqual((installed / "version").read_text(), "one")
            self.assertEqual(install().returncode, 0)
            self.assertEqual((installed / "version").read_text(), "two")
            contents = payload.read_bytes()
            payload.write_bytes(contents[:-8] + b"damaged!")
            self.assertNotEqual(install().returncode, 0)
            self.assertEqual((installed / "version").read_text(), "two")
            self.assertFalse((data / "scripturesound-qc/install.lock").exists())

    @unittest.skipUnless(sys.platform == "linux", "Uses Linux shell tools")
    def test_online_download_failure_and_bad_hash_never_execute_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "ScriptureSoundQC-Offline.sh"
            payload.write_text('#!/bin/bash\necho installed > "$TEST_MARKER"\n')
            online = build_online(payload, BASE_URL, "linux")
            binaries = root / "bin"
            binaries.mkdir()
            curl = binaries / "curl"
            curl.write_text('''#!/bin/bash
if [[ "${FAIL_DOWNLOAD:-0}" == 1 ]]; then exit 22; fi
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --output ]]; then cp "$TEST_PAYLOAD" "$2"; exit; fi
  shift
done
exit 1
''')
            curl.chmod(0o755)
            marker = root / "installed"
            env = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ["PATH"],
                       TEST_PAYLOAD=str(payload), TEST_MARKER=str(marker))
            for fail in ("1", "0"):
                result = subprocess.run(["bash", str(online)], env=dict(env, FAIL_DOWNLOAD=fail),
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode == 0, fail == "0", result.stderr)
                self.assertEqual(marker.exists(), fail == "0")
            marker.unlink()
            payload.write_text('#!/bin/bash\necho tampered > "$TEST_MARKER"\n')
            result = subprocess.run(["bash", str(online)], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
