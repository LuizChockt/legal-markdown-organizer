"""Release-script contract tests use a fake gh executable, never GitHub."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "publish-release.sh"
pytestmark = pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="Release script runs on a POSIX runner")


@pytest.mark.parametrize("existing", ["missing", "matching", "conflicting"])
def test_publication_never_replaces_an_existing_tag(tmp_path: Path, existing: str) -> None:
    cli = tmp_path / "gh"
    cli.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys
from pathlib import Path
arguments = sys.argv[1:]
with Path(os.environ["TEST_GH_LOG"]).open("a") as stream:
    stream.write(json.dumps(arguments) + "\\n")
if arguments[0] == "api" and "--method" not in arguments:
    scenario = os.environ["TEST_EXISTING_TAG"]
    if scenario == "missing":
        print('{"message":"Not Found","status":"404"}')
        raise SystemExit(1)
    print(os.environ["RELEASE_SHA"] if scenario == "matching" else "1" * 40)
elif arguments[:3] == ["api", "--method", "POST"]:
    assert "ref=refs/tags/v0.2.0" in arguments
    assert "sha=" + os.environ["RELEASE_SHA"] in arguments
elif arguments[:2] == ["release", "create"]:
    assert "--verify-tag" in arguments
else:
    raise SystemExit("Unexpected fake gh call")
''', encoding="utf-8")
    cli.chmod(0o700)
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "fictional.whl").write_bytes(b"Fictional artifact")
    log = tmp_path / "calls.jsonl"
    process = subprocess.run(
        ["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
             "GH_REPO": "fictional-owner/fictional-repo", "RELEASE_SHA": "0" * 40,
             "TEST_EXISTING_TAG": existing, "TEST_GH_LOG": str(log)},
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    creates = [call for call in calls if call[:3] == ["api", "--method", "POST"]]
    releases = [call for call in calls if call[:2] == ["release", "create"]]
    if existing == "conflicting":
        assert process.returncode != 0 and not creates and not releases
        assert "refusing to change" in process.stderr
    else:
        assert process.returncode == 0, process.stderr
        assert len(creates) == (1 if existing == "missing" else 0)
        assert len(releases) == 1
