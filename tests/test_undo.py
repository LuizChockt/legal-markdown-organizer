import os
import shutil
from pathlib import Path

import pytest

from legal_organizer.filesystem import SafeRoot
from legal_organizer.history import HistoryError, get_history
from legal_organizer.organizer import organize_directory, undo_last
from tests.test_history import snapshot, write_document


@pytest.mark.parametrize("content", [
    b"", b"# Fictional\r\n[[Link|Alias]] #tag\r\n\x00",
    "---\r\ntype: agravo\r\n---\r\n# Ficção jurídica — íntegra\r\n".encode("utf-8"),
    b"\xef\xbb\xbf---\ntype: agravo\n---\n# Fictional\n",
])
def test_restore_preserves_exact_bytes_and_original_mtime(tmp_path: Path, content: bytes) -> None:
    source = write_document(tmp_path, content=content)
    original_mtime = source.stat().st_mtime_ns
    organized = organize_directory(tmp_path)
    result = undo_last(tmp_path)
    assert len(result.moves) == 1 and not result.errors
    assert result.run_id == organized.run_id
    assert source.read_bytes() == content
    assert source.stat().st_mtime_ns == original_mtime
    assert (tmp_path / "Agravos").is_dir()  # Empty categories are deliberately kept.
    assert not (tmp_path / "Agravos" / source.name).exists()
    assert get_history(tmp_path)[0].entries[0].undo.state == "moved"


def test_undo_preview_preserves_complete_tree_and_manifest_times(tmp_path: Path) -> None:
    write_document(tmp_path)
    organize_directory(tmp_path)
    before = snapshot(tmp_path)
    result = undo_last(tmp_path, dry_run=True)
    assert len(result.moves) == 1 and not result.errors
    assert snapshot(tmp_path) == before
    assert get_history(tmp_path)[0].status == "completed"


@pytest.mark.parametrize("dry_run", [False, True])
def test_existing_original_is_never_overwritten(tmp_path: Path, dry_run: bool) -> None:
    source = write_document(tmp_path)
    organize_directory(tmp_path)
    source.write_bytes(b"Unrelated new document")
    result = undo_last(tmp_path, dry_run=dry_run)
    assert result.moves == [] and len(result.errors) == 1
    assert source.read_bytes() == b"Unrelated new document"
    assert (tmp_path / "Agravos" / source.name).read_bytes() == b"# Fictional\r\n"
    source.rename(tmp_path / "retained.md")
    assert not undo_last(tmp_path).errors


@pytest.mark.parametrize("change", ["contents", "mtime", "replace", "missing"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_changed_replaced_or_missing_document_is_not_restored(tmp_path: Path, change: str, dry_run: bool) -> None:
    source = write_document(tmp_path)
    destination = organize_directory(tmp_path).moves[0][1]
    if change == "contents":
        destination.write_bytes(b"Edited after organization")
    elif change == "mtime":
        old = destination.stat()
        os.utime(destination, ns=(old.st_atime_ns, old.st_mtime_ns + 1_000_000_000))
    elif change == "replace":
        replacement = tmp_path / "replacement"
        replacement.write_bytes(destination.read_bytes())
        replacement.replace(destination)
    else:
        destination.unlink()
    before = snapshot(tmp_path)
    result = undo_last(tmp_path, dry_run=dry_run)
    assert not result.moves and len(result.errors) == 1
    assert not source.exists()
    # Only real undo may update the manifest, never document bytes.
    for relative, details in before.items():
        if relative.endswith(".md"):
            assert snapshot(tmp_path)[relative] == details


def test_partial_undo_restores_other_files_and_retries_only_pending_ones(tmp_path: Path) -> None:
    write_document(tmp_path)
    write_document(tmp_path, "sentenca.md")
    organize_directory(tmp_path)
    conflict = write_document(tmp_path, "agravo.md", b"Unrelated original-path occupant")
    first = undo_last(tmp_path)
    assert len(first.moves) == 1 and len(first.errors) == 1
    assert get_history(tmp_path)[0].status == "undo_partial"
    with pytest.raises(HistoryError, match="incomplete"):
        organize_directory(tmp_path)
    conflict.rename(tmp_path / "retained.txt")
    second = undo_last(tmp_path)
    assert len(second.moves) == 1 and second.skipped == 1 and not second.errors
    assert get_history(tmp_path)[0].status == "undone"


def test_partial_organization_records_failures_and_restores_successes(tmp_path: Path) -> None:
    write_document(tmp_path)
    write_document(tmp_path, "sentenca.md")
    (tmp_path / "Sentencas").write_bytes(b"Unrelated blocking file")
    organized = organize_directory(tmp_path)
    assert len(organized.moves) == 1 and len(organized.errors) == 1
    run = get_history(tmp_path)[0]
    assert run.status == "partial" and any(entry.move.error for entry in run.entries)
    restored = undo_last(tmp_path)
    assert len(restored.moves) == 1 and restored.skipped == 1 and not restored.errors
    assert (tmp_path / "Sentencas").read_bytes() == b"Unrelated blocking file"
    assert (tmp_path / "sentenca.md").exists() and (tmp_path / "agravo.md").exists()


def test_failed_source_removal_cleans_only_verified_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_document(tmp_path)
    original_unlink = SafeRoot.unlink

    def fail(root, path, expected):
        if path == source:
            raise PermissionError("Simulated locked original")
        original_unlink(root, path, expected)

    monkeypatch.setattr(SafeRoot, "unlink", fail)
    assert len(organize_directory(tmp_path).errors) == 1
    before = snapshot(tmp_path)
    preview = undo_last(tmp_path, dry_run=True)
    assert len(preview.cleaned) == 1 and not preview.errors
    assert snapshot(tmp_path) == before
    result = undo_last(tmp_path)
    assert len(result.cleaned) == 1 and not result.errors
    assert source.read_bytes() == b"# Fictional\r\n"
    assert not (tmp_path / "Agravos" / source.name).exists()


def test_undo_copy_failure_keeps_organized_file_and_can_be_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_document(tmp_path)
    organize_directory(tmp_path)

    def fail(original, target):
        target.write(b"Partial")
        raise OSError("Simulated copy failure")

    with monkeypatch.context() as changes:
        changes.setattr(shutil, "copyfileobj", fail)
        result = undo_last(tmp_path)
    assert len(result.errors) == 1 and result.moves == [] and not source.exists()
    assert (tmp_path / "Agravos" / source.name).read_bytes() == b"# Fictional\r\n"
    assert not undo_last(tmp_path).errors


def test_undo_deletion_failure_resumes_from_verified_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_document(tmp_path)
    destination = organize_directory(tmp_path).moves[0][1]
    original_unlink = SafeRoot.unlink

    def fail(root, path, expected):
        if path == destination:
            raise PermissionError("Simulated locked organized file")
        original_unlink(root, path, expected)

    with monkeypatch.context() as changes:
        changes.setattr(SafeRoot, "unlink", fail)
        assert len(undo_last(tmp_path).errors) == 1
    assert source.read_bytes() == destination.read_bytes()
    assert not undo_last(tmp_path).errors
    assert not destination.exists()


def test_modified_partial_undo_original_blocks_duplicate_deletion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_document(tmp_path)
    destination = organize_directory(tmp_path).moves[0][1]
    original_unlink = SafeRoot.unlink

    def fail(root, path, expected):
        if path == destination:
            raise PermissionError("Locked")
        original_unlink(root, path, expected)

    with monkeypatch.context() as changes:
        changes.setattr(SafeRoot, "unlink", fail)
        undo_last(tmp_path)
    source.write_bytes(b"User edited restored copy")
    assert len(undo_last(tmp_path).errors) == 1
    assert destination.exists() and source.read_bytes() == b"User edited restored copy"


def test_duplicate_name_suffix_is_recorded_and_restored_to_original_name(tmp_path: Path) -> None:
    (tmp_path / "Agravos").mkdir()
    (tmp_path / "Agravos" / "agravo.md").write_bytes(b"Unrelated existing file")
    source = write_document(tmp_path)
    organize_directory(tmp_path)
    assert get_history(tmp_path)[0].entries[0].destination == "Agravos/agravo_1.md"
    assert not undo_last(tmp_path).errors
    assert source.read_bytes() == b"# Fictional\r\n"
    assert (tmp_path / "Agravos" / "agravo.md").read_bytes() == b"Unrelated existing file"


def test_unicode_paths_txt_and_unrelated_files_survive_round_trip(tmp_path: Path) -> None:
    base = tmp_path / "Acervo Jurídico — 日本語"
    base.mkdir()
    source = write_document(base, "Sentença com espaços — ação.md", "# Ficção\r\n".encode())
    text = write_document(base, "agravo.txt", b"\xff\x00\r\n")
    unrelated = write_document(base, "manual.pdf", b"Fictional placeholder")
    organize_directory(base, include_txt=True)
    assert not undo_last(base).errors
    assert source.read_bytes() == "# Ficção\r\n".encode()
    assert text.read_bytes() == b"\xff\x00\r\n" and unrelated.read_bytes() == b"Fictional placeholder"
