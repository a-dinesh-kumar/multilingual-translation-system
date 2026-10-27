"""FastAPI application entry point."""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException

from app.config import LANGUAGES, get_settings
from app.model_loader import TranslationModel
from app.schemas import (
    BatchTranslationRequest,
    BatchTranslationResponse,
    TranslationRequest,
    TranslationResponse,
)
from app.translation_service import TranslationService

from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
model_bundle = TranslationModel()
translation_service = TranslationService(model_bundle)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.app_name)
    try:
        model_bundle.load()
        yield
    finally:
        model_bundle.unload()
        logger.info("Application shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Translate customer-support messages between English, French, Spanish, Hindi and Tamil.",
    lifespan=lifespan,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
app.mount(
    "/static",
    StaticFiles(directory=PROJECT_ROOT / "static"),
    name="static",
)

def to_response(result) -> TranslationResponse:
    return TranslationResponse(
        source_text=result.source_text,
        translated_text=result.translated_text,
        source_language=result.src_iso,
        source_language_name=LANGUAGES[result.src_iso]["name"],
        target_language=result.tgt_iso,
        target_language_name=LANGUAGES[result.tgt_iso]["name"],
        source_nllb_code=result.src_nllb,
        target_nllb_code=result.tgt_nllb,
        detected_confidence=result.detection.confidence,
        detection_note=result.detection.note,
        input_token_count=result.num_input_tokens,
        latency_ms=round(result.latency_ms, 2),
    )


@app.get("/")
def root():
    return FileResponse(PROJECT_ROOT / "templates" / "index.html")


@app.get("/health")
def health():
    return {
        "status": "ok" if model_bundle.is_loaded else "loading_or_unavailable",
        "model_loaded": model_bundle.is_loaded,
        "model_name": settings.model_name,
        "device": str(model_bundle.device),
    }


@app.post("/api/translate", response_model=TranslationResponse)
def translate_message(request: TranslationRequest):
    try:
        result = translation_service.translate(
            text=request.text,
            target_language=request.target_language,
            source_language=request.source_language,
            protect=request.protect_terms,
        )
        return to_response(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Translation runtime error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected translation failure")
        raise HTTPException(status_code=500, detail="Translation failed unexpectedly.") from exc


@app.post("/api/translate/batch", response_model=BatchTranslationResponse)
def translate_batch(request: BatchTranslationRequest):
    try:
        results = [
            to_response(result)
            for result in translation_service.translate_batch(
                messages=request.messages,
                target_language=request.target_language,
                source_language=request.source_language,
                protect=request.protect_terms,
            )
        ]
        return BatchTranslationResponse(count=len(results), results=results)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Batch translation runtime error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected batch translation failure")
        raise HTTPException(status_code=500, detail="Batch translation failed unexpectedly.") from exc
