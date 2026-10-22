"""Lazy loading for the pretrained NLLB tokenizer and translation model."""
import logging
import threading

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from app.config import get_settings

logger = logging.getLogger(__name__)


class TranslationModel:
    """Owns model resources and serializes access to mutable tokenizer state."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = None
        self.model = None
        self.lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self.model is not None and self.tokenizer is not None

    def load(self) -> None:
        if self.is_loaded:
            return
        logger.info("Loading tokenizer: %s", self.settings.model_name)
        tokenizer = AutoTokenizer.from_pretrained(self.settings.model_name)
        dtype = torch.float16 if self.device.type == "cuda" else torch.float32
        logger.info("Loading model on %s using %s", self.device, dtype)
        model = AutoModelForSeq2SeqLM.from_pretrained(
            self.settings.model_name,
            dtype=dtype,
        )
        model.to(self.device)
        model.eval()
        self.tokenizer = tokenizer
        self.model = model
        logger.info("Translation model loaded.")

    def unload(self) -> None:
        self.model = None
        self.tokenizer = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
