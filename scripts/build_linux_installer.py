"""Package a frozen Linux app as a self-contained, per-user offline installer."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def build(app, output):
    app, output = Path(app), Path(output)
    if not (app / "ScriptureSoundQC").is_file():
        raise ValueError("Expected the frozen ScriptureSoundQC app directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile() as archive:
        with tarfile.open(fileobj=archive, mode="w:gz", compresslevel=6) as stream:
            stream.add(app, arcname="ScriptureSoundQC")
        archive.seek(0)
        digest = hashlib.file_digest(archive, "sha256").hexdigest()
        header = (ROOT / "installer/linux_offline.sh").read_text()
        header = header.replace("@PAYLOAD_SHA256@", digest)
        archive.seek(0)
        with output.open("wb") as stream:
            stream.write(header.encode("utf-8"))
            shutil.copyfileobj(archive, stream)
    output.chmod(0o755)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.app, args.output))
