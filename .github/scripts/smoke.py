"""Exercise the installed wheel outside the checkout, using only temporary data."""

import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

assert version("legal-markdown-organizer") == "0.2.0"
subprocess.run([sys.executable, "-m", "legal_organizer", "--version"], check=True)
with tempfile.TemporaryDirectory(prefix="legal-organizer-smoke-") as temporary:
    directory = Path(temporary) / "Acervo fictício"
    directory.mkdir()
    source = directory / "Sentença de exemplo.md"
    original = "# Documento fictício\r\n[[Nota|Alias]] #tag\r\n".encode("utf-8")
    source.write_bytes(original)

    def run(*options: str) -> None:
        subprocess.run(["legal-organizer", str(directory), *options], check=True)

    run("--dry-run")
    assert source.read_bytes() == original
    assert sorted(path.name for path in directory.iterdir()) == [source.name]
    run()
    destination = directory / "Sentencas" / source.name
    assert destination.read_bytes() == original and not source.exists()
    run("--history")
    manifest = next((directory / ".legal-organizer").glob("*.json"))
    before = manifest.read_bytes()
    run("--undo-last", "--dry-run")
    assert manifest.read_bytes() == before and not source.exists()
    run("--undo-last")
    assert source.read_bytes() == original and not destination.exists()
print("Installed-wheel smoke check passed.")
