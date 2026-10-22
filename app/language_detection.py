"""Best-effort source-language detection."""
from dataclasses import dataclass, field

from langdetect import DetectorFactory, detect_langs, LangDetectException

from app.config import LANGUAGES, get_settings

DetectorFactory.seed = 42


@dataclass
class DetectionResult:
    iso: str
    confidence: float
    supported: bool
    candidates: list[tuple[str, float]] = field(default_factory=list)
    note: str = ""


def detect_language(text: str) -> DetectionResult:
    default_iso = get_settings().default_source_language
    if not text or not text.strip():
        return DetectionResult(default_iso, 0.0, True, note="Empty input; defaulted to configured source language.")
    try:
        ranked = detect_langs(text)
    except LangDetectException:
        return DetectionResult(default_iso, 0.0, True, note="Detector could not decide; used configured fallback.")

    candidates = [(candidate.lang, float(candidate.prob)) for candidate in ranked]
    top_iso, top_probability = candidates[0]

    if top_iso not in LANGUAGES:
        return DetectionResult(
            default_iso, top_probability, False, candidates,
            f"Detected '{top_iso}' is unsupported; defaulted to '{default_iso}'.",
        )

    note = ""
    if len(candidates) > 1 and candidates[1][1] > 0.30:
        note = f"Possible code-switching: also detected '{candidates[1][0]}' (p={candidates[1][1]:.2f})."

    return DetectionResult(top_iso, top_probability, True, candidates, note)
