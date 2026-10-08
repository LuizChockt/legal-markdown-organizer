"""Command-line arguments, validation and presentation."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .organizer import OrganizationResult, organize_directory
from .rules import CATEGORY_PRIORITY


def _print_result(result: OrganizationResult, directory: Path, dry_run: bool) -> None:
    if dry_run:
        print("[DRY RUN]\n")
    for source, destination in result.moves:
        print(f"{source.name}\n-> {destination.relative_to(directory).as_posix()}\n")

    if not dry_run:
        status = "Organization completed with errors." if result.errors else "Organization completed."
        print(f"{status}\n")
    for category in CATEGORY_PRIORITY:
        if result.counts[category]:
            print(f"{category}: {result.counts[category]}")

    count = len(result.moves)
    noun = "file" if count == 1 else "files"
    if dry_run:
        print(f"\n{count} {noun} would be organized.\nNo files were modified.")
    else:
        print(f"\n{count} {noun} processed.")
    if result.errors:
        print(f"{len(result.errors)} file(s) could not be organized.")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; return 0 on success, 1 for per-file failures."""
    parser = argparse.ArgumentParser(
        description="Organize legal Markdown documents by filename or simple front matter.",
    )
    parser.add_argument("path", type=Path, metavar="PATH", help="Directory containing legal .md files.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating or moving anything.")
    parser.add_argument("--include-txt", action="store_true", help="Also organize .txt files by filename.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    directory = args.path.expanduser()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    try:
        result = organize_directory(directory, dry_run=args.dry_run, include_txt=args.include_txt)
    except OSError as error:
        parser.error(str(error))
    _print_result(result, directory, args.dry_run)
    for source, message in result.errors:
        logging.error("Could not organize %s: %s", source.name, message)
    return 1 if result.errors else 0
