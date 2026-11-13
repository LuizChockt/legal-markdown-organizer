"""Journaled, byte-preserving organization and conservative restoration."""

import io
import os
import shutil
import stat
import uuid
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from .classifier import classify_filename, classify_type
from .filesystem import Fingerprint, Identity, SafeRoot, identity, is_link
from .frontmatter import read_frontmatter_stream
from .history import (
    Entry,
    HistoryError,
    HistoryStore,
    Manifest,
    Transfer,
    now,
    validate_name,
)
from .rules import DEFAULT_EXTENSIONS, OPTIONAL_EXTENSIONS


@dataclass
class OrganizationResult:
    """Only verified successes are included in moves and counts."""

    moves: list[tuple[Path, Path]] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    skipped: int = 0
    cleaned: list[Path] = field(default_factory=list)
    run_id: str | None = None


def available_destination(destination: Path, reserved: set[Path] | None = None) -> Path:
    """Add a numbered suffix for files, directories, symlinks or planned moves."""
    reserved = reserved if reserved is not None else set()
    candidate = destination
    suffix = 1
    while candidate.exists() or candidate.is_symlink() or candidate in reserved:
        candidate = destination.with_name(f"{destination.stem}_{suffix}{destination.suffix}")
        suffix += 1
    return candidate


def _transfer(
    root: SafeRoot, source: Path, destination: Path, expected: Fingerprint,
    transfer: Transfer, save: Callable[[], None],
) -> None:
    """Persist ownership and verified content before deleting a source.

    A crash leaves a planned, created or verified-copy checkpoint. Only the
    latter can justify a later deletion. Unknown/replaced files are retained.
    """
    root.verify(source, expected)
    try:
        with root.open(source) as original, root.open(destination, "xb") as target:
            transfer.created = identity(os.fstat(target.fileno()))
            transfer.state = "created"
            save()
            shutil.copyfileobj(original, target)
            target.flush()
            os.fsync(target.fileno())
            root.preserve_metadata(os.fstat(original.fileno()), target, destination)
            os.fsync(target.fileno())
        root.sync_parent(destination)
        root.verify(source, expected)
        verified = root.fingerprint(destination)
        if (verified.sha256, verified.size) != (expected.sha256, expected.size):
            raise OSError("Copied bytes do not match the original; both files were retained.")
        transfer.verified = verified
        transfer.state = "copied"
        save()
        root.verify(source, expected)
        root.verify(destination, verified)
        root.unlink(source, Identity(expected.device, expected.inode))
        root.sync_parent(source)
        transfer.state = "moved"
        save()
    except BaseException:
        # Cleanup is limited to a file created by this call, before the verified
        # copy checkpoint. Never remove a replacement or an unrecorded artifact.
        if transfer.state == "created" and transfer.created is not None:
            with suppress(OSError):
                root.unlink(destination, transfer.created)
                root.sync_parent(destination)
                transfer.state = "aborted"
        raise


def _classification(root: SafeRoot, source: Path) -> str:
    if source.suffix.lower() == ".md":
        with root.open(source) as stream:
            with io.TextIOWrapper(stream, encoding="utf-8-sig") as text:
                category = classify_type(read_frontmatter_stream(text).get("type", ""))
        if category is not None:
            return category
    return classify_filename(source.name)


def _candidates(root: SafeRoot, include_txt: bool, result: OrganizationResult) -> list[Path]:
    extensions = DEFAULT_EXTENSIONS | OPTIONAL_EXTENSIONS if include_txt else DEFAULT_EXTENSIONS
    candidates = []
    for path in sorted(root.path.iterdir(), key=lambda path: (path.name.casefold(), path.name)):
        if path.name == ".legal-organizer":
            continue
        if path.suffix.lower() not in extensions:
            result.skipped += 1
            continue
        try:
            info = path.lstat()
        except OSError:
            # Journal the read error in the normal per-file processing path.
            candidates.append(path)
            continue
        if not is_link(info) and stat.S_ISREG(info.st_mode):
            candidates.append(path)
        else:
            result.skipped += 1
    return candidates


def organize_directory(
    directory: Path, *, dry_run: bool = False, include_txt: bool = False,
) -> OrganizationResult:
    """Scan top-level files; dry-run never creates history, locks or folders."""
    root = SafeRoot(directory)
    store = HistoryStore(root)
    result = OrganizationResult()
    # Preserve empty/no-op directory behavior, including its modification time.
    if not _candidates(root, include_txt, result):
        if store.exists():
            with store.lock(write=False):
                if any(run.status not in {"completed", "undone"} for run in store.load()):
                    raise HistoryError("An incomplete execution needs review. Use --undo-last --dry-run.")
        return result
    with store.lock(write=not dry_run):
        runs = store.load()
        if any(run.status in {"running", "interrupted", "partial", "undoing", "undo_partial"} for run in runs):
            raise HistoryError("An incomplete execution needs review. Use --undo-last --dry-run, then --undo-last.")
        result.skipped = 0
        candidates = _candidates(root, include_txt, result)
        if not candidates:
            return result
        run = Manifest(id=uuid.uuid4().hex, root=root.identity, sequence=1 + max((run.sequence for run in runs), default=0))
        result.run_id = None if dry_run else run.id
        save = (lambda: None) if dry_run else lambda: store.save(run)
        if not dry_run:
            save()
        reserved: set[Path] = set()
        try:
            for source in candidates:
                try:
                    validate_name(source.name)
                except ValueError as error:
                    result.errors.append((source, str(error)))
                    continue
                entry = Entry(source=source.name)
                run.entries.append(entry)
                save()
                try:
                    entry.original = root.fingerprint(source)
                    category = _classification(root, source)
                    root.verify(source, entry.original)
                    category_directory = root.path / category
                    if root.exists(category_directory) and not stat.S_ISDIR(root.stat(category_directory).st_mode):
                        raise NotADirectoryError(f"Category path is not a directory: {category_directory}")
                    destination = available_destination(category_directory / source.name, reserved)
                    if not dry_run:
                        root.mkdir(category_directory)
                    while True:
                        entry.destination = destination.relative_to(root.path).as_posix()
                        save()
                        if dry_run:
                            break
                        try:
                            _transfer(root, source, destination, entry.original, entry.move, save)
                            break
                        except FileExistsError:
                            if entry.move.state != "planned":
                                raise
                            # Another writer reserved this name after planning.
                            destination = available_destination(category_directory / source.name, reserved)
                    reserved.add(destination)
                    result.moves.append((source, destination))
                    result.counts[category] += 1
                except HistoryError:
                    raise
                except (OSError, UnicodeError, ValueError) as error:
                    entry.move.error = str(error)
                    result.errors.append((source, str(error)))
                    save()
            run.status = "partial" if result.errors else "completed"
            run.finished_at = now()
            save()
        except BaseException:
            run.status = "interrupted"
            with suppress(OSError):
                save()
            raise
    return result


def _restore_entry(
    root: SafeRoot, entry: Entry, result: OrganizationResult,
    save: Callable[[], None], *, dry_run: bool,
) -> None:
    source = root.path / entry.source
    if entry.undo is not None and entry.undo.state == "moved":
        result.skipped += 1
        return
    if not entry.destination or entry.move.state in {"planned", "aborted"}:
        # A crash between exclusive creation and journaling can leave an
        # unowned target. Report it, but never infer ownership from its name.
        if entry.destination and root.exists(root.path / entry.destination) and entry.move.state == "planned":
            raise OSError("Unrecorded destination retained; inspect it manually before retrying.")
        if entry.original is not None and not root.exists(source):
            raise FileNotFoundError("Original is missing and no verified move was recorded; inspect backups.")
        result.skipped += 1
        return
    destination = root.path / entry.destination
    if entry.move.verified is None or entry.original is None:
        if not root.exists(destination):
            if not root.exists(source):
                raise FileNotFoundError("Both original and unverified copy are missing; inspect backups.")
            result.skipped += 1
            return
        raise OSError("Unverified partial copy retained; inspect it manually. No automatic deletion is safe.")
    expected = entry.move.verified
    undo = entry.undo
    if undo is not None and undo.state == "copied" and undo.verified is not None:
        # Resume an undo interrupted before/after removing the organized copy.
        root.verify(source, undo.verified)
        if root.exists(destination):
            root.verify(destination, expected)
            if not dry_run:
                root.unlink(destination, Identity(expected.device, expected.inode))
                root.sync_parent(destination)
        if not dry_run:
            undo.state = "moved"
            save()
        if undo.verified == entry.original:
            result.cleaned.append(destination)
        else:
            result.moves.append((destination, source))
        return
    root.verify(destination, expected)
    if root.exists(source):
        # A failed source deletion can leave two complete copies. Only the
        # unchanged ORIGINAL inode permits deleting our verified duplicate.
        if entry.move.state == "copied" and undo is None:
            root.verify(source, entry.original)
            if not dry_run:
                entry.undo = Transfer(state="copied", created=Identity(entry.original.device, entry.original.inode), verified=entry.original)
                save()
                root.verify(destination, expected)
                root.verify(source, entry.original)
                root.unlink(destination, Identity(expected.device, expected.inode))
                root.sync_parent(destination)
                entry.undo.state = "moved"
                save()
            result.cleaned.append(destination)
            return
        raise FileExistsError(f"Original path already exists; move it to a safe location and retry: {source.name}")
    if dry_run:
        result.moves.append((destination, source))
        return
    entry.undo = Transfer()
    save()
    _transfer(root, destination, source, expected, entry.undo, save)
    result.moves.append((destination, source))


def undo_last(directory: Path, *, dry_run: bool = False) -> OrganizationResult:
    """Restore the newest non-undone execution, including partial checkpoints.

    Conflicts remain pending for a retry. Empty category folders are retained.
    Undo uses the same copy/verify/journal/delete sequence as organization.
    """
    root = SafeRoot(directory)
    store = HistoryStore(root)
    result = OrganizationResult()
    if not store.exists():
        return result
    with store.lock(write=not dry_run):
        run = next((run for run in store.load() if run.status != "undone"), None)
        if run is None:
            return result
        result.run_id = run.id
        save = (lambda: None) if dry_run else lambda: store.save(run)
        if not dry_run:
            run.status = "undoing"
            save()
        try:
            for entry in reversed(run.entries):
                try:
                    _restore_entry(root, entry, result, save, dry_run=dry_run)
                except HistoryError:
                    raise
                except (OSError, UnicodeError) as error:
                    result.errors.append((root.path / entry.source, str(error)))
                    if not dry_run:
                        if entry.undo is None:
                            entry.undo = Transfer()
                        entry.undo.error = str(error)
                        save()
            run.status = "undo_partial" if result.errors else "undone"
            save()
        except BaseException:
            run.status = "undo_partial"
            with suppress(OSError):
                save()
            raise
    return result
