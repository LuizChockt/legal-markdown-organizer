# Changelog

## [0.2.0] — 2026-11-13

### Added

- Local, versioned JSON execution manifests with unique IDs, relative paths,
  SHA-256 hashes, filesystem identities and per-file checkpoints.
- `--history`, `--undo-last` and `--undo-last --dry-run`, preserving existing
  organization commands and the installed `legal-organizer` entrypoint.
- Retriable partial undo, crash recovery at verified-copy checkpoints and safe
  cleanup of a verified duplicate when the original could not be removed.
- Cross-process OS locks, Windows junction/reparse-point rejection and POSIX
  no-follow directory-descriptor access.
- Fictional-data tests for conflicts, concurrent edits, interrupted processes,
  malformed history, Unicode paths and exact byte preservation.
- Installed-wheel smoke checks on Linux, Windows and macOS; Python 3.12/3.13
  checks in addition to the existing 3.11/3.14 boundary matrix.
- A version-specific release workflow gated on successful main-branch tests,
  publishing an immutable tag, wheel, source archive and SHA-256 checksums.

### Changed

- Copies are flushed, hashed and journaled before removing source files.
- Journal failures stop the execution instead of continuing with unrecorded
  movements. Incomplete executions must be reviewed before organizing again.
- Summaries include skipped entries, execution IDs and pending restore errors.
- Read-only previews/history do not create manifests, lock files or directories.
- Local manifests are ignored both by this repository and their own `.gitignore`.

### Limits

- Undo does not replace backups. Modified/replaced/missing files and unverified
  crash artifacts remain for manual review. No original is overwritten.
- Empty category folders remain after undo; links are not rewritten.
- No new runtime dependency, recursive scanning, GUI or semantic classification.

## 0.1.0

- Initial deterministic Markdown-first organizer, optional TXT, simple front
  matter, collision suffixes, previews, bilingual docs and cross-platform tests.

[0.2.0]: https://github.com/LuizChockt/legal-markdown-organizer/releases/tag/v0.2.0
