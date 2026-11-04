from app.config import get_settings
from app.extraction.evidence import verify
from app.extraction.fallback import fallback
from app.extraction.gemini import PROMPT_VERSION, GeminiUnavailable, extract_gemini


class ExtractionModeFailure(GeminiUnavailable):
    def __init__(self, model):
        super().__init__(
            "Required Gemini extraction failed or produced unsupported evidence. No fallback was used."
        )
        self.metadata = {
            "fields": {},
            "provider": "NONE",
            "model": None,
            "requested_mode": "GEMINI",
            "attempted_provider": "GEMINI",
            "attempted_model": model,
            "fallback_reason": None,
            "safe_error": str(self),
        }


def structure(pages: list[dict], document_id: str, mode="AUTO") -> dict:
    if mode not in ["AUTO", "GEMINI", "FALLBACK"]:
        raise ValueError("Unsupported extraction mode.")
    settings = get_settings()
    reason = (
        "Rule-based extraction explicitly requested."
        if mode == "FALLBACK"
        else "No Gemini key configured; conservative extraction used."
    )
    source = "FALLBACK"
    if mode != "FALLBACK" and settings.gemini_api_key:
        try:
            result = extract_gemini(
                pages, settings.gemini_api_key.get_secret_value(), settings.gemini_model
            )
            source = "GEMINI"
            reason = None
        except GeminiUnavailable:
            if mode == "GEMINI":
                raise ExtractionModeFailure(settings.gemini_model) from None
            reason = "Gemini request failed, timed out, or returned invalid structured data. Conservative fallback used."
            result = fallback(pages)
    elif mode == "GEMINI":
        raise ExtractionModeFailure(settings.gemini_model)
    else:
        result = fallback(pages)
    fields = verify(result, pages, document_id)
    if mode == "GEMINI":
        values = [v for v in fields.values() if isinstance(v, dict)] + [
            v for item in fields.get("items", []) for v in item.values()
        ]
        if fields.get("issues") or any(
            v.get("value") is not None and not v.get("verified") for v in values
        ):
            raise ExtractionModeFailure(settings.gemini_model)
    return {
        "fields": fields,
        "provider": source,
        "model": settings.gemini_model if source == "GEMINI" else None,
        "prompt_version": PROMPT_VERSION if source == "GEMINI" else None,
        "fallback_reason": reason,
        "requested_mode": mode,
    }
