"""Command-line arguments, validation and presentation."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .history import HistoryError, get_history
from .organizer import OrganizationResult, organize_directory, undo_last
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
    print(f"{result.skipped} unrelated entry/entries skipped.")
    if result.run_id:
        print(f"Execution: {result.run_id}")


def _print_undo(result: OrganizationResult, directory: Path, dry_run: bool) -> None:
    if result.run_id is None:
        print("No organization to undo.")
        return
    if dry_run:
        print("[DRY RUN]\n")
    print(f"Execution: {result.run_id}")
    for source, destination in result.moves:
        print(f"{source.relative_to(directory).as_posix()}\n-> {destination.name}\n")
    for path in result.cleaned:
        print(f"Verified duplicate: {path.relative_to(directory).as_posix()} (original retained)")
    if dry_run:
        print(f"{len(result.moves)} file(s) would be restored; {len(result.cleaned)} duplicate(s) would be removed.")
        print("No files were modified.")
    else:
        status = "Undo incomplete; resolve the reported conflicts and retry." if result.errors else "Undo completed."
        print(status)
        print(f"{len(result.moves)} file(s) restored; {len(result.cleaned)} verified duplicate(s) removed.")
    print(f"{result.skipped} entry/entries already restored or never moved; {len(result.errors)} pending error(s).")
    print("Undo is not a backup. Modified, missing or replaced files require manual review.")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; return 0 on success, 1 for per-file failures."""
    parser = argparse.ArgumentParser(
        description="Organize legal Markdown documents by filename or simple front matter.",
    )
    parser.add_argument("path", type=Path, metavar="PATH", help="Directory containing legal .md files.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating or moving anything.")
    parser.add_argument("--include-txt", action="store_true", help="Also organize .txt files by filename.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--history", action="store_true", help="List local executions without modifying files.")
    actions.add_argument("--undo-last", action="store_true", help="Undo the latest pending execution; never overwrite originals.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    if args.history and (args.dry_run or args.include_txt):
        parser.error("--history is already read-only; do not combine it with --dry-run or --include-txt.")
    if args.undo_last and args.include_txt:
        parser.error("--undo-last uses the recorded files; do not combine it with --include-txt.")
    directory = args.path.expanduser().absolute()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    try:
        if args.history:
            runs = get_history(directory)
            if not runs:
                print("No organization history.")
            for run in runs:
                moved = sum(entry.move.state == "moved" for entry in run.entries)
                restored = sum(entry.undo is not None and entry.undo.state == "moved" for entry in run.entries)
                print(f"{run.started_at}  {run.id}  {run.status}  moved={moved} restored={restored}")
            return 0
        if args.undo_last:
            result = undo_last(directory, dry_run=args.dry_run)
        else:
            result = organize_directory(directory, dry_run=args.dry_run, include_txt=args.include_txt)
    except HistoryError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        print("Interrupted. Inspect --history and preview --undo-last --dry-run before retrying.", file=sys.stderr)
        return 130
    directory = directory.resolve()
    if args.undo_last:
        _print_undo(result, directory, args.dry_run)
    else:
        _print_result(result, directory, args.dry_run)
    for source, message in result.errors:
        logging.error("Could not %s %s: %s", "restore" if args.undo_last else "organize", source.name, message)
    return 1 if result.errors else 0
