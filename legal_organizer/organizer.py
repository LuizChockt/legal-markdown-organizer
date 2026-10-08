"""Organize top-level documents while preserving bytes and avoiding overwrites."""

import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .classifier import classify_file
from .rules import DEFAULT_EXTENSIONS, OPTIONAL_EXTENSIONS


@dataclass
class OrganizationResult:
    """Small data container for the CLI; it holds no organization logic."""

    moves: list[tuple[Path, Path]] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)
    errors: list[tuple[Path, str]] = field(default_factory=list)


def available_destination(destination: Path, reserved: set[Path] | None = None) -> Path:
    """Add a numbered suffix for files, directories, symlinks or planned moves."""
    reserved = reserved if reserved is not None else set()
    candidate = destination
    suffix = 1
    while candidate.exists() or candidate.is_symlink() or candidate in reserved:
        candidate = destination.with_name(f"{destination.stem}_{suffix}{destination.suffix}")
        suffix += 1
    return candidate


def _move_without_overwrite(source: Path, destination: Path) -> Path:
    """Copy into an exclusively created target, then remove the original.

    shutil.move can overwrite a target that appears after an existence check.
    Opening with 'xb' closes that race and works the same on Windows and POSIX.
    The source stays in place if copying or metadata preservation fails.
    """
    original_destination = destination
    with source.open("rb") as source_stream:
        while True:
            try:
                target_stream = destination.open("xb")
                break
            except FileExistsError:
                destination = available_destination(original_destination)
        try:
            with target_stream:
                shutil.copyfileobj(source_stream, target_stream)
            shutil.copystat(source, destination)
        except OSError:
            destination.unlink(missing_ok=True)
            raise
    # If deletion fails, retain both complete copies and report the error.
    source.unlink()
    return destination


def organize_directory(
    directory: Path, *, dry_run: bool = False, include_txt: bool = False,
) -> OrganizationResult:
    """Scan one directory, create only needed categories and return a report.

    A dry run only reads files and records planned destinations. Source
    symlinks are skipped; category symlinks are rejected to keep writes local
    to the selected base. Per-file errors do not stop unrelated documents.
    """
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")

    extensions = DEFAULT_EXTENSIONS | OPTIONAL_EXTENSIONS if include_txt else DEFAULT_EXTENSIONS
    candidates = sorted(
        (
            path for path in directory.iterdir()
            if path.suffix.lower() in extensions and not path.is_symlink() and path.is_file()
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )
    result = OrganizationResult()
    reserved: set[Path] = set()
    for source in candidates:
        try:
            category = classify_file(source)
            category_directory = directory / category
            if category_directory.is_symlink():
                raise OSError(f"Category directory is a symlink: {category_directory}")
            if category_directory.exists() and not category_directory.is_dir():
                raise NotADirectoryError(f"Category path is not a directory: {category_directory}")
            destination = available_destination(category_directory / source.name, reserved)
            if not dry_run:
                category_directory.mkdir(exist_ok=True)
                destination = _move_without_overwrite(source, destination)
            reserved.add(destination)
            result.moves.append((source, destination))
            result.counts[category] += 1
        except (OSError, UnicodeError) as error:
            result.errors.append((source, str(error)))
    return result
