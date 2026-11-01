
"""Request and response schemas for the public API."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.config import LANGUAGES


SUPPORTED_LANGUAGES = ", ".join(LANGUAGES)


class TranslationRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Customer-support message to translate.",
    )
    target_language: str = Field(
        ...,
        description=f"Target ISO language code: {SUPPORTED_LANGUAGES}",
    )
    source_language: Optional[str] = Field(
        default=None,
        description="Optional source ISO language code. Omit to detect automatically.",
    )
    protect_terms: bool = Field(
        default=True,
        description="Preserve URLs, order IDs and other protected terms.",
    )

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Please enter text to translate.")
        return value

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in LANGUAGES:
            raise ValueError(
                f"Unsupported target language. Choose one of: {SUPPORTED_LANGUAGES}"
            )
        return value

    @field_validator("source_language")
    @classmethod
    def validate_source_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.lower().strip()

        if value not in LANGUAGES:
            raise ValueError(
                f"Unsupported source language. Choose one of: {SUPPORTED_LANGUAGES}"
            )

        return value


class TranslationResponse(BaseModel):
    source_text: str
    translated_text: str

    source_language: str
    source_language_name: str
    target_language: str
    target_language_name: str

    detected_confidence: float
    detection_note: str

    # Google Translation API does not provide an NLLB token count.
    input_character_count: int = Field(
        description="Number of characters in the original input text."
    )

    latency_ms: float

    # Temporary backward compatibility with the previous NLLB API response.
    # These fields will be removed after the frontend migration is verified.
    source_nllb_code: Optional[str] = Field(
        default=None,
        deprecated=True,
        description="Legacy NLLB language code. Not used by Google Translation API.",
    )
    target_nllb_code: Optional[str] = Field(
        default=None,
        deprecated=True,
        description="Legacy NLLB language code. Not used by Google Translation API.",
    )
    input_token_count: Optional[int] = Field(
        default=None,
        deprecated=True,
        description="Legacy NLLB tokenizer count. Not applicable to Google Translation API.",
    )


class BatchTranslationRequest(BaseModel):
    messages: list[str] = Field(
        ...,
        min_length=1,
        max_length=32,
        description="List of customer-support messages to translate.",
    )
    target_language: str
    source_language: Optional[str] = None
    protect_terms: bool = True

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("Every message must contain non-empty text.")

        if any(len(value) > 10000 for value in values):
            raise ValueError("Each message must be 10000 characters or fewer.")

        return values

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, value: str) -> str:
        value = value.lower().strip()

        if value not in LANGUAGES:
            raise ValueError(
                f"Unsupported target language. Choose one of: {SUPPORTED_LANGUAGES}"
            )

        return value

    @field_validator("source_language")
    @classmethod
    def validate_source_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.lower().strip()

        if value not in LANGUAGES:
            raise ValueError(
                f"Unsupported source language. Choose one of: {SUPPORTED_LANGUAGES}"
            )

        return value


class BatchTranslationResponse(BaseModel):
    count: int
    results: list[TranslationResponse]


class APIErrorDetail(BaseModel):
    code: str
    message: str


class APIErrorResponse(BaseModel):
    error: APIErrorDetail
