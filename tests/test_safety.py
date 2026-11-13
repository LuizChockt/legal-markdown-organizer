import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from legal_organizer import organizer
from legal_organizer.filesystem import SafeRoot, identity
from legal_organizer.history import get_history
from legal_organizer.organizer import organize_directory, undo_last
from tests.test_history import manifest_path, write_document


def symlink(path: Path, target: Path) -> None:
    try:
        path.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable for this account/filesystem")


def test_source_symlink_is_skipped_without_reading_or_moving_target(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    external = write_document(tmp_path, "external.md", b"External fictional content")
    symlink(base / "agravo.md", external)
    result = organize_directory(base)
    assert result.moves == [] and result.skipped == 1
    assert external.read_bytes() == b"External fictional content"
    assert get_history(base) == []


@pytest.mark.parametrize("dry_run", [False, True])
def test_category_symlink_never_writes_outside_authorized_root(tmp_path: Path, dry_run: bool) -> None:
    base = tmp_path / "base"
    outside = tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    source = write_document(base)
    symlink(base / "Agravos", outside)
    result = organize_directory(base, dry_run=dry_run)
    assert len(result.errors) == 1 and not result.moves and source.exists()
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("target", ["directory", "document", "history", "manifest"])
def test_symlink_replacements_during_undo_are_rejected(tmp_path: Path, target: str) -> None:
    base = tmp_path / "base"
    base.mkdir()
    source = write_document(base)
    destination = organize_directory(base).moves[0][1]
    outside = tmp_path / "outside"
    outside.mkdir()
    external = write_document(outside, "external.md", b"External fictional content")
    if target == "directory":
        (base / "Agravos").rename(base / "retained-category")
        symlink(base / "Agravos", outside)
    elif target == "document":
        destination.unlink()
        symlink(destination, external)
    elif target == "history":
        (base / ".legal-organizer").rename(base / "retained-history")
        symlink(base / ".legal-organizer", outside)
    else:
        manifest = manifest_path(base)
        manifest.unlink()
        symlink(manifest, external)
    if target in {"history", "manifest"}:
        with pytest.raises(OSError):
            undo_last(base)
    else:
        assert len(undo_last(base).errors) == 1
    assert not source.exists()
    assert external.read_bytes() == b"External fictional content"
    assert sorted(path.name for path in outside.iterdir()) == [external.name]


def test_symlink_original_path_is_a_conflict_not_a_write_target(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    source = write_document(base)
    organize_directory(base)
    external = write_document(tmp_path, "external.md", b"Unrelated fictional document")
    symlink(source, external)
    assert len(undo_last(base).errors) == 1
    assert external.read_bytes() == b"Unrelated fictional document" and source.is_symlink()


def test_category_swapped_for_symlink_after_planning_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    # Verify symlink capability before installing the race.
    probe = base / "probe"
    symlink(probe, outside)
    probe.unlink()
    source = write_document(base)
    original_open = SafeRoot.open
    raced = False

    def racing_open(root, path, mode="rb"):
        nonlocal raced
        if mode == "xb" and path.parent.name == "Agravos" and not raced:
            raced = True
            path.parent.rename(base / "retained-category")
            symlink(path.parent, outside)
        return original_open(root, path, mode)

    monkeypatch.setattr(SafeRoot, "open", racing_open)
    result = organize_directory(base)
    assert raced and len(result.errors) == 1 and source.exists()
    assert list(outside.iterdir()) == []


def test_modified_source_during_copy_is_never_deleted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_document(tmp_path)
    copy = shutil.copyfileobj

    def concurrent_edit(original, target):
        copy(original, target)
        source.write_bytes(b"Edited by a fictional editor during organization")

    monkeypatch.setattr(shutil, "copyfileobj", concurrent_edit)
    result = organize_directory(tmp_path)
    assert len(result.errors) == 1 and result.moves == []
    assert source.read_bytes() == b"Edited by a fictional editor during organization"


def test_cleanup_never_removes_a_replacement_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_document(tmp_path)
    destination = tmp_path / "Agravos" / source.name

    def concurrent_replace(original, target):
        target.write(b"Partial fictional copy")
        target.flush()
        target.close()  # Permit replacement on Windows, which denies replacing open CRT files.
        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"Unrelated file that must survive")
        replacement.replace(destination)
        raise OSError("Simulated failure after target replacement")

    monkeypatch.setattr(shutil, "copyfileobj", concurrent_replace)
    result = organize_directory(tmp_path)
    assert len(result.errors) == 1 and source.exists()
    assert destination.read_bytes() == b"Unrelated file that must survive"
    assert len(undo_last(tmp_path).errors) == 1
    assert destination.read_bytes() == b"Unrelated file that must survive"


def test_malicious_category_is_rejected_before_any_external_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "base"
    base.mkdir()
    source = write_document(base)
    monkeypatch.setattr(organizer, "_classification", lambda *args: "../outside")
    result = organize_directory(base)
    assert len(result.errors) == 1 and source.exists()
    assert not (tmp_path / "outside").exists()


def test_destination_created_after_undo_preview_is_not_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_document(tmp_path)
    organize_directory(tmp_path)
    assert len(undo_last(tmp_path, dry_run=True).moves) == 1
    original_open = SafeRoot.open

    def race(root, path, mode="rb"):
        if mode == "xb" and path == source:
            source.write_bytes(b"Concurrent unrelated original-path occupant")
        return original_open(root, path, mode)

    monkeypatch.setattr(SafeRoot, "open", race)
    assert len(undo_last(tmp_path).errors) == 1
    assert source.read_bytes() == b"Concurrent unrelated original-path occupant"
    assert (tmp_path / "Agravos" / source.name).exists()


def test_interrupted_partial_copy_requires_manual_review(tmp_path: Path) -> None:
    source = write_document(tmp_path)
    script = """
import os, shutil, sys
from pathlib import Path
from legal_organizer.organizer import organize_directory
def stop(original, target):
    target.write(b'Partial')
    target.flush()
    os._exit(31)
shutil.copyfileobj = stop
organize_directory(Path(sys.argv[1]))
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30,
    )
    assert process.returncode == 31, process.stderr
    assert source.read_bytes() == b"# Fictional\r\n"
    destination = tmp_path / "Agravos" / source.name
    assert destination.read_bytes() == b"Partial"
    result = undo_last(tmp_path)
    assert len(result.errors) == 1 and result.moves == []
    assert destination.read_bytes() == b"Partial" and source.exists()
    # An explicit user cleanup of the known partial artifact allows retry.
    destination.unlink()
    assert not undo_last(tmp_path).errors


def test_unjournaled_target_is_never_assumed_to_belong_to_run(tmp_path: Path) -> None:
    source = write_document(tmp_path)
    organize_directory(tmp_path)
    undo_last(tmp_path)
    path = manifest_path(tmp_path)
    data = json.loads(path.read_text())
    data["status"] = "interrupted"
    data["entries"][0]["move"] = {"state": "planned", "created": None, "verified": None, "error": None}
    data["entries"][0]["undo"] = None
    path.write_text(json.dumps(data))
    destination = tmp_path / "Agravos" / source.name
    destination.write_bytes(b"Unrecorded file")
    assert len(undo_last(tmp_path).errors) == 1
    assert destination.read_bytes() == b"Unrecorded file"


def test_lock_and_manifests_are_ignored_by_git_even_in_an_unconfigured_consumer(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    write_document(tmp_path)
    organize_directory(tmp_path)
    process = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    assert ".legal-organizer" not in process.stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_windows_junction_category_is_rejected(tmp_path: Path) -> None:
    base = tmp_path / "base"
    outside = tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    source = write_document(base)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(base / "Agravos"), str(outside)], check=True, capture_output=True)
    assert len(organize_directory(base).errors) == 1
    assert source.exists() and list(outside.iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX special file and descriptor semantics")
def test_special_files_and_traversal_are_refused(tmp_path: Path) -> None:
    root = SafeRoot(tmp_path)
    fifo = tmp_path / "agravo.md"
    os.mkfifo(fifo)
    with pytest.raises(OSError, match="regular file"):
        root.open(fifo)
    with pytest.raises(OSError, match="Unsafe path"):
        root.open(tmp_path / ".." / "outside.md")
    assert organize_directory(tmp_path).skipped == 1


def test_unlink_requires_original_identity(tmp_path: Path) -> None:
    path = write_document(tmp_path)
    root = SafeRoot(tmp_path)
    before = identity(path.stat())
    replacement = write_document(tmp_path, "replacement", b"Replacement")
    replacement.replace(path)
    with pytest.raises(OSError, match="replaced"):
        root.unlink(path, before)
    assert path.read_bytes() == b"Replacement"


def test_keyboard_interrupt_is_journaled_and_recoverable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_document(tmp_path)

    def interrupt(*args):
        raise KeyboardInterrupt

    with monkeypatch.context() as changes:
        changes.setattr(shutil, "copyfileobj", interrupt)
        with pytest.raises(KeyboardInterrupt):
            organize_directory(tmp_path)
    assert source.exists() and get_history(tmp_path)[0].status == "interrupted"
    assert not undo_last(tmp_path).errors


def test_read_failure_is_recorded_and_other_documents_continue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_document(tmp_path)
    write_document(tmp_path, "sentenca.md")
    original_open = SafeRoot.open

    def fail(root, path, mode="rb"):
        if path == source:
            raise PermissionError("Simulated unreadable document")
        return original_open(root, path, mode)

    monkeypatch.setattr(SafeRoot, "open", fail)
    result = organize_directory(tmp_path)
    assert len(result.errors) == 1 and len(result.moves) == 1
    assert source.exists() and (tmp_path / "Sentencas" / "sentenca.md").exists()
    assert get_history(tmp_path)[0].status == "partial"
