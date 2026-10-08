# Legal Markdown Organizer

[![Tests](https://github.com/LuizChockt/legal-markdown-organizer/actions/workflows/tests.yml/badge.svg)](https://github.com/LuizChockt/legal-markdown-organizer/actions/workflows/tests.yml)

A lightweight Python CLI for automatically organizing legal Markdown documents
using filename patterns and optional front matter metadata.

**Markdown-first legal document organizer.** Built for lawyers, law students,
legal researchers, Markdown knowledge bases and Obsidian users, with particular
attention to Brazilian legal document names. The application is deliberately
small, deterministic and understandable by beginner/intermediate Python developers.

## Features

- Markdown (`.md`) is the default and primary format; `.txt` is opt-in.
- Eighteen categories with separate folders for dispatches, decisions, judgments,
  appellate judgments, interlocutory appeals and other appeals.
- Case-insensitive and accent-insensitive classification.
- Spaces, underscores and hyphens work as filename separators.
- Optional simple YAML front matter with `type` taking priority.
- A read-only `--dry-run` preview, including conflict suffixes.
- Numbered filenames protect existing documents from overwrites.
- Original document bytes, filenames, front matter, headings, tags and wikilinks
  are preserved; only a conflicting destination requires a filename suffix.
- Local processing, type hints, pytest tests and GitHub Actions.
- Python 3.11+ and **no third-party runtime dependencies**.

## How it works

The organizer scans **only files directly inside the selected directory**.
It does not recurse into subfolders or reprocess documents already in category
folders. Only categories needed for successfully organized documents are created;
an empty directory stays empty.

Classification uses this order:

1. A recognized `type` in opening Markdown front matter.
2. Filename keywords, evaluated in the priority order below.
3. `Outros` when no rule matches.

A missing, empty, unknown or unsupported `type` falls back to the filename.
An explicit `type: Outros` overrides the filename. The document body is never
used for classification.

```text
Before

legal-notes/
├── agravo_instrumento.md
├── despacho_intimacao.md
├── sentenca.md
├── recurso_especial.md
└── acordao_tjrs.md
```

```text
After

legal-notes/
├── Agravos/
│   └── agravo_instrumento.md
├── Despachos/
│   └── despacho_intimacao.md
├── Sentencas/
│   └── sentenca.md
├── Recursos/
│   └── recurso_especial.md
└── Acordaos/
    └── acordao_tjrs.md
```

## Legal categories

Folder names are Portuguese and use ASCII for portability. The table follows
the actual rule priority, from highest to lowest. Matching any keyword in an
earlier row takes precedence over matching a later row.

| Category | Example filename keywords |
| --- | --- |
| `Despachos` | `despacho`, `despacho de intimacao` |
| `Sentencas` | `sentenca`, `sentenca procedente`, `sentenca improcedente` |
| `Acordaos` | `acordao`, `julgamento colegiado` |
| `Agravos` | `agravo`, `agravo de instrumento`, `agravo interno`, `agravo regimental` |
| `Contestacoes` | `contestacao`, `defesa` |
| `Manifestacoes` | `manifestacao`, `peticao intermediaria` |
| `Peticoes` | `peticao`, `peticao inicial`, `inicial` |
| `Recursos` | `recurso`, `apelacao`, `resp`, `re`, `embargos de declaracao`, `contrarrazoes` |
| `Decisoes` | `decisao`, `decisao interlocutoria`, `liminar`, `tutela` |
| `Procuracoes` | `procuracao`, `substabelecimento` |
| `Contratos` | `contrato`, `contrato de honorarios`, `acordo extrajudicial` |
| `Certidoes` | `certidao`, `antecedentes`, `negativa`, `positiva`, `objeto e pe`, `narratoria` |
| `Jurisprudencia` | `jurisprudencia`, `precedente`, `sumula`, `tema repetitivo`, `repercussao geral` |
| `Legislacao` | `lei`, `decreto`, `codigo`, `constituicao`, `resolucao`, `portaria` |
| `Doutrina` | `doutrina`, `artigo`, `livro`, `comentario`, `resumo doutrinario` |
| `Documentos_Pessoais` | `documento pessoal`, `rg`, `cpf`, `identidade`, `cnh`, `comprovante de residencia` |
| `Financeiro` | `financeiro`, `recibo`, `boleto`, `pagamento`, `nota fiscal`, `custas`, `honorarios` |
| `Outros` | Fallback or an explicit front matter category |

All categories, keywords, metadata aliases, priorities and supported extensions
are centralized in [`legal_organizer/rules.py`](legal_organizer/rules.py). To add
a category, add its folder name to `CATEGORY_PRIORITY` and its keyword tuple to
`KEYWORDS`. Add optional metadata aliases to `TYPE_ALIASES`. Keep `Outros` last.
Use simple folder names without path separators.

## Filename classification

Normalization uses Python's `unicodedata` to lowercase comparison strings,
remove accents, replace `_` and `-` with spaces, and collapse repeated whitespace.
It never renames an original document just to classify it.

These names all resolve to `Agravos`:

```text
AGRAVO DE INSTRUMENTO.md
agravo_de_instrumento.md
Agravo-de-Instrumento.md
agravo instrumento.md
```

Likewise, `Sentença.md`, `sentenca.md` and `SENTENCA.md` resolve to `Sentencas`.
Keywords match complete words or phrases; punctuation separates words. A short
keyword such as `re` will not match inside `relatorio` or `secretaria`.
Extensions are case-insensitive, so `.MD` also works.

Examples of precedence:

```text
agravo_em_recurso_especial.md  -> Agravos
sentenca_decisao.md            -> Sentencas
peticao_intermediaria.md       -> Manifestacoes
contestacao.md                -> Contestacoes
contrato_honorarios.md         -> Contratos
recurso_especial.md            -> Recursos
```

Broad words such as `inicial`, `negativa` and `artigo` can still cause ambiguous
matches. For a known document, use a specific `type` to choose its category.

## Front Matter classification

For a file named `documento_123.md`:

```markdown
---
type: sentenca
process: EXAMPLE-001
court: Fictional Example Court
tags:
  - fictional-example
  - processo
---

# Fictional judgment

This document does not refer to a real lawsuit, client or party.
```

The file goes to `Sentencas/documento_123.md`, regardless of its filename.
Values such as `agravo`, `agravo de instrumento`, `sentença`, `Agravos`,
`Documentos_Pessoais` and the explicit aliases in `rules.py` are supported.
Category names, aliases and keyword phrases must match the entire `type` value.

This is a **small subset of YAML**, implemented without a YAML dependency:

- The opening `---` must be on the first line, optionally following a UTF-8 BOM.
- A closing `---` is required; an unclosed header is ignored.
- Only top-level `key: value` scalar pairs are extracted. Keys are case-sensitive;
  use the lowercase key `type`.
- Plain values and simple single/double-quoted strings are supported.
- A comment after a value can start with a space followed by `#`.
- Lists, nested mappings, multiline blocks, flow collections, anchors, aliases,
  YAML tags and quote escape sequences are not supported.
- Only `type` influences classification. `process` and `court` are plain metadata;
  they do not create process folders or trigger automatic detection.
- `.txt` files use filename classification only.

Markdown files must use UTF-8 or UTF-8 with BOM. Unreadable files and decoding
errors are reported, and their source documents are retained.

## Installation

You need **Python 3.11 or later**. Download the source or clone your copy of the
repository, then enter its directory:

```bash
git clone https://github.com/LuizChockt/legal-markdown-organizer.git
cd legal-markdown-organizer
```

The CLI works directly from the checkout, without installing anything:

```bash
python main.py --help
```

For development and the installed `legal-organizer` command, create a virtual
environment and install the development extra.

Windows PowerShell, without requiring script activation:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe main.py --help
```

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python main.py --help
```

The development extra installs `pytest`; the organizer itself uses only the
standard library. Installation may download build/test tools, while document
processing requires no network connection. Packaging is configured in
[`pyproject.toml`](pyproject.toml) using the standard
[Python packaging metadata format](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).

## Usage

Preview first, then organize the selected base:

```bash
python main.py "/path/to/legal-notes" --dry-run
python main.py "/path/to/legal-notes"
```

On Windows, quote paths with spaces and accents:

```powershell
python main.py "D:\Direito\Base Jurídica" --dry-run
python main.py "D:\Direito\Base Jurídica"
```

With the virtual environment above, replace `python` with
`.\.venv\Scripts\python.exe` on Windows or `.venv/bin/python` on Linux/macOS.

Include plain text documents explicitly:

```bash
python main.py "/path/to/legal-notes" --include-txt
```

After installation, the same CLI is available as `legal-organizer`:

```powershell
.\.venv\Scripts\legal-organizer.exe "D:\Direito\Base Jurídica" --dry-run
```

Display help or version information:

```bash
python main.py --help
python main.py --version
```

A successful execution reports the categories actually used:

```text
Organization completed.

Despachos: 1
Sentencas: 1
Acordaos: 1
Agravos: 1
Recursos: 1

5 files processed.
```

Exit codes are `0` for success, `1` for one or more per-file failures, and `2`
for an invalid directory or command-line arguments. Files that fail are reported
on standard error, while unrelated documents continue to be processed. Counts
include only successful moves, or successful plans in dry-run mode.

If a destination already exists, a suffix is added before the extension:

```text
Agravos/agravo_instrumento.md
Agravos/agravo_instrumento_1.md
Agravos/agravo_instrumento_2.md
```

Files, directories and symlinks occupying a destination name all reserve it.
Exclusive binary creation prevents overwriting even if a file appears after
planning. The organizer copies the original bytes, preserves available file
metadata with `shutil.copystat`, and removes the source only after the copy
finishes. If copying fails, the source is retained and the partial target is
removed when possible. If removing the source fails, both complete copies are
retained and the error is reported; inspect these copies before retrying.

Keep a backup and close document editors before organizing a working base.
This version has no undo command or protection against external edits made
during a move. Source file symlinks are skipped, and category-directory symlinks
are rejected.

## Dry-run mode

```bash
python main.py "/path/to/legal-notes" --dry-run
```

```text
[DRY RUN]

agravo_instrumento.md
-> Agravos/agravo_instrumento.md

despacho_intimacao.md
-> Despachos/despacho_intimacao.md

recurso_especial.md
-> Recursos/recurso_especial.md

sentenca.md
-> Sentencas/sentenca.md

Despachos: 1
Sentencas: 1
Agravos: 1
Recursos: 1

4 files would be organized.
No files were modified.
```

Dry-run does not create category directories, move or rename documents, or edit
Markdown in the selected base. Existing targets and other planned moves are
considered when choosing suffixes. If the base stays unchanged, the subsequent
real execution chooses the same destinations.

Try the included fictional documents safely:

```bash
python main.py examples --dry-run
```

## Obsidian compatibility

Use the organizer with regular Markdown knowledge bases or **Obsidian vaults**.
No Obsidian API or plugin is required. The program reads standard files and
moves top-level notes into category folders. Existing subfolders, `.obsidian`
settings and attachments are not scanned or moved.

Wikilinks (`[[wikilinks]]`), headings, tags, Markdown text and existing front
matter remain byte-for-byte unchanged. The program does not rewrite references.
Moving a note can affect relative or folder-specific links, and a collision
suffix can affect references to its filename. Check these links after organizing
a copy of your vault; preservation of text does not guarantee link resolution.

## Project structure

```text
legal-markdown-organizer/
├── legal_organizer/
│   ├── __init__.py
│   ├── cli.py
│   ├── classifier.py
│   ├── frontmatter.py
│   ├── organizer.py
│   └── rules.py
├── tests/
│   ├── __init__.py
│   ├── test_classifier.py
│   ├── test_frontmatter.py
│   ├── test_organizer.py
│   └── test_cli.py
├── examples/
│   ├── agravo_instrumento.md
│   ├── despacho.md
│   └── recurso_especial.md
├── .github/
│   └── workflows/
│       └── tests.yml
├── .gitignore
├── LICENSE
├── README.md
├── pyproject.toml
└── main.py
```

`rules.py` defines the policy; `frontmatter.py` only extracts simple metadata;
`classifier.py` normalizes and classifies; `organizer.py` handles traversal,
safe moves, dry-run and statistics; `cli.py` owns arguments and output.
One small dataclass carries the results between the organizer and CLI.

## Running tests

Install the development extra as shown above, then run from the project root:

```bash
python -m pytest
```

With the Windows virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

With the Linux/macOS virtual environment:

```bash
.venv/bin/python -m pytest
```

Tests use `tmp_path`, temporary directories and fictional data. They cover legal
categories, accents, capitalization, separators, metadata priority, specific
rule priority, unsupported formats, collisions, empty and missing directories,
exact byte preservation, copy failures, a destination created after planning,
dry-run filesystem snapshots and a real CLI subprocess with spaces and accents
in its path.

The workflow in [`.github/workflows/tests.yml`](.github/workflows/tests.yml)
runs on `push` and `pull_request`, installs `.[dev]` and executes pytest on
Windows and Ubuntu with Python 3.11 and 3.14. It uses the official
[checkout](https://github.com/actions/checkout) and
[setup-python](https://github.com/actions/setup-python) actions.

## Privacy

> All document processing is performed locally. No legal documents or metadata
> are uploaded to external services.

The application makes no API requests, uses no cloud service and does not send
documents for external analysis or store them outside the selected base. There
is no telemetry or external database. CLI output includes filenames and local
paths, so treat saved terminal output according to your own confidentiality needs.

All files in `examples/` and all test fixtures are fictional. They contain no
real clients, parties, lawsuit numbers or confidential legal documents.
Keep personal vaults outside this repository or in ignored directories such as
`vaults/`, `private/` or `local-data/`. The `.gitignore` provides useful defaults;
it does not identify confidential files placed elsewhere.

## Limitations

- Classification is deterministic and does not semantically understand legal text.
- No PDF, DOC/DOCX, image reading, PDF conversion or OCR.
- No AI, external API, database or semantic model.
- No automatic party, court or lawsuit-number detection from document content.
- No recursive scanning, moving whole folders or automatic process folders.
- No document text, headings, tags, links or front matter modifications.
- Only simple UTF-8 front matter scalar pairs are supported.
- Keyword priority may need adjustment for a particular naming convention.
- Moves are handled per file, without a transaction for the whole directory.
- No undo; concurrent edits, power loss and filesystem metadata differences
  require ordinary backups and care when organizing important originals.

## Roadmap

Possible future improvements, **not implemented in this version**:

- Recursive folder scanning.
- Configurable rules in TOML or JSON.
- Undo command.
- Custom categories from user configuration.
- Extraction of Brazilian CNJ lawsuit numbers.
- Automatic process folder creation.
- Richer YAML front matter support.
- Markdown tag-based classification.
- Court detection.
- Party detection.
- PDF-to-Markdown integration.
- OCR.
- Semantic classification.
- Optional local AI classification.

A future process-based structure could look like this, using a fictional
placeholder identifier rather than a real lawsuit number:

```text
Processos/
└── EXAMPLE-001/
    ├── Peticoes/
    ├── Despachos/
    ├── Decisoes/
    ├── Sentencas/
    ├── Agravos/
    └── Recursos/
```

## License

This project is distributed under the [MIT License](LICENSE).
