"""Token local para proteger el servidor que escucha en loopback."""

from __future__ import annotations

import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

HEADER = "X-Penfold-Token"


def new_token() -> str:
    return secrets.token_urlsafe(32)


class TokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith("/api/") or path == "/api/health":
            return await call_next(request)
        expected = getattr(request.app.state, "token", None)
        if not expected:
            return JSONResponse(
                {"detail": "El servidor no tiene un token configurado."}, status_code=403
            )
        supplied = request.headers.get(HEADER)
        # EventSource y descargas de artefactos no pueden enviar headers:
        # esos dos endpoints (de solo lectura) admite también token por query.
        if path.endswith("/stream") or path.startswith("/api/artifacts/"):
            supplied = supplied or request.query_params.get("token")
        if not supplied or not hmac.compare_digest(str(supplied), str(expected)):
            return JSONResponse({"detail": "Token local inválido o ausente."}, status_code=401)
        return await call_next(request)
