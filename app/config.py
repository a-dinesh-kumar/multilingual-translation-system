"""Central application configuration."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Multilingual Customer-Support Translation System"
    app_version: str = "1.0.0"
    model_name: str = "facebook/nllb-200-distilled-600M"
    max_input_tokens: int = 512
    max_new_tokens: int = 512
    num_beams: int = 5
    no_repeat_ngram_size: int = 3
    length_penalty: float = 1.0
    early_stopping: bool = True
    default_source_language: str = "en"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


LANGUAGES = {
    "en": {"name": "English", "nllb": "eng_Latn"},
    "fr": {"name": "French", "nllb": "fra_Latn"},
    "es": {"name": "Spanish", "nllb": "spa_Latn"},
    "hi": {"name": "Hindi", "nllb": "hin_Deva"},
    "ta": {"name": "Tamil", "nllb": "tam_Taml"},
}


@lru_cache
def get_settings() -> Settings:
    return Settings()
