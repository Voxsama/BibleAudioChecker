"""Exercise apt failure handling without installing packages or requiring sudo."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform == "linux" and os.geteuid() != 0,
                     "Linux installer runs as a non-root user")
class LinuxSetupTests(unittest.TestCase):
    def test_failed_refresh_can_continue_but_failed_install_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "setup_linux.sh"
            shutil.copyfile(Path(__file__).resolve().parents[1] / script.name, script)
            binaries = root / "bin"
            binaries.mkdir()
            commands = {
                "sudo": 'exec "$@"',
                "apt-cache": "exit 0",
                "dpkg-query": "exit 1",
                "apt-get": '''echo "apt $1" >> "$TEST_LOG"
if [ "$1" = update ]; then exit 100; fi
exit "$INSTALL_STATUS"''',
                "python3": 'echo python >> "$TEST_LOG"; exit 42',
            }
            for name, body in commands.items():
                executable = binaries / name
                executable.write_text("#!/bin/sh\n" + body + "\n")
                executable.chmod(0o755)
            log = root / "commands.log"
            env = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ["PATH"],
                       TEST_LOG=str(log))
            for install_status in (0, 100):
                with self.subTest(install_status=install_status):
                    log.write_text("")
                    result = subprocess.run(
                        ["bash", str(script)], env=dict(env, INSTALL_STATUS=str(install_status)),
                        capture_output=True, text=True)
                    self.assertIn("[WARNING]", result.stderr)
                    self.assertEqual(result.returncode, 42 if install_status == 0 else 100)
                    expected = ["apt update", "apt install"]
                    if install_status == 0:
                        expected.append("python")
                    self.assertEqual(log.read_text().splitlines(), expected)


if __name__ == "__main__":
    unittest.main()
