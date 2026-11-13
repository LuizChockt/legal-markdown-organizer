# Local history and safe undo — 0.2.0

[English overview](../README.md) · [Português](../README.pt-BR.md)

The existing organization commands are unchanged. These additional commands work
from a source checkout; installed users can replace `python main.py` with
`python -m legal_organizer` or `legal-organizer`:

```powershell
python main.py "D:\Notes\Fictional Legal Base" --dry-run
python main.py "D:\Notes\Fictional Legal Base"
python main.py "D:\Notes\Fictional Legal Base" --history
python main.py "D:\Notes\Fictional Legal Base" --undo-last --dry-run
python main.py "D:\Notes\Fictional Legal Base" --undo-last
```

Paths above are fictional. `--include-txt` still opts into filename-based TXT
classification. Undo uses the recorded documents, so it does not accept that
option. `--history` is already read-only; do not combine it with `--dry-run`.

## What is recorded

Real attempts with candidate documents create `PATH/.legal-organizer/`. An
execution gets a random UUID (32 hexadecimal characters) and one `UUID.json`.
Repeated empty organization, history and dry-run do not create executions.
The directory also holds a process-lock file and a `.gitignore` containing `*`.
The repository additionally ignores `.legal-organizer/` at any depth.

JSON schema **1** is intentionally small and versioned:

| Field | Meaning |
| --- | --- |
| `schema`, `version` | Format version and program version that created the run. |
| `id`, `started_at`, `finished_at` | UUID, UTC start time and completion time (null if interrupted). |
| `sequence` | Increasing execution order under the process lock, independent of system-clock changes. |
| `root` | Selected directory's device/inode identity; no absolute path. |
| `status` | `running`, `completed`, `partial`, `interrupted`, `undoing`, `undo_partial` or `undone`. |
| `entries[].source` | One original top-level Markdown/TXT filename. |
| `entries[].destination` | Relative category/filename, including any conflict suffix. |
| `entries[].original` | Original SHA-256, size, timestamps and device/inode. |
| `entries[].move` | Organization checkpoint, created-target identity, verified fingerprint and error. |
| `entries[].undo` | Separate restoration checkpoint/fingerprint/error, or null. |

Each fingerprint includes `device`, `inode`, `size`, `mtime_ns`, `ctime_ns` and
`sha256`. A transfer contains `state`, `created`, `verified` and `error`. Transfer
states are `planned`, `created`, `copied`, `moved` and `aborted`. An undo transfer
in `moved` state means restored (or a verified duplicate safely removed).

Windows change-time fingerprints are consistently measured through open handles.
Path/handle identity, size and modification time are also compared; their `ctime`
fields are not mixed because of [CPython's Windows stat/fstat discrepancy](https://github.com/python/cpython/issues/157671).

No document text is put into the manifest, but filenames, hashes and errors are
private metadata. Do not attach manifests to public issues. They are neither
backups nor cryptographically authenticated records. Do not hand-edit them.
The loader validates paths, categories, filenames, identities, hashes and schema;
malformed/unreadable history blocks restoration rather than falling back to an
older run. A manifest is limited to 16 MiB; organize large collections in batches.

## Copy, verify, journal, delete

For each document, the program:

1. Hashes the original, reads its classification through a confined file handle,
   then records the intended relative destination.
2. Exclusively creates a destination: an occupied path cannot be overwritten.
   It records the identity of the file it actually created before copying.
3. Copies bytes, flushes and synchronizes the file, preserves modification time
   (and POSIX permission bits), then verifies both source and destination.
4. Atomically saves and synchronizes the `copied` checkpoint before removing the
   source. Only then does it record `moved` and count a successful movement.

On Windows, timestamps are applied through `SetFileTime` on the already-open
destination handle, without reopening its path or requiring a newer Python's
`utime` capabilities.

JSON updates use a new, exclusively created temporary file, `fsync` and atomic
replacement. POSIX directories are synchronized as well. Windows has no portable
directory-fsync equivalent. A journal write failure stops the whole execution.
Ordinary per-file errors are recorded while unrelated files continue.

At any checkpoint, at least one complete, verified copy must remain before a
source can be deleted. Live copy failures can remove only the partial target
created by that call, after checking its identity. A replaced target is retained.
Crash artifacts whose ownership/content cannot be established are retained for
manual review. Stale `.tmp` files are not promoted automatically into history.

## Undo and retry behavior

`--undo-last` selects the newest execution whose status is not `undone`, including
partial/interrupted attempts. Entries are examined in reverse order. Multiple
completed executions can be undone one at a time; there is no arbitrary-ID undo
in this version. An execution with pending conflicts stays selected on retries.

| Situation | Result |
| --- | --- |
| Organized file unchanged, original path vacant | Copy, verify, journal and restore to the exact original name. |
| Original path already occupied | Preserve both paths and report a conflict; no overwrite or auto-renaming. |
| Organized file edited, metadata changed, replaced, missing or unreadable | Skip it with an error; retain other available documents. |
| Organization copied successfully but could not remove the original | Remove only the recorded, unchanged duplicate when the original still matches its original fingerprint. |
| Process stopped after verified copy, before/after source deletion | Recover using identities and the saved `copied` checkpoint. |
| Undo stopped after its verified original copy was written | Verify both copies again and resume the pending deletion without recopying/overwriting. |
| Unverified partial copy or unknown file at a planned destination | Retain it and require manual inspection. |
| File already restored in this execution | Skip it; retry only pending entries. |

Undo never deletes whole directories. Empty category folders and unrelated
documents remain. Incomplete runs block new organization until reviewed and
undone, preventing accidental chains of duplicate copies.

`--undo-last --dry-run` performs the same eligibility checks and reports proposed
restorations/verified duplicate cleanup without changing documents, manifests,
lock files or directory modification times. Ordinary filesystem reads can update
access times. A later real run rechecks everything; a preview reserves no paths.

## Resolving a pending execution

1. Close editors and pause other programs moving the same documents. Keep an
   independent backup of the base before manually resolving conflicts.
2. Read `--history`, then run `--undo-last --dry-run`. Review each error.
3. For an occupied original name, move the unrelated occupant somewhere safe;
   do not overwrite or discard it. Retry the preview and then the real undo.
4. For modified/replaced documents, choose and preserve the desired version
   manually. This version has no force/overwrite switch or automatic way to
   approve an edited document. Use your backup/manual recovery as appropriate.
5. For an unverified partial artifact, inspect both paths and move that artifact
   into a separate quarantine after verifying the complete original. Retry undo
   once the ambiguous path is vacant. Do not alter JSON to claim verification.
6. For corrupt/unreadable history or missing originals, stop automatic recovery;
   preserve the entire directory and inspect permissions, backups and artifacts.

A normal retry returns `0` only when all selected entries are resolved. Errors
return `1`; invalid arguments/root paths return `2`; a handled Ctrl+C returns
`130`. Some files may have succeeded before a nonzero exit. Read the summary.

## Concurrency and filesystem limits

OS locks coordinate separate organizer processes and are automatically released
when a process exits. The persistent `lock` filename does not indicate a stale
lock; do not delete it to bypass a running process. Reads lock an existing history
without rewriting it. With no history, preview/history do not create a lock.

Source symlinks are skipped. Category/history symlinks and Windows reparse points
(including junctions) are rejected. POSIX file creation, reads, replacement and
deletion use no-follow directory descriptors. Windows uses reparse-point and
identity checks around path operations. Manifest paths are confined to one
top-level source name and a known category destination. Non-portable Windows
filenames are refused consistently across platforms.

Use a local filesystem exposing stable file identities, exclusive creation,
locking and atomic replacement. Network shares, sync folders and unusual virtual
filesystems may not provide these guarantees. Copying a manifest to a different
directory/filesystem does not authorize restoration: the root identity must match.

Hashes/identities detect ordinary concurrent edits, but a final check/delete
race cannot be fully eliminated portably, especially on Windows. A malicious
process with the same filesystem permissions is outside the security boundary.
Power loss, hardware faults, lost manifests, unavailable storage and manually
modified history can still require backups. ACLs, ownership, extended attributes
and every platform-specific timestamp are not guaranteed to round-trip.

**Undo complements backups; it does not replace them.**
