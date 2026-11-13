"""Confined file access and fingerprints for conservative, journaled moves."""

import hashlib
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast


@dataclass(frozen=True)
class Identity:
    device: int
    inode: int


@dataclass(frozen=True)
class Fingerprint:
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    sha256: str


def identity(info: os.stat_result) -> Identity:
    return Identity(info.st_dev, info.st_ino)


def is_link(info: os.stat_result) -> bool:
    """Reject Windows junctions/reparse points as well as POSIX symlinks."""
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class SafeRoot:
    """Access only regular files beneath a fixed directory identity.

    POSIX operations use no-follow directory descriptors for every component.
    Windows uses reparse-point and identity checks before/after path access.
    The OS lock coordinates organizer processes, not unrelated editors.
    """

    def __init__(self, directory: Path):
        directory = Path(directory).expanduser()
        if not directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")
        if not directory.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {directory}")
        if is_link(directory.lstat()):
            raise OSError("The selected directory is a symlink or reparse point; use its real path.")
        self.path = directory.resolve(strict=True)
        self.identity = identity(self.path.lstat())
        if self.identity.inode == 0:
            raise OSError("This filesystem does not expose stable file identities; use a local supported filesystem.")
        self._dir_fd = os.name != "nt" and os.open in os.supports_dir_fd

    def relative(self, path: Path) -> Path:
        relative = path.relative_to(self.path)
        if not relative.parts or any(part in (".", "..") for part in relative.parts):
            raise OSError(f"Unsafe path: {path}")
        return relative

    @contextmanager
    def parent(self, path: Path) -> Iterator[tuple[Path, int | None]]:
        parts = self.relative(path).parts[:-1]
        if identity(self.path.lstat()) != self.identity or is_link(self.path.lstat()):
            raise OSError("The selected directory changed; stop and inspect it.")
        current = self.path
        descriptor = None
        try:
            if self._dir_fd:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(self.path, flags)
                if identity(os.fstat(descriptor)) != self.identity:
                    raise OSError("The selected directory changed while opening it.")
            for part in parts:
                current /= part
                if descriptor is not None:
                    next_descriptor = os.open(part, flags, dir_fd=descriptor)
                    os.close(descriptor)
                    descriptor = next_descriptor
                else:
                    info = current.lstat()
                    if is_link(info) or not stat.S_ISDIR(info.st_mode):
                        raise OSError(f"Unsafe directory (symlink/reparse point or non-directory): {current}")
            yield current, descriptor
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def stat(self, path: Path) -> os.stat_result:
        with self.parent(path) as (_, descriptor):
            if descriptor is not None:
                info = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
            else:
                info = path.lstat()
            if is_link(info):
                raise OSError(f"Symlink or reparse point refused: {path}")
            return info

    def exists(self, path: Path) -> bool:
        try:
            self.stat(path)
        except FileNotFoundError:
            return False
        return True

    def mkdir(self, path: Path) -> None:
        created = False
        with self.parent(path) as (_, descriptor):
            try:
                if descriptor is not None:
                    os.mkdir(path.name, mode=0o700, dir_fd=descriptor)
                else:
                    path.mkdir(mode=0o700)
                created = True
            except FileExistsError:
                pass
        if not stat.S_ISDIR(self.stat(path).st_mode):
            raise NotADirectoryError(f"Category path is not a directory: {path}")
        if created:
            self.sync_parent(path)

    def open(self, path: Path, mode: str = "rb") -> BinaryIO:
        flags = {"rb": os.O_RDONLY, "r+b": os.O_RDWR, "xb": os.O_WRONLY | os.O_CREAT | os.O_EXCL}[mode]
        flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with self.parent(path) as (_, descriptor):
            if mode != "xb":
                before = self.stat(path)
                if not stat.S_ISREG(before.st_mode):
                    raise OSError(f"Not a regular file: {path}")
            fd = os.open(path.name if descriptor is not None else path, flags, 0o600, dir_fd=descriptor)
            try:
                info = os.fstat(fd)
                if is_link(info) or not stat.S_ISREG(info.st_mode):
                    raise OSError(f"Not a regular file: {path}")
                if info.st_ino == 0:
                    raise OSError(f"Stable file identity is unavailable: {path}")
                if mode != "xb" and identity(info) != identity(before):
                    raise OSError(f"File was replaced while opening: {path}")
                if identity(self.stat(path)) != identity(info):
                    raise OSError(f"File path changed while opening: {path}")
                return cast(BinaryIO, os.fdopen(fd, mode))
            except BaseException:
                os.close(fd)
                raise

    def fingerprint(self, path: Path) -> Fingerprint:
        with self.open(path) as stream:
            before = os.fstat(stream.fileno())
            hasher = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(block)
            digest = hasher.hexdigest()
            after = os.fstat(stream.fileno())
        if _signature(before) != _signature(after) or _signature(self.stat(path)) != _signature(after):
            raise OSError(f"File changed while reading; close editors and retry: {path}")
        return Fingerprint(*_signature(after), digest)

    def verify(self, path: Path, expected: Fingerprint) -> None:
        if self.fingerprint(path) != expected:
            raise OSError(f"File was modified or replaced; retained for manual review: {path}")

    def unlink(self, path: Path, expected: Identity) -> None:
        with self.parent(path) as (_, descriptor):
            if identity(self.stat(path)) != expected:
                raise OSError(f"Refusing to remove a replaced file: {path}")
            if descriptor is not None:
                os.unlink(path.name, dir_fd=descriptor)
            else:
                path.unlink()

    def replace(self, source: Path, destination: Path) -> None:
        with self.parent(source) as (_, source_fd), self.parent(destination) as (_, target_fd):
            os.replace(
                source.name if source_fd is not None else source,
                destination.name if target_fd is not None else destination,
                src_dir_fd=source_fd, dst_dir_fd=target_fd,
            )

    def sync_parent(self, path: Path) -> None:
        # Directory fsync is unavailable on Windows. File contents are still fsynced.
        with self.parent(path) as (_, descriptor):
            if descriptor is not None:
                os.fsync(descriptor)

    def preserve_metadata(self, source_info: os.stat_result, target: BinaryIO, path: Path) -> None:
        """Preserve mode and timestamps without reopening POSIX paths."""
        if sys.platform != "win32":
            os.fchmod(target.fileno(), stat.S_IMODE(source_info.st_mode) & 0o777)
            os.utime(target.fileno(), ns=(source_info.st_atime_ns, source_info.st_mtime_ns))
        else:
            # Windows does not implement utime(..., follow_symlinks=False) on
            # every supported Python. Set times on our already-open target
            # handle instead of reopening a potentially replaced pathname.
            import ctypes
            import msvcrt
            from ctypes import wintypes

            set_file_time = ctypes.WinDLL("kernel32", use_last_error=True).SetFileTime
            pointer = ctypes.POINTER(wintypes.FILETIME)
            set_file_time.argtypes = [wintypes.HANDLE, pointer, pointer, pointer]
            set_file_time.restype = wintypes.BOOL

            def file_time(nanoseconds: int) -> wintypes.FILETIME:
                # FILETIME counts 100 ns ticks since 1601, not Unix's 1970 epoch.
                ticks = nanoseconds // 100 + 116444736000000000
                return wintypes.FILETIME(ticks & 0xFFFFFFFF, ticks >> 32)

            access = file_time(source_info.st_atime_ns)
            modified = file_time(source_info.st_mtime_ns)
            if not set_file_time(msvcrt.get_osfhandle(target.fileno()), None, ctypes.byref(access), ctypes.byref(modified)):
                raise ctypes.WinError(ctypes.get_last_error())
