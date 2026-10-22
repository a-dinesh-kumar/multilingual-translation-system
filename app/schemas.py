"""Request and response schemas for the public API."""
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from app.config import LANGUAGES


class TranslationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000, description="UTF-8 support message")
    target_language: str = Field(..., description="Target ISO language code: en, fr, es, hi, or ta")
    source_language: Optional[str] = Field(
        default=None,
        description="Optional source ISO language code. Omit to detect automatically.",
    )
    protect_terms: bool = True

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in LANGUAGES:
            raise ValueError(f"Unsupported target_language. Choose one of: {', '.join(LANGUAGES)}")
        return value

    @field_validator("source_language")
    @classmethod
    def validate_source_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.lower().strip()
        if value not in LANGUAGES:
            raise ValueError(f"Unsupported source_language. Choose one of: {', '.join(LANGUAGES)}")
        return value


class TranslationResponse(BaseModel):
    source_text: str
    translated_text: str
    source_language: str
    source_language_name: str
    target_language: str
    target_language_name: str
    source_nllb_code: str
    target_nllb_code: str
    detected_confidence: float
    detection_note: str
    input_token_count: int
    latency_ms: float


class BatchTranslationRequest(BaseModel):
    messages: list[str] = Field(..., min_length=1, max_length=32)
    target_language: str
    source_language: Optional[str] = None
    protect_terms: bool = True

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("Every message must be a non-empty string")
        if any(len(value) > 10000 for value in values):
            raise ValueError("Each message must be 10000 characters or fewer")
        return values

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in LANGUAGES:
            raise ValueError(f"Unsupported target_language. Choose one of: {', '.join(LANGUAGES)}")
        return value

    @field_validator("source_language")
    @classmethod
    def validate_source_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.lower().strip()
        if value not in LANGUAGES:
            raise ValueError(f"Unsupported source_language. Choose one of: {', '.join(LANGUAGES)}")
        return value


class BatchTranslationResponse(BaseModel):
    count: int
    results: list[TranslationResponse]
