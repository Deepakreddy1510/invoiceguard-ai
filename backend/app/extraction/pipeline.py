from app.config import get_settings
from app.extraction.evidence import verify
from app.extraction.fallback import fallback
from app.extraction.gemini import PROMPT_VERSION, GeminiUnavailable, extract_gemini


def structure(pages: list[dict], document_id: str) -> dict:
    settings = get_settings()
    reason = "No Gemini key configured; conservative extraction used."
    source = "FALLBACK"
    if settings.gemini_api_key:
        try:
            result = extract_gemini(
                pages, settings.gemini_api_key.get_secret_value(), settings.gemini_model
            )
            source = "GEMINI"
            reason = None
        except GeminiUnavailable as exc:
            reason = str(exc)
            result = fallback(pages)
    else:
        result = fallback(pages)
    return {
        "fields": verify(result, pages, document_id),
        "provider": source,
        "model": settings.gemini_model if source == "GEMINI" else None,
        "prompt_version": PROMPT_VERSION if source == "GEMINI" else None,
        "fallback_reason": reason,
    }
