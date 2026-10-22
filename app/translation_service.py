"""Application service that orchestrates the notebook's translation pipeline."""
import logging
import time
from dataclasses import dataclass
from typing import Optional

import torch

from app.config import LANGUAGES, get_settings
from app.language_detection import DetectionResult, detect_language
from app.model_loader import TranslationModel
from app.term_protection import postprocess, protect_terms, restore_terms

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    source_text: str
    translated_text: str
    src_iso: str
    tgt_iso: str
    src_nllb: str
    tgt_nllb: str
    detection: DetectionResult
    num_input_tokens: int
    latency_ms: float


class TranslationService:
    def __init__(self, model_bundle: TranslationModel) -> None:
        self.bundle = model_bundle
        self.settings = get_settings()

    @staticmethod
    def _validate_text(text: str) -> str:
        if not isinstance(text, str):
            raise ValueError(f"Input must be a string, got {type(text).__name__}.")
        if not text.strip():
            raise ValueError("Input text is empty.")
        if len(text) > 10000:
            raise ValueError("Input text must be 10000 characters or fewer.")
        return text.strip()

    @staticmethod
    def _nllb_code(iso: str) -> str:
        if iso not in LANGUAGES:
            raise ValueError(f"Unsupported language '{iso}'. Supported: {sorted(LANGUAGES)}")
        return LANGUAGES[iso]["nllb"]

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
            raise ValueError(f"Unsupported target '{target_language}'. Supported: {sorted(LANGUAGES)}")
        if source_language is None:
            detection = detect_language(text)
            source_language = detection.iso
        else:
            if source_language not in LANGUAGES:
                raise ValueError(f"Unsupported source '{source_language}'. Supported: {sorted(LANGUAGES)}")
            detection = DetectionResult(
                iso=source_language, confidence=1.0, supported=True,
                note="Source language provided by caller.",
            )

        source_code = self._nllb_code(source_language)
        target_code = self._nllb_code(target_language)

        if not self.bundle.is_loaded:
            raise RuntimeError("Translation model is not loaded.")

        masked_text, replacements = protect_terms(text) if protect else (text, {})

        # tokenizer.src_lang is mutable. Lock the complete inference sequence so
        # concurrent requests cannot overwrite one another's source-language state.
        with self.bundle.lock:
            self.bundle.tokenizer.src_lang = source_code
            encoded = self.bundle.tokenizer(
                masked_text,
                return_tensors="pt",
                truncation=True,
                max_length=self.settings.max_input_tokens,
            ).to(self.bundle.device)
            target_token_id = self.bundle.tokenizer.convert_tokens_to_ids(target_code)
            if target_token_id is None or target_token_id == self.bundle.tokenizer.unk_token_id:
                raise RuntimeError(f"Could not resolve NLLB target token: {target_code}")

            with torch.inference_mode():
                generated = self.bundle.model.generate(
                    **encoded,
                    forced_bos_token_id=target_token_id,
                    num_beams=self.settings.num_beams,
                    max_new_tokens=self.settings.max_new_tokens,
                    no_repeat_ngram_size=self.settings.no_repeat_ngram_size,
                    length_penalty=self.settings.length_penalty,
                    early_stopping=self.settings.early_stopping,
                )
            decoded = self.bundle.tokenizer.batch_decode(
                generated, skip_special_tokens=True
            )[0]

        if protect:
            decoded = restore_terms(decoded, replacements)
        output = postprocess(decoded)

        return TranslationResult(
            source_text=text,
            translated_text=output,
            src_iso=source_language,
            tgt_iso=target_language,
            src_nllb=source_code,
            tgt_nllb=target_code,
            detection=detection,
            num_input_tokens=int(encoded["input_ids"].shape[1]),
            latency_ms=(time.perf_counter() - start_time) * 1000.0,
        )

    def translate_batch(
        self,
        messages: list[str],
        target_language: str,
        source_language: Optional[str] = None,
        protect: bool = True,
    ) -> list[TranslationResult]:
        """Translate a batch, grouping messages by source language and preserving order."""
        if not messages:
            return []
        if target_language not in LANGUAGES:
            raise ValueError(f"Unsupported target '{target_language}'. Supported: {sorted(LANGUAGES)}")

        clean_messages = [self._validate_text(message) for message in messages]
        resolved: list[tuple[int, str, DetectionResult]] = []
        groups: dict[str, list[int]] = {}
        for index, message in enumerate(clean_messages):
            if source_language is not None:
                if source_language not in LANGUAGES:
                    raise ValueError(f"Unsupported source '{source_language}'. Supported: {sorted(LANGUAGES)}")
                detection = DetectionResult(
                    iso=source_language, confidence=1.0, supported=True,
                    note="Source language provided by caller.",
                )
                source_iso = source_language
            else:
                detection = detect_language(message)
                source_iso = detection.iso
            resolved.append((index, source_iso, detection))
            groups.setdefault(source_iso, []).append(index)

        if not self.bundle.is_loaded:
            raise RuntimeError("Translation model is not loaded.")

        results: list[Optional[TranslationResult]] = [None] * len(clean_messages)
        for source_iso, indices in groups.items():
            source_code = self._nllb_code(source_iso)
            target_code = self._nllb_code(target_language)
            chunk_texts = [clean_messages[index] for index in indices]
            protected: list[str] = []
            replacement_maps: list[dict[str, str]] = []
            for message in chunk_texts:
                masked, mapping = protect_terms(message) if protect else (message, {})
                protected.append(masked)
                replacement_maps.append(mapping)

            start_time = time.perf_counter()
            with self.bundle.lock:
                self.bundle.tokenizer.src_lang = source_code
                encoded = self.bundle.tokenizer(
                    protected,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=self.settings.max_input_tokens,
                ).to(self.bundle.device)
                target_token_id = self.bundle.tokenizer.convert_tokens_to_ids(target_code)
                if target_token_id is None or target_token_id == self.bundle.tokenizer.unk_token_id:
                    raise RuntimeError(f"Could not resolve NLLB target token: {target_code}")
                with torch.inference_mode():
                    generated = self.bundle.model.generate(
                        **encoded,
                        forced_bos_token_id=target_token_id,
                        num_beams=self.settings.num_beams,
                        max_new_tokens=self.settings.max_new_tokens,
                        no_repeat_ngram_size=self.settings.no_repeat_ngram_size,
                        length_penalty=self.settings.length_penalty,
                        early_stopping=self.settings.early_stopping,
                    )
                decoded_texts = self.bundle.tokenizer.batch_decode(generated, skip_special_tokens=True)

            per_message_latency = (time.perf_counter() - start_time) * 1000.0 / len(indices)
            padded_token_count = int(encoded["input_ids"].shape[1])
            for local_index, original_index in enumerate(indices):
                decoded = decoded_texts[local_index]
                if protect:
                    decoded = restore_terms(decoded, replacement_maps[local_index])
                detection = resolved[original_index][2]
                results[original_index] = TranslationResult(
                    source_text=clean_messages[original_index],
                    translated_text=postprocess(decoded),
                    src_iso=source_iso,
                    tgt_iso=target_language,
                    src_nllb=source_code,
                    tgt_nllb=target_code,
                    detection=detection,
                    num_input_tokens=padded_token_count,
                    latency_ms=per_message_latency,
                )

        return [result for result in results if result is not None]

