
"""Application service for Google Cloud Translation."""

import html
import logging
import time
from dataclasses import dataclass
from typing import Optional

from app.config import LANGUAGES, get_settings
from app.language_detection import DetectionResult, detect_language
from app.model_loader import (
    GoogleTranslationError,
    TranslationModel,
)
from app.term_protection import postprocess, protect_terms, restore_terms

logger = logging.getLogger(__name__)

# Keep each Google API request comfortably below its content-size limit.
MAX_BATCH_CHARACTERS = 25000


@dataclass
class TranslationResult:
    source_text: str
    translated_text: str
    src_iso: str
    tgt_iso: str
    src_nllb: str
    tgt_nllb: str
    detection: DetectionResult

    # Legacy field retained temporarily for response compatibility.
    # Google Cloud Translation does not expose tokenizer token counts.
    num_input_tokens: int = 0

    # Google translation uses character count instead of model token count.
    num_input_characters: int = 0

    latency_ms: float = 0.0


class TranslationService:

    def __init__(self, model_bundle: TranslationModel) -> None:
        self.bundle = model_bundle
        self.settings = get_settings()

    @staticmethod
    def _validate_text(text: str) -> str:
        if not isinstance(text, str):
            raise ValueError(
                f"Input must be a string, got {type(text).__name__}."
            )

        if not text.strip():
            raise ValueError("Input text is empty.")

        if len(text) > 10000:
            raise ValueError(
                "Input text must be 10000 characters or fewer."
            )

        return text.strip()

    @staticmethod
    def _google_code(iso: str) -> str:
        """Return Google's language code for a supported ISO language."""

        if iso not in LANGUAGES:
            raise ValueError(
                f"Unsupported language '{iso}'. "
                f"Supported: {sorted(LANGUAGES)}"
            )

        return LANGUAGES[iso]["google"]

    @staticmethod
    def _nllb_code(iso: str) -> str:
        """
        Retain legacy NLLB metadata during the API migration.

        These codes are not sent to Google.
        """

        if iso not in LANGUAGES:
            raise ValueError(
                f"Unsupported language '{iso}'. "
                f"Supported: {sorted(LANGUAGES)}"
            )

        return LANGUAGES[iso]["nllb"]

    def _call_translation_api(
        self,
        texts: list[str],
        source_language: str,
        target_language: str,
    ) -> list[str]:
        """Call Google and convert provider errors into service errors."""

        try:
            translations = self.bundle.translate(
                texts=texts,
                source_language=source_language,
                target_language=target_language,
            )

            # Google may HTML-escape characters in translated text.
            return [html.unescape(text) for text in translations]

        except GoogleTranslationError as exc:
            logger.exception("Google Translation API operation failed.")
            raise RuntimeError(str(exc)) from exc

    def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
        protect: bool = True,
    ) -> TranslationResult:

        start_time = time.perf_counter()

        text = self._validate_text(text)

        if target_language not in LANGUAGES:
            raise ValueError(
                f"Unsupported target '{target_language}'. "
                f"Supported: {sorted(LANGUAGES)}"
            )

        # Preserve the existing automatic language detection behaviour.
        if source_language is None:
            detection = detect_language(text)
            source_language = detection.iso

        else:
            if source_language not in LANGUAGES:
                raise ValueError(
                    f"Unsupported source '{source_language}'. "
                    f"Supported: {sorted(LANGUAGES)}"
                )

            detection = DetectionResult(
                iso=source_language,
                confidence=1.0,
                supported=True,
                note="Source language provided by caller.",
            )

        # Google uses standard ISO language codes.
        source_code = self._google_code(source_language)
        target_code = self._google_code(target_language)

        # Keep the existing NLLB response metadata temporarily.
        source_nllb_code = self._nllb_code(source_language)
        target_nllb_code = self._nllb_code(target_language)

        if not self.bundle.is_loaded:
            raise RuntimeError(
                "Google Translation API client is not configured."
            )

        # No API call is required when source and target languages are identical.
        if source_language == target_language:
            return TranslationResult(
                source_text=text,
                translated_text=text,
                src_iso=source_language,
                tgt_iso=target_language,
                src_nllb=source_nllb_code,
                tgt_nllb=target_nllb_code,
                detection=detection,
                num_input_tokens=0,
                num_input_characters=len(text),
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

        # Protect technical terms before sending text to Google.
        masked_text, replacements = (
            protect_terms(text) if protect else (text, {})
        )

        translated_texts = self._call_translation_api(
            texts=[masked_text],
            source_language=source_code,
            target_language=target_code,
        )

        if len(translated_texts) != 1:
            raise RuntimeError(
                "Google Translation API returned an unexpected "
                "number of translations."
            )

        translated_text = translated_texts[0]

        # Restore URLs, IDs, email addresses and other protected terms.
        if protect:
            translated_text = restore_terms(
                translated_text,
                replacements,
            )

        output = postprocess(translated_text)

        return TranslationResult(
            source_text=text,
            translated_text=output,
            src_iso=source_language,
            tgt_iso=target_language,
            src_nllb=source_nllb_code,
            tgt_nllb=target_nllb_code,
            detection=detection,
            num_input_tokens=0,
            num_input_characters=len(text),
            latency_ms=(
                time.perf_counter() - start_time
            ) * 1000.0,
        )

    def translate_batch(
        self,
        messages: list[str],
        target_language: str,
        source_language: Optional[str] = None,
        protect: bool = True,
    ) -> list[TranslationResult]:
        """
        Translate a batch, grouping by source language and preserving
        the original message order.
        """

        if not messages:
            return []

        if target_language not in LANGUAGES:
            raise ValueError(
                f"Unsupported target '{target_language}'. "
                f"Supported: {sorted(LANGUAGES)}"
            )

        if source_language is not None and source_language not in LANGUAGES:
            raise ValueError(
                f"Unsupported source '{source_language}'. "
                f"Supported: {sorted(LANGUAGES)}"
            )

        clean_messages = [
            self._validate_text(message)
            for message in messages
        ]

        if not self.bundle.is_loaded:
            raise RuntimeError(
                "Google Translation API client is not configured."
            )

        # Resolve source language for every message.
        resolved: list[tuple[str, DetectionResult]] = []
        groups: dict[str, list[int]] = {}

        for index, message in enumerate(clean_messages):

            if source_language is not None:
                detection = DetectionResult(
                    iso=source_language,
                    confidence=1.0,
                    supported=True,
                    note="Source language provided by caller.",
                )
                source_iso = source_language

            else:
                detection = detect_language(message)
                source_iso = detection.iso

            resolved.append((source_iso, detection))
            groups.setdefault(source_iso, []).append(index)

        # Results are stored at their original positions so grouping
        # by source language never changes the response order.
        results: list[Optional[TranslationResult]] = [
            None
        ] * len(clean_messages)

        target_code = self._google_code(target_language)
        target_nllb_code = self._nllb_code(target_language)

        for source_iso, indices in groups.items():

            source_code = self._google_code(source_iso)
            source_nllb_code = self._nllb_code(source_iso)

            # Skip translation when messages are already in the target language.
            # This avoids unnecessary Google API calls and potential HTTP 400 errors.
            if source_iso == target_language:

                for index in indices:
                    detection = resolved[index][1]

                    results[index] = TranslationResult(
                        source_text=clean_messages[index],
                        translated_text=clean_messages[index],
                        src_iso=source_iso,
                        tgt_iso=target_language,
                        src_nllb=source_nllb_code,
                        tgt_nllb=target_nllb_code,
                        detection=detection,
                        num_input_tokens=0,
                        num_input_characters=len(clean_messages[index]),
                        latency_ms=0.0,
                    )

                # No API request is required for this language group.
                continue

            # Prepare the messages and their protected-term mappings.
            protected_texts: list[str] = []
            replacement_maps: list[dict[str, str]] = []

            for index in indices:
                message = clean_messages[index]

                masked, mapping = (
                    protect_terms(message) if protect else (message, {})
                )

                protected_texts.append(masked)
                replacement_maps.append(mapping)

            # Google accepts multiple q values in one API request.
            # Split large groups into smaller requests to avoid
            # oversized payloads.
            chunks: list[list[int]] = []
            current_chunk: list[int] = []
            current_characters = 0

            for local_index, masked_text in enumerate(protected_texts):

                text_length = len(masked_text)

                if (
                    current_chunk
                    and current_characters + text_length
                    > MAX_BATCH_CHARACTERS
                ):
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_characters = 0

                current_chunk.append(local_index)
                current_characters += text_length

            if current_chunk:
                chunks.append(current_chunk)

            group_start_time = time.perf_counter()

            for chunk in chunks:

                chunk_texts = [
                    protected_texts[local_index]
                    for local_index in chunk
                ]

                translated_texts = self._call_translation_api(
                    texts=chunk_texts,
                    source_language=source_code,
                    target_language=target_code,
                )

                if len(translated_texts) != len(chunk):
                    raise RuntimeError(
                        "Google Translation API returned an "
                        "unexpected number of batch translations."
                    )

                for local_index, translated_text in zip(
                    chunk,
                    translated_texts,
                ):

                    original_index = indices[local_index]

                    if protect:
                        translated_text = restore_terms(
                            translated_text,
                            replacement_maps[local_index],
                        )

                    detection = resolved[original_index][1]

                    results[original_index] = TranslationResult(
                        source_text=clean_messages[original_index],
                        translated_text=postprocess(translated_text),
                        src_iso=source_iso,
                        tgt_iso=target_language,
                        src_nllb=source_nllb_code,
                        tgt_nllb=target_nllb_code,
                        detection=detection,
                        num_input_tokens=0,
                        num_input_characters=len(
                            clean_messages[original_index]
                        ),
                        latency_ms=0.0,
                    )

            # Report average provider time per message in this group.
            group_latency = (
                time.perf_counter() - group_start_time
            ) * 1000.0 / len(indices)

            for index in indices:
                if results[index] is not None:
                    results[index].latency_ms = group_latency

        return [
            result
            for result in results
            if result is not None
        ]
