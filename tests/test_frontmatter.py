from pathlib import Path

import pytest

from legal_organizer.frontmatter import read_frontmatter


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("---\ntype: agravo\n---\n# Body\n", {"type": "agravo"}),
        ("---\ntype: 'sentença'\n---\n", {"type": "sentença"}),
        ('---\ntype: "despacho"\n---\n', {"type": "despacho"}),
        ("---\ntype: agravo # comment\n---\n", {"type": "agravo"}),
        ("---\ntype: 'agravo' # comment\n---\n", {"type": "agravo"}),
        ("---\nprocess: EXAMPLE-001\ncourt: Fictional: Court\n---\n",
         {"process": "EXAMPLE-001", "court": "Fictional: Court"}),
        ("---\n# comment\ninvalid line\ntype: agravo\n---\n", {"type": "agravo"}),
        ("---\ntype: # no value\n---\n", {}),
    ],
)
def test_simple_metadata(tmp_path: Path, content: str, expected: dict[str, str]) -> None:
    document = tmp_path / "document.md"
    document.write_text(content, encoding="utf-8")
    assert read_frontmatter(document) == expected


@pytest.mark.parametrize("content", [
    "", "# Heading\n---\ntype: agravo\n---\n", "\n---\ntype: agravo\n---\n",
    "---\ntype: agravo\n", "---\ntype: agravo\n# No closing delimiter\n",
])
def test_missing_or_incomplete_opening_header(tmp_path: Path, content: str) -> None:
    document = tmp_path / "document.md"
    document.write_text(content, encoding="utf-8")
    assert read_frontmatter(document) == {}


@pytest.mark.parametrize("unsupported", [
    "tags:\n  - recurso\n  - processo",
    "nested:\n  type: sentenca",
    "tags: [recurso, processo]",
    "nested: {type: sentenca}",
    "description: |\n  type: sentenca",
    "description: >\n  type: sentenca",
    "type: 'unclosed",
])
def test_unsupported_yaml_is_ignored(tmp_path: Path, unsupported: str) -> None:
    document = tmp_path / "document.md"
    document.write_text(f"---\n{unsupported}\ncourt: Fictional\n---\n", encoding="utf-8")
    assert read_frontmatter(document) == {"court": "Fictional"}


def test_utf8_bom_and_windows_line_endings(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    document.write_bytes(b"\xef\xbb\xbf---\r\ntype: sentenca\r\n---\r\n# Body\r\n")
    assert read_frontmatter(document) == {"type": "sentenca"}


def test_body_fields_are_not_metadata(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    document.write_text("---\ntype: agravo\n---\ntype: sentenca\n", encoding="utf-8")
    assert read_frontmatter(document) == {"type": "agravo"}


def test_reading_preserves_exact_bytes(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    original = "---\r\ntype: sentença\r\n---\r\n# Título\r\n[[Link]] #tag\r\n".encode("utf-8")
    document.write_bytes(original)
    original_mtime = document.stat().st_mtime_ns
    read_frontmatter(document)
    assert document.read_bytes() == original
    assert document.stat().st_mtime_ns == original_mtime


def test_missing_file_reports_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_frontmatter(tmp_path / "missing.md")


def test_invalid_utf8_reports_error(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    document.write_bytes(b"---\ntype: \xff\n---\n")
    with pytest.raises(UnicodeDecodeError):
        read_frontmatter(document)
