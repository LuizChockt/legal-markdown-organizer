"""Deterministic classification using metadata, then filename keywords."""

import re
import unicodedata
from pathlib import Path

from .frontmatter import read_frontmatter
from .rules import CATEGORY_PRIORITY, KEYWORDS, TYPE_ALIASES


def normalize_text(text: str) -> str:
    """Normalize a comparison string without changing any original filename."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(unaccented.replace("_", " ").replace("-", " ").split())


def classify_type(document_type: str) -> str | None:
    """Resolve a category, exact keyword phrase or explicit metadata alias."""
    normalized = normalize_text(document_type)
    for category in CATEGORY_PRIORITY:
        aliases = (category, *KEYWORDS[category], *TYPE_ALIASES.get(category, ()))
        if any(normalized == normalize_text(alias) for alias in aliases):
            return category
    return None


def classify_filename(filename: str) -> str:
    """Match complete words and phrases in priority order, excluding the suffix."""
    words = re.findall(r"[a-z0-9]+", normalize_text(Path(filename).stem))
    searchable = f" {' '.join(words)} "
    for category in CATEGORY_PRIORITY:
        for keyword in KEYWORDS[category]:
            if f" {normalize_text(keyword)} " in searchable:
                return category
    return "Outros"


def classify_file(file_path: Path) -> str:
    """Prefer a recognized Markdown type; otherwise fall back to the filename.

    Optional .txt documents are classified only by their filenames.
    The document body is never used for classification.
    """
    if file_path.suffix.lower() == ".md":
        metadata = read_frontmatter(file_path)
        category = classify_type(metadata.get("type", ""))
        if category is not None:
            return category
    return classify_filename(file_path.name)
