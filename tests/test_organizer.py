import shutil
from pathlib import Path

import pytest

from legal_organizer.organizer import available_destination, organize_directory


def _write(path: Path, content: bytes = b"# Fictional document\n") -> Path:
    path.write_bytes(content)
    return path


def _snapshot(directory: Path) -> dict[str, tuple[bool, bytes | None, int]]:
    return {
        str(path.relative_to(directory)): (
            path.is_dir(), None if path.is_dir() else path.read_bytes(), path.stat().st_mtime_ns,
        )
        for path in [directory, *sorted(directory.rglob("*"))]
    }


def test_moves_files_and_creates_needed_categories(tmp_path: Path) -> None:
    _write(tmp_path / "agravo.md")
    _write(tmp_path / "sentenca.md")
    _write(tmp_path / "observacoes.md")
    result = organize_directory(tmp_path)
    assert result.counts == {"Agravos": 1, "Sentencas": 1, "Outros": 1}
    assert len(result.moves) == 3
    assert result.errors == []
    for category, filename in [
        ("Agravos", "agravo.md"), ("Sentencas", "sentenca.md"), ("Outros", "observacoes.md"),
    ]:
        assert (tmp_path / category / filename).is_file()
        assert not (tmp_path / filename).exists()


def test_filename_is_preserved(tmp_path: Path) -> None:
    source = _write(tmp_path / "Agravo-de-Instrumento.MD")
    result = organize_directory(tmp_path)
    assert result.moves[0][1].name == source.name
    assert (tmp_path / "Agravos" / source.name).is_file()


def test_conflicts_never_overwrite_existing_files(tmp_path: Path) -> None:
    category = tmp_path / "Agravos"
    category.mkdir()
    _write(category / "agravo.md", b"Existing original")
    _write(category / "agravo_1.md", b"Existing numbered")
    _write(tmp_path / "agravo.md", b"New document")
    result = organize_directory(tmp_path)
    assert result.moves[0][1] == category / "agravo_2.md"
    assert (category / "agravo.md").read_bytes() == b"Existing original"
    assert (category / "agravo_1.md").read_bytes() == b"Existing numbered"
    assert (category / "agravo_2.md").read_bytes() == b"New document"


def test_dry_run_and_execution_choose_identical_conflict_names(tmp_path: Path) -> None:
    category = tmp_path / "Agravos"
    category.mkdir()
    _write(category / "agravo.md")
    _write(tmp_path / "agravo.md", b"New first")
    _write(tmp_path / "agravo_1.md", b"New second")
    planned = organize_directory(tmp_path, dry_run=True)
    actual = organize_directory(tmp_path)
    assert planned.moves == actual.moves
    assert (category / "agravo_1.md").read_bytes() == b"New first"
    assert (category / "agravo_1_1.md").read_bytes() == b"New second"


def test_dry_run_does_not_create_directories(tmp_path: Path) -> None:
    _write(tmp_path / "agravo.md")
    result = organize_directory(tmp_path, dry_run=True)
    assert result.counts == {"Agravos": 1}
    assert sorted(path.name for path in tmp_path.iterdir()) == ["agravo.md"]


def test_dry_run_does_not_move_files(tmp_path: Path) -> None:
    document = _write(tmp_path / "sentenca.md")
    result = organize_directory(tmp_path, dry_run=True)
    assert result.moves == [(document, tmp_path / "Sentencas" / document.name)]
    assert document.exists()
    assert not result.moves[0][1].exists()


def test_dry_run_preserves_entire_tree_bytes_and_modification_times(tmp_path: Path) -> None:
    category = tmp_path / "Agravos"
    category.mkdir()
    _write(category / "agravo.md", b"Existing")
    _write(tmp_path / "agravo.md", b"---\ntype: agravo\n---\n[[Link]] #tag\n")
    _write(tmp_path / "sentenca.md")
    _write(tmp_path / "ignored.pdf", b"Fictional placeholder")
    before = _snapshot(tmp_path)
    organize_directory(tmp_path, dry_run=True)
    assert _snapshot(tmp_path) == before


def test_complete_markdown_content_is_preserved(tmp_path: Path) -> None:
    content = (
        "---\r\ntype: agravo\r\nprocess: EXAMPLE-001\r\ntags:\r\n  - exemplo\r\n---\r\n"
        "# Título com acentos\r\n[[Outra nota#Seção|Alias]] #tag\r\n"
        "## Heading\r\n```python\r\nprint('exemplo')\r\n```\r\n\r\n"
    ).encode("utf-8")
    source = _write(tmp_path / "documento_123.md", content)
    original_mtime = source.stat().st_mtime_ns
    organize_directory(tmp_path)
    destination = tmp_path / "Agravos" / source.name
    assert destination.read_bytes() == content
    assert destination.stat().st_mtime_ns == original_mtime


def test_empty_directory_stays_empty(tmp_path: Path) -> None:
    result = organize_directory(tmp_path)
    assert result.moves == []
    assert result.counts == {}
    assert result.errors == []
    assert list(tmp_path.iterdir()) == []


def test_nonexistent_directory_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        organize_directory(missing)
    assert not missing.exists()


def test_file_instead_of_directory_is_rejected(tmp_path: Path) -> None:
    document = _write(tmp_path / "document.md")
    with pytest.raises(NotADirectoryError, match="not a directory"):
        organize_directory(document)


@pytest.mark.parametrize("include_txt", [False, True])
def test_only_supported_extensions_are_organized(tmp_path: Path, include_txt: bool) -> None:
    for extension in [".md", ".txt", ".pdf", ".doc", ".docx", ".jpg", ".png"]:
        _write(tmp_path / f"agravo{extension}")
    result = organize_directory(tmp_path, include_txt=include_txt)
    assert len(result.moves) == (2 if include_txt else 1)
    assert (tmp_path / "Agravos" / "agravo.md").exists()
    assert (tmp_path / "agravo.txt").exists() is not include_txt
    for extension in [".pdf", ".doc", ".docx", ".jpg", ".png"]:
        assert (tmp_path / f"agravo{extension}").read_bytes() == b"# Fictional document\n"


def test_subdirectories_and_already_organized_documents_are_untouched(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    _write(nested / "agravo.md")
    before = _snapshot(tmp_path)
    assert organize_directory(tmp_path).moves == []
    assert _snapshot(tmp_path) == before


def test_running_twice_does_not_duplicate_documents(tmp_path: Path) -> None:
    _write(tmp_path / "agravo.md")
    organize_directory(tmp_path)
    before = _snapshot(tmp_path)
    assert organize_directory(tmp_path).moves == []
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("dry_run", [False, True])
def test_blocked_category_is_reported_and_other_files_continue(tmp_path: Path, dry_run: bool) -> None:
    blocker = _write(tmp_path / "Sentencas", b"Existing unrelated file")
    sentenca = _write(tmp_path / "sentenca.md")
    _write(tmp_path / "agravo.md")
    result = organize_directory(tmp_path, dry_run=dry_run)
    assert result.counts == {"Agravos": 1}
    assert len(result.errors) == 1
    assert result.errors[0][0] == sentenca
    assert sentenca.exists()
    assert blocker.read_bytes() == b"Existing unrelated file"


def test_copy_failure_keeps_source_and_removes_partial_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = b"Complete original document"
    source = _write(tmp_path / "agravo.md", original)

    def fail_copy(source_stream, target_stream) -> None:
        target_stream.write(b"Partial")
        raise OSError("Simulated copy failure")

    monkeypatch.setattr(shutil, "copyfileobj", fail_copy)
    result = organize_directory(tmp_path)
    assert source.read_bytes() == original
    assert not (tmp_path / "Agravos" / source.name).exists()
    assert result.moves == []
    assert len(result.errors) == 1


def test_metadata_copy_failure_keeps_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _write(tmp_path / "agravo.md")

    def fail_stat(*args, **kwargs) -> None:
        raise OSError("Simulated metadata copy failure")

    monkeypatch.setattr(shutil, "copystat", fail_stat)
    result = organize_directory(tmp_path)
    assert source.exists()
    assert not (tmp_path / "Agravos" / source.name).exists()
    assert len(result.errors) == 1


def test_source_deletion_failure_retains_both_complete_copies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"Complete original document"
    source = _write(tmp_path / "agravo.md", content)
    original_unlink = Path.unlink

    def fail_source_unlink(path: Path, *args, **kwargs) -> None:
        if path == source:
            raise PermissionError("Simulated locked source")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_source_unlink)
    result = organize_directory(tmp_path)
    assert len(result.errors) == 1
    assert source.read_bytes() == content
    assert (tmp_path / "Agravos" / source.name).read_bytes() == content


def test_a_target_created_after_planning_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _write(tmp_path / "agravo.md", b"New document")
    destination = tmp_path / "Agravos" / source.name
    original_open = Path.open
    collision_created = False

    def racing_open(path: Path, mode="r", *args, **kwargs):
        nonlocal collision_created
        if path == destination and mode == "xb" and not collision_created:
            collision_created = True
            with original_open(path, "wb") as target:
                target.write(b"Created by another operation")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", racing_open)
    result = organize_directory(tmp_path)
    assert result.errors == []
    assert destination.read_bytes() == b"Created by another operation"
    assert result.moves[0][1] == destination.with_name("agravo_1.md")
    assert result.moves[0][1].read_bytes() == b"New document"


def test_invalid_utf8_is_reported_without_moving_source(tmp_path: Path) -> None:
    source = _write(tmp_path / "agravo.md", b"---\ntype: \xff\n---\n")
    result = organize_directory(tmp_path)
    assert source.exists()
    assert len(result.errors) == 1
    assert result.moves == []
    assert not (tmp_path / "Agravos").exists()


def test_directories_with_document_extensions_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "agravo.md").mkdir()
    assert organize_directory(tmp_path).moves == []


def test_planned_destinations_and_existing_directories_reserve_names(tmp_path: Path) -> None:
    target = tmp_path / "agravo.md"
    target.mkdir()
    reserved = {tmp_path / "agravo_1.md"}
    assert available_destination(target, reserved) == tmp_path / "agravo_2.md"
