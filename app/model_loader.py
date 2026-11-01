
import logging
from typing import Union

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)


class GoogleTranslationError(Exception):
    """Raised when Google Cloud Translation API returns an error."""


class GoogleTranslationClient:
    """
    Client for Google Cloud Translation API v2.

    Translation is performed by Google's cloud service.
    No local ML model is downloaded or loaded into memory.
    """

    def __init__(self):
        self.settings = get_settings()

        self.api_key = self.settings.google_translate_api_key
        self.api_url = self.settings.google_translate_api_url

        self.timeout = 30

    def validate_configuration(self):
        """Validate that the required Google API configuration exists."""

        if not self.api_key:
            raise GoogleTranslationError(
                "Google Cloud Translation API key is not configured."
            )

    def translate(
        self,
        texts: Union[str, list[str]],
        source_language: str,
        target_language: str,
    ) -> list[str]:
        """
        Translate one or multiple texts using Google Cloud Translation API.

        Google accepts a single string or a list of strings in the 'q' field.
        The returned translations preserve the input order.
        """

        self.validate_configuration()

        if isinstance(texts, str):
            texts = [texts]

        if not texts:
            return []

        payload = {
            "q": texts,
            "source": source_language,
            "target": target_language,
            "format": "text",
        }

        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

            response.raise_for_status()

            response_data = response.json()

            translations = response_data["data"]["translations"]

            return [
                item["translatedText"]
                for item in translations
            ]

        except requests.exceptions.Timeout as exc:
            logger.error("Google Translation API request timed out.")

            raise GoogleTranslationError(
                "Google Translation API request timed out."
            ) from exc

        except requests.exceptions.HTTPError as exc:

            status_code = exc.response.status_code if exc.response else None

            # Extract Google's error message for internal debugging.
            try:
                error_data = exc.response.json()
                google_error = error_data.get("error", {}).get(
                    "message", "Unknown Google API error."
                )
            except (ValueError, AttributeError):
                google_error = "Unable to read Google API error details."

            logger.error(
                "Google Translation API HTTP error. "
                "Status: %s | Details: %s",
                status_code,
                google_error,
            )

            raise GoogleTranslationError(
                f"Google Translation API request failed (HTTP {status_code})."
            ) from exc

        except requests.exceptions.RequestException as exc:

            logger.exception("Google Translation API connection failed.")

            raise GoogleTranslationError(
                "Unable to connect to the translation service. Please try again."
            ) from exc

        except (KeyError, TypeError, ValueError) as exc:
            logger.exception("Unexpected Google Translation API response.")

            raise GoogleTranslationError(
                "Received an invalid response from Google Translation API."
            ) from exc


# Temporary compatibility layer.
# Existing main.py expects TranslationModel during this migration stage.
class TranslationModel(GoogleTranslationClient):

    @property
    def is_loaded(self) -> bool:
        """For compatibility, report whether API configuration is available."""
        return bool(self.api_key)

    def load(self):
        """
        Validate API configuration instead of loading a local ML model.
        """
        self.validate_configuration()
        logger.info("Google Cloud Translation client initialized.")

    def unload(self):
        """
        No local model needs to be unloaded.
        """
        logger.info("Google Cloud Translation client shutdown.")
