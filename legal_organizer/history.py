"""Versioned local JSON journals, validation and crash-released process locks."""

import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar

from . import __version__
from .filesystem import Fingerprint, Identity, SafeRoot
from .rules import CATEGORY_PRIORITY

STATE_DIRECTORY = ".legal-organizer"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
RUN_STATES = {"running", "completed", "partial", "interrupted", "undoing", "undo_partial", "undone"}
TRANSFER_STATES = {"planned", "created", "copied", "moved", "aborted"}
Record = TypeVar("Record", Identity, Fingerprint)


class HistoryError(OSError):
    """A journal error must stop writes, never be treated as a per-file error."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@dataclass
class Transfer:
    state: str = "planned"
    created: Identity | None = None
    verified: Fingerprint | None = None
    error: str | None = None


@dataclass
class Entry:
    source: str
    destination: str | None = None
    original: Fingerprint | None = None
    move: Transfer = field(default_factory=Transfer)
    undo: Transfer | None = None


@dataclass
class Manifest:
    id: str
    root: Identity
    sequence: int = 1
    started_at: str = field(default_factory=now)
    status: str = "running"
    entries: list[Entry] = field(default_factory=list)
    finished_at: str | None = None
    schema: int = 1
    version: str = __version__


def validate_name(name: str) -> str:
    """Require one portable filename, including on a different OS at undo time."""
    if (
        not name or name in {".", ".."} or any(char in name for char in '/\\:\x00<>"|?*')
        or any(ord(char) < 32 for char in name) or name.endswith((".", " "))
        or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", name.split(".")[0])
    ):
        raise ValueError(f"Unsafe or non-portable filename: {name!r}")
    return name


def _record(cls: type[Record], data: Any) -> Record:
    if not isinstance(data, dict):
        raise ValueError("Invalid file identity/fingerprint")
    result = cls(**data)
    for key, value in data.items():
        if key == "sha256":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("Invalid SHA-256")
        elif type(value) is not int or (key not in {"mtime_ns", "ctime_ns"} and value < 0):
            raise ValueError("Invalid numeric fingerprint field")
    return result


def _transfer(data: Any) -> Transfer:
    if not isinstance(data, dict):
        raise ValueError("Invalid transfer")
    transfer = Transfer(**data)
    if transfer.state not in TRANSFER_STATES:
        raise ValueError("Invalid transfer state")
    if transfer.created is not None:
        transfer.created = _record(Identity, transfer.created)
    if transfer.verified is not None:
        transfer.verified = _record(Fingerprint, transfer.verified)
    if transfer.state in {"created", "copied", "moved"} and transfer.created is None:
        raise ValueError("Missing created-file identity")
    if transfer.state in {"copied", "moved"} and transfer.verified is None:
        raise ValueError("Missing verified fingerprint")
    if transfer.verified and transfer.created != Identity(transfer.verified.device, transfer.verified.inode):
        raise ValueError("Inconsistent target identity")
    if transfer.error is not None and not isinstance(transfer.error, str):
        raise ValueError("Invalid error message")
    return transfer


def _manifest(data: Any, file: Path, root: SafeRoot) -> Manifest:
    if not isinstance(data, dict):
        raise ValueError("Manifest must be an object")
    run = Manifest(**data)
    if type(run.schema) is not int or run.schema != 1:
        raise ValueError("Unsupported manifest schema")
    if type(run.sequence) is not int or run.sequence < 1:
        raise ValueError("Invalid execution sequence")
    if not isinstance(run.id, str) or not re.fullmatch(r"[0-9a-f]{32}", run.id) or file.stem != run.id:
        raise ValueError("Invalid manifest identifier")
    if run.status not in RUN_STATES or not isinstance(run.entries, list):
        raise ValueError("Invalid execution status or entries")
    if not isinstance(run.started_at, str) or datetime.fromisoformat(run.started_at).utcoffset() is None:
        raise ValueError("Invalid execution timestamp")
    run.root = _record(Identity, run.root)
    if run.root != root.identity:
        raise ValueError("History belongs to another directory/filesystem; inspect it manually")
    entries = []
    sources: set[str] = set()
    destinations: set[str] = set()
    for value in run.entries:
        if not isinstance(value, dict):
            raise ValueError("Invalid entry")
        entry = Entry(**value)
        validate_name(entry.source)
        if Path(entry.source).suffix.lower() not in {".md", ".txt"} or entry.source in sources:
            raise ValueError("Invalid or duplicate source")
        sources.add(entry.source)
        if entry.destination is not None:
            parts = PurePosixPath(entry.destination).parts
            if len(parts) != 2 or parts[0] not in CATEGORY_PRIORITY:
                raise ValueError("Destination must be in a known category")
            validate_name(parts[1])
            source = Path(entry.source)
            pattern = re.escape(source.stem) + r"(?:_[1-9][0-9]*)?" + re.escape(source.suffix)
            if not re.fullmatch(pattern, parts[1]) or entry.destination in destinations:
                raise ValueError("Invalid or duplicate destination filename")
            destinations.add(entry.destination)
        entry.move = _transfer(entry.move)
        if entry.original is not None:
            entry.original = _record(Fingerprint, entry.original)
        if entry.move.state in {"created", "copied", "moved"} and (not entry.original or not entry.destination):
            raise ValueError("Missing original fingerprint or destination")
        if entry.undo is not None:
            entry.undo = _transfer(entry.undo)
        entries.append(entry)
    run.entries = entries
    return run


class HistoryStore:
    def __init__(self, root: SafeRoot):
        self.root = root
        self.directory = root.path / STATE_DIRECTORY

    def exists(self) -> bool:
        return self.root.exists(self.directory)

    @contextmanager
    def lock(self, *, write: bool) -> Iterator[None]:
        if write:
            self.root.mkdir(self.directory)
            ignore = self.directory / ".gitignore"
            try:
                with self.root.open(ignore, "xb") as stream:
                    stream.write(b"*\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                with self.root.open(ignore) as stream:
                    if stream.read(4) != b"*\n":
                        raise HistoryError("History .gitignore must contain only '*'; repair it before continuing.")
        elif not self.exists():
            yield
            return
        lock_file = self.directory / "lock"
        if write:
            try:
                with self.root.open(lock_file, "xb") as stream:
                    stream.write(b"0")
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                pass
        # Never create or rewrite anything during history or dry-run reads.
        try:
            stream = self.root.open(lock_file, "rb")
        except FileNotFoundError as error:
            raise HistoryError("History lock is missing; inspect .legal-organizer before continuing.") from error
        with stream:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise HistoryError("Another organizer process is using this directory; wait and retry.") from error
            try:
                yield
            finally:
                if sys.platform == "win32":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def save(self, run: Manifest) -> None:
        temporary = self.directory / f".{run.id}-{uuid.uuid4().hex}.tmp"
        try:
            payload = (json.dumps(asdict(run), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if len(payload) > MAX_MANIFEST_BYTES:
                raise ValueError("History exceeds the 16 MiB per-execution limit; use smaller batches")
            with self.root.open(temporary, "xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self.root.replace(temporary, self.directory / f"{run.id}.json")
            self.root.sync_parent(temporary)
        except (OSError, ValueError) as error:
            raise HistoryError(f"Could not save history; stopped to protect documents: {error}") from error

    def load(self) -> list[Manifest]:
        if not self.exists():
            return []
        if not stat.S_ISDIR(self.root.stat(self.directory).st_mode):
            raise HistoryError("History path is not a directory.")
        runs = []
        sequences: set[int] = set()
        try:
            for path in sorted(self.directory.glob("*.json")):
                with self.root.open(path) as stream:
                    content = stream.read(MAX_MANIFEST_BYTES + 1)
                if len(content) > MAX_MANIFEST_BYTES:
                    raise ValueError("Manifest exceeds 16 MiB")
                run = _manifest(json.loads(content), path, self.root)
                if run.sequence in sequences:
                    raise ValueError("Duplicate execution sequence")
                sequences.add(run.sequence)
                runs.append(run)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            raise HistoryError(f"Invalid or unreadable history; no files will be restored: {error}") from error
        return sorted(runs, key=lambda run: run.sequence, reverse=True)


def get_history(directory: Path) -> list[Manifest]:
    store = HistoryStore(SafeRoot(directory))
    with store.lock(write=False):
        return store.load()
