import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from legal_organizer.filesystem import SafeRoot
from legal_organizer.history import HistoryError, HistoryStore, get_history
from legal_organizer.organizer import organize_directory, undo_last


def write_document(directory: Path, name: str = "agravo.md", content: bytes = b"# Fictional\r\n") -> Path:
    path = directory / name
    path.write_bytes(content)
    return path


def snapshot(directory: Path) -> dict:
    return {
        str(path.relative_to(directory)): (
            path.is_dir(), None if path.is_dir() else path.read_bytes(), path.stat().st_mtime_ns,
        )
        for path in [directory, *sorted(directory.rglob("*"))]
    }


def manifest_path(directory: Path) -> Path:
    return next((directory / ".legal-organizer").glob("*.json"))


def test_manifest_records_relative_paths_hashes_identity_and_version(tmp_path: Path) -> None:
    source = write_document(tmp_path)
    result = organize_directory(tmp_path)
    assert not result.errors, result.errors
    run = get_history(tmp_path)[0]
    assert run.id == result.run_id and len(run.id) == 32
    assert run.status == "completed" and run.version == "0.2.0" and run.schema == 1
    assert run.finished_at is not None
    entry = run.entries[0]
    assert entry.source == source.name and entry.destination == "Agravos/agravo.md"
    assert entry.move.state == "moved"
    assert entry.original.sha256 == entry.move.verified.sha256
    assert entry.move.created.inode == entry.move.verified.inode
    assert str(tmp_path) not in manifest_path(tmp_path).read_text(encoding="utf-8")
    assert (tmp_path / ".legal-organizer" / ".gitignore").read_bytes() == b"*\n"


def test_dry_run_does_not_create_history(tmp_path: Path) -> None:
    write_document(tmp_path)
    before = snapshot(tmp_path)
    assert organize_directory(tmp_path, dry_run=True).run_id is None
    assert get_history(tmp_path) == []
    assert snapshot(tmp_path) == before


def test_history_and_undo_without_history_do_not_create_files(tmp_path: Path) -> None:
    before = snapshot(tmp_path)
    assert get_history(tmp_path) == []
    assert undo_last(tmp_path).run_id is None
    assert undo_last(tmp_path, dry_run=True).run_id is None
    assert snapshot(tmp_path) == before


def test_history_is_read_only_and_empty_repeated_organization_is_not_recorded(tmp_path: Path) -> None:
    write_document(tmp_path)
    organize_directory(tmp_path)
    before = snapshot(tmp_path)
    assert len(get_history(tmp_path)) == 1
    assert organize_directory(tmp_path).run_id is None
    assert snapshot(tmp_path) == before


def test_multiple_executions_have_distinct_ids_and_undo_as_a_stack(tmp_path: Path) -> None:
    write_document(tmp_path, "agravo.md")
    first = organize_directory(tmp_path)
    write_document(tmp_path, "sentenca.md")
    second = organize_directory(tmp_path)
    assert first.run_id != second.run_id
    assert [run.id for run in get_history(tmp_path)] == [second.run_id, first.run_id]
    assert undo_last(tmp_path).run_id == second.run_id
    assert not (tmp_path / "agravo.md").exists()
    assert (tmp_path / "sentenca.md").exists()
    assert undo_last(tmp_path).run_id == first.run_id
    assert all(run.status == "undone" for run in get_history(tmp_path))
    assert undo_last(tmp_path).run_id is None


def test_history_order_does_not_depend_on_wall_clock(tmp_path: Path) -> None:
    write_document(tmp_path)
    first = organize_directory(tmp_path)
    write_document(tmp_path, "sentenca.md")
    second = organize_directory(tmp_path)
    file = tmp_path / ".legal-organizer" / f"{first.run_id}.json"
    data = json.loads(file.read_text())
    data["started_at"] = "2099-01-01T00:00:00+00:00"
    file.write_text(json.dumps(data))
    assert [run.id for run in get_history(tmp_path)] == [second.run_id, first.run_id]
    assert undo_last(tmp_path).run_id == second.run_id


@pytest.mark.parametrize("failure_at", [1, 3, 5, 6])
def test_journal_write_failure_stops_without_losing_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_at: int,
) -> None:
    source = write_document(tmp_path)
    content = source.read_bytes()
    save = HistoryStore.save
    calls = 0

    def fail(store, run):
        nonlocal calls
        calls += 1
        if calls >= failure_at:
            raise HistoryError("Simulated disk full")
        save(store, run)

    monkeypatch.setattr(HistoryStore, "save", fail)
    with pytest.raises(HistoryError, match="disk full"):
        organize_directory(tmp_path)
    documents = list(tmp_path.rglob("*.md"))
    assert documents and all(path.read_bytes() == content for path in documents)
    if failure_at < 6:
        assert source.read_bytes() == content


def test_atomic_manifest_failure_keeps_last_valid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_document(tmp_path)
    organize_directory(tmp_path)
    old_json = manifest_path(tmp_path).read_bytes()

    def fail(*args, **kwargs):
        raise PermissionError("Simulated journal replacement failure")

    monkeypatch.setattr(SafeRoot, "replace", fail)
    with pytest.raises(HistoryError, match="save history"):
        undo_last(tmp_path)
    assert manifest_path(tmp_path).read_bytes() == old_json
    assert (tmp_path / "Agravos" / "agravo.md").is_file()


@pytest.mark.parametrize("mutate", [
    lambda data: data.update(schema=999),
    lambda data: data.update(status="invented"),
    lambda data: data.update(id="invalid"),
    lambda data: data.update(root={"device": 0, "inode": 0}),
    lambda data: data.update(started_at="invalid"),
    lambda data: data["entries"][0].update(source="../outside.md"),
    lambda data: data["entries"][0].update(source="C:\\outside.md"),
    lambda data: data["entries"][0].update(destination="../outside/agravo.md"),
    lambda data: data["entries"][0].update(destination="Agravos/unrelated.md"),
    lambda data: data["entries"][0]["move"]["verified"].update(sha256="invalid"),
    lambda data: data["entries"][0]["move"].update(created=None),
    lambda data: data["entries"].append(data["entries"][0]),
])
def test_invalid_manifests_fail_closed_without_touching_documents(tmp_path: Path, mutate) -> None:
    write_document(tmp_path)
    organize_directory(tmp_path)
    path = manifest_path(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(HistoryError, match="history"):
        undo_last(tmp_path)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("content", [b"{", b"null", b"\xff", b"[]"])
def test_malformed_json_fails_closed(tmp_path: Path, content: bytes) -> None:
    write_document(tmp_path)
    organize_directory(tmp_path)
    manifest_path(tmp_path).write_bytes(content)
    with pytest.raises(HistoryError):
        get_history(tmp_path)
    with pytest.raises(HistoryError):
        undo_last(tmp_path, dry_run=True)


def test_process_lock_prevents_two_organizers(tmp_path: Path) -> None:
    write_document(tmp_path)
    store = HistoryStore(SafeRoot(tmp_path))
    with store.lock(write=True):
        with pytest.raises(HistoryError, match="Another organizer"):
            organize_directory(tmp_path)
        with pytest.raises(HistoryError, match="Another organizer"):
            get_history(tmp_path)
    assert not organize_directory(tmp_path).errors


@pytest.mark.parametrize("action", ["organize", "undo"])
@pytest.mark.parametrize("after_unlink", [False, True])
def test_hard_process_exit_releases_lock_and_recovers_verified_checkpoint(
    tmp_path: Path, action: str, after_unlink: bool,
) -> None:
    source = write_document(tmp_path)
    original = source.read_bytes()
    if action == "undo":
        organize_directory(tmp_path)
    script = """
import os, sys
from pathlib import Path
from legal_organizer.filesystem import SafeRoot
from legal_organizer.organizer import organize_directory, undo_last
unlink = SafeRoot.unlink
def stop(self, path, expected):
    if sys.argv[3] == 'True':
        unlink(self, path, expected)
    os._exit(23)
SafeRoot.unlink = stop
(organize_directory if sys.argv[2] == 'organize' else undo_last)(Path(sys.argv[1]))
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), action, str(after_unlink)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, timeout=30,
    )
    assert process.returncode == 23, process.stderr
    assert get_history(tmp_path)[0].status in {"running", "undoing"}
    result = undo_last(tmp_path)
    assert not result.errors
    assert source.read_bytes() == original
    assert not (tmp_path / "Agravos" / source.name).exists()
    assert get_history(tmp_path)[0].status == "undone"
