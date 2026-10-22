"""Mask and restore technical identifiers before and after translation."""
import re

_PROTECT_PATTERNS = [
    re.compile(r"https?://\S+"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    re.compile(r"\b(?:ERR|ERROR|CODE|E|SKU|ID)[-_ ]?\d{2,}\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{2,}[-_]?\d+[A-Z0-9-]*\b"),
    re.compile(r"#\w+|@\w+"),
]
_SENTINEL_PREFIX = "NLLBKEEP"


def protect_terms(text: str) -> tuple[str, dict[str, str]]:
    spans: list[tuple[int, int, str]] = []
    for pattern in _PROTECT_PATTERNS:
        for match in pattern.finditer(text):
            if match.group(0).strip():
                spans.append((match.start(), match.end(), match.group(0)))

    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept: list[tuple[int, int, str]] = []
    for start, end, value in spans:
        if any(not (end <= kept_start or start >= kept_end)
               for kept_start, kept_end, _ in kept):
            continue
        kept.append((start, end, value))

    ordered = sorted(kept, key=lambda item: item[0])
    index_by_span = {(start, end): index for index, (start, end, _) in enumerate(ordered)}
    mapping: dict[str, str] = {}

    for start, end, value in sorted(kept, key=lambda item: item[0], reverse=True):
        placeholder = f"{_SENTINEL_PREFIX}{index_by_span[(start, end)]}"
        text = text[:start] + placeholder + text[end:]
        mapping[placeholder] = value
    return text, mapping


def restore_terms(text: str, mapping: dict[str, str]) -> str:
    for placeholder, original in sorted(mapping.items(), key=lambda item: -len(item[0])):
        digits = placeholder[len(_SENTINEL_PREFIX):]
        pattern = re.compile(re.escape(_SENTINEL_PREFIX) + r"\s*" + digits + r"(?!\d)", re.IGNORECASE)
        text = pattern.sub(lambda _match, value=original: value, text)
    return text


def postprocess(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
