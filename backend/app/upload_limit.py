from fastapi import HTTPException
from starlette.responses import JSONResponse

from app.config import get_settings


class UploadLimit:
    """Bound the body while multipart parsing, not just after spooling a file."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or not scope["path"].startswith("/api/")
            or scope.get("method") not in ["POST", "PUT", "PATCH"]
        ):
            return await self.app(scope, receive, send)
        limit = (
            get_settings().max_upload_bytes + 65536
            if scope["path"].rstrip("/") == "/api/v1/documents"
            else 1024 * 1024
        )
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = 0
        if length > limit:
            return await JSONResponse({"detail": "Upload request exceeds limit."}, status_code=413)(
                scope, receive, send
            )
        count = 0

        async def bounded_receive():
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > limit:
                raise HTTPException(413, "Upload request exceeds limit.")
            return message

        await self.app(scope, bounded_receive, send)
