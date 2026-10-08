"""Read only a small, explicitly supported subset of YAML front matter."""

import re
from pathlib import Path


def _read_scalar(value: str) -> str | None:
    """Accept plain or quoted strings, ignoring YAML collections and blocks."""
    value = value.strip()
    if value.startswith(("'", '"')):
        quote = value[0]
        closing = value.find(quote, 1)
        if closing < 0:
            return None
        remainder = value[closing + 1:].strip()
        if remainder and not remainder.startswith("#"):
            return None
        return value[1:closing]

    value = value.split(" #", 1)[0].strip()
    if not value or value.startswith(("#", "[", "{", "|", ">", "&", "*", "!")):
        return None
    return value


def read_frontmatter(file_path: Path) -> dict[str, str]:
    """Extract top-level key: value strings from a complete opening header.

    UTF-8 and UTF-8 with BOM are supported. Lists, nested maps and multiline
    values are ignored. Missing or unclosed headers return an empty dict.
    Filesystem and decoding errors are left to the caller; no file is edited.
    """
    metadata: dict[str, str] = {}
    with file_path.open("r", encoding="utf-8-sig") as document:
        if document.readline().strip() != "---":
            return {}
        for line in document:
            if line.rstrip() == "---":
                return metadata
            if line[:1].isspace() or ":" not in line:
                continue
            key, _, raw_value = line.partition(":")
            key = key.strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
                continue
            value = _read_scalar(raw_value)
            if value is not None:
                metadata[key] = value
    return {}
