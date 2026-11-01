
"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import LANGUAGES, get_settings
from app.model_loader import TranslationModel
from app.schemas import (
    APIErrorResponse,
    BatchTranslationRequest,
    BatchTranslationResponse,
    TranslationRequest,
    TranslationResponse,
)
from app.translation_service import TranslationService


# --------------------------------------------------
# Application configuration
# --------------------------------------------------

settings = get_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

model_bundle = TranslationModel()
translation_service = TranslationService(model_bundle)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------
# Application lifecycle
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.app_name)

    try:
        model_bundle.load()
        logger.info("Google Cloud Translation client initialized.")
        yield

    finally:
        model_bundle.unload()
        logger.info("Application shutdown complete.")


# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Translate customer-support messages between "
        "English, French, Spanish, Hindi and Tamil."
    ),
    lifespan=lifespan,
)


app.mount(
    "/static",
    StaticFiles(directory=PROJECT_ROOT / "static"),
    name="static",
)


# --------------------------------------------------
# Standard API error response
# --------------------------------------------------

def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list | None = None,
):
    error = {
        "code": code,
        "message": message,
    }

    if details:
        error["details"] = details

    return JSONResponse(
        status_code=status_code,
        content={"error": error},
    )


# --------------------------------------------------
# Centralised exception handlers
# --------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    # Do not expose submitted input values in validation details.
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]

    return error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Please check the submitted information and try again.",
        details=details,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    status_messages = {
        400: ("BAD_REQUEST", "The request could not be processed."),
        404: ("NOT_FOUND", "The requested resource was not found."),
        405: ("METHOD_NOT_ALLOWED", "This request method is not supported."),
    }

    code, message = status_messages.get(
        exc.status_code,
        ("HTTP_ERROR", "The request could not be completed."),
    )

    return error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
    )


@app.exception_handler(ValueError)
async def value_error_handler(
    request: Request,
    exc: ValueError,
):
    return error_response(
        status_code=422,
        code="INVALID_TRANSLATION_REQUEST",
        message=str(exc),
    )


@app.exception_handler(RuntimeError)
async def runtime_error_handler(
    request: Request,
    exc: RuntimeError,
):
    logger.exception("Translation service runtime error")

    return error_response(
        status_code=503,
        code="TRANSLATION_SERVICE_UNAVAILABLE",
        message=(
            "Translation service is temporarily unavailable. "
            "Please try again later."
        ),
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.exception(
        "Unexpected backend error. Method=%s Path=%s",
        request.method,
        request.url.path,
    )

    return error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="Something went wrong. Please try again later.",
    )


# --------------------------------------------------
# Response conversion
# --------------------------------------------------

def to_response(result) -> TranslationResponse:
    return TranslationResponse(
        source_text=result.source_text,
        translated_text=result.translated_text,

        source_language=result.src_iso,
        source_language_name=LANGUAGES[result.src_iso]["name"],

        target_language=result.tgt_iso,
        target_language_name=LANGUAGES[result.tgt_iso]["name"],

        detected_confidence=result.detection.confidence,
        detection_note=result.detection.note,

        input_character_count=result.num_input_characters,
        latency_ms=round(result.latency_ms, 2),

        # Temporary backward compatibility.
        source_nllb_code=result.src_nllb,
        target_nllb_code=result.tgt_nllb,
        input_token_count=result.num_input_tokens,
    )


# --------------------------------------------------
# Frontend routes
# --------------------------------------------------

@app.get("/")
def root():
    return FileResponse(PROJECT_ROOT / "templates" / "index.html")


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/health")
def health():
    configured = model_bundle.is_loaded

    return {
        "status": "ok" if configured else "unavailable",
        "translation_provider": "Google Cloud Translation API",
        "translation_service_configured": configured,
    }


# --------------------------------------------------
# Single translation endpoint
# --------------------------------------------------

@app.post(
    "/api/translate",
    response_model=TranslationResponse,
)
def translate_message(request: TranslationRequest):

    result = translation_service.translate(
        text=request.text,
        target_language=request.target_language,
        source_language=request.source_language,
        protect=request.protect_terms,
    )

    return to_response(result)


# --------------------------------------------------
# Batch translation endpoint
# --------------------------------------------------

@app.post(
    "/api/translate/batch",
    response_model=BatchTranslationResponse,
)
def translate_batch(request: BatchTranslationRequest):

    results = translation_service.translate_batch(
        messages=request.messages,
        target_language=request.target_language,
        source_language=request.source_language,
        protect=request.protect_terms,
    )

    translated_results = [
        to_response(result)
        for result in results
    ]

    return BatchTranslationResponse(
        count=len(translated_results),
        results=translated_results,
    )
