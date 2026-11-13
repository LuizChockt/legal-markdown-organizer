import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from legal_organizer.cli import main


def test_help_describes_available_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "PATH" in output
    assert "--dry-run" in output
    assert "--include-txt" in output
    assert "--history" in output and "--undo-last" in output


def test_missing_directory_exits_with_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main([str(tmp_path / "missing")])
    assert error.value.code == 2
    assert "Directory does not exist" in capsys.readouterr().err


def test_missing_path_argument_exits_with_usage_error() -> None:
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 2


def test_dry_run_output_and_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = tmp_path / "agravo.md"
    document.write_text("# Fictional\n", encoding="utf-8")
    assert main([str(tmp_path), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "[DRY RUN]" in output
    assert "-> Agravos/agravo.md" in output
    assert "1 file would be organized." in output
    assert "No files were modified." in output
    assert document.exists()


def test_success_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "sentenca.md").write_text("# Fictional\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "Organization completed." in output
    assert "Sentencas: 1" in output
    assert "1 file processed." in output


def test_empty_directory_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path)]) == 0
    assert "0 files processed." in capsys.readouterr().out


def test_txt_option(tmp_path: Path) -> None:
    (tmp_path / "agravo.txt").write_text("Fictional\n", encoding="utf-8")
    assert main([str(tmp_path), "--include-txt"]) == 0
    assert (tmp_path / "Agravos" / "agravo.txt").exists()


def test_per_file_failure_exits_one_and_reports_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "sentenca.md").write_text("# Fictional\n", encoding="utf-8")
    (tmp_path / "Sentencas").write_text("Existing file", encoding="utf-8")
    assert main([str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "Organization completed with errors." in output
    assert "1 file(s) could not be organized." in output
    assert (tmp_path / "sentenca.md").exists()


def test_real_entrypoint_handles_paths_with_spaces_and_accents(tmp_path: Path) -> None:
    base = tmp_path / "Direito" / "Base Jurídica"
    base.mkdir(parents=True)
    source = base / "Sentença.md"
    source.write_bytes("# Documento fictício\r\n[[Link]]\r\n".encode("utf-8"))
    original = source.read_bytes()
    entrypoint = Path(__file__).resolve().parents[1] / "main.py"
    environment = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    preview = subprocess.run(
        [sys.executable, str(entrypoint), str(base), "--dry-run"],
        cwd=tmp_path, env=environment, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert preview.returncode == 0, preview.stderr
    assert "Sentencas/Sentença.md" in preview.stdout
    assert source.read_bytes() == original
    assert not (base / "Sentencas").exists()
    execution = subprocess.run(
        [sys.executable, str(entrypoint), str(base)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert execution.returncode == 0, execution.stderr
    assert (base / "Sentencas" / source.name).read_bytes() == original
    assert not source.exists()


def test_checkout_dry_run_does_not_create_python_caches(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copyfile(project / "main.py", checkout / "main.py")
    shutil.copytree(
        project / "legal_organizer", checkout / "legal_organizer",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    base = checkout / "notes"
    base.mkdir()
    (base / "sentenca.md").write_text("# Fictional\n", encoding="utf-8")
    before = {path.relative_to(checkout) for path in checkout.rglob("*")}
    environment = {**os.environ, "PYTHONUTF8": "1"}
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    result = subprocess.run(
        [sys.executable, str(checkout / "main.py"), str(base), "--dry-run"],
        cwd=checkout, env=environment, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, result.stderr
    assert {path.relative_to(checkout) for path in checkout.rglob("*")} == before


def test_history_and_undo_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = tmp_path / "agravo.md"
    document.write_bytes(b"# Fictional\n")
    assert main([str(tmp_path), "--history"]) == 0
    assert "No organization history" in capsys.readouterr().out
    assert main([str(tmp_path)]) == 0
    capsys.readouterr()
    assert main([str(tmp_path), "--history"]) == 0
    assert "completed" in capsys.readouterr().out
    assert main([str(tmp_path), "--undo-last", "--dry-run"]) == 0
    assert "would be restored" in capsys.readouterr().out
    assert not document.exists()
    assert main([str(tmp_path), "--undo-last"]) == 0
    assert "Undo completed" in capsys.readouterr().out
    assert document.read_bytes() == b"# Fictional\n"
    assert main([str(tmp_path), "--undo-last"]) == 0
    assert "No organization to undo" in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [
    ["--history", "--undo-last"], ["--history", "--dry-run"],
    ["--history", "--include-txt"], ["--undo-last", "--include-txt"],
])
def test_incompatible_options_do_not_modify_files(tmp_path: Path, arguments: list[str]) -> None:
    before = list(tmp_path.iterdir())
    with pytest.raises(SystemExit) as error:
        main([str(tmp_path), *arguments])
    assert error.value.code == 2
    assert list(tmp_path.iterdir()) == before


def test_undo_conflict_exits_one_and_reports_incomplete(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = tmp_path / "agravo.md"
    document.write_bytes(b"# Fictional\n")
    assert main([str(tmp_path)]) == 0
    document.write_bytes(b"Unrelated occupant")
    assert main([str(tmp_path), "--undo-last"]) == 1
    assert "Undo incomplete" in capsys.readouterr().out
    assert document.read_bytes() == b"Unrelated occupant"


def test_invalid_history_exits_one_with_actionable_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "agravo.md").write_bytes(b"# Fictional\n")
    main([str(tmp_path)])
    next((tmp_path / ".legal-organizer").glob("*.json")).write_bytes(b"{")
    assert main([str(tmp_path), "--history"]) == 1
    assert "Invalid or unreadable history" in capsys.readouterr().err


def test_relative_path_round_trip_through_real_entrypoint(tmp_path: Path) -> None:
    base = tmp_path / "fictional notes"
    base.mkdir()
    source = base / "agravo.md"
    source.write_bytes(b"# Fictional\r\n")
    script = Path(__file__).resolve().parents[1] / "main.py"
    for options in [["--dry-run"], [], ["--history"], ["--undo-last", "--dry-run"], ["--undo-last"]]:
        result = subprocess.run(
            [sys.executable, str(script), "fictional notes", *options], cwd=tmp_path,
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        assert result.returncode == 0, result.stderr
    assert source.read_bytes() == b"# Fictional\r\n"
