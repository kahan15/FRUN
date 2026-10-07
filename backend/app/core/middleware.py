import asyncio
import time
from uuid import uuid4

import structlog
from starlette.responses import JSONResponse


class RequestMiddleware:
    def __init__(self, app, max_bytes: int, body_timeout_seconds: float = 60):
        self.app, self.max_bytes = app, max_bytes
        self.body_timeout_seconds = body_timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.monotonic()
        response_started = False

        async def with_headers(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                # Credentials, precise location and friend-only map responses must not be cached
                # by browsers or shared intermediaries. The app's protected offline cache is separate.
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower()
                    not in {b"cache-control", b"x-request-id", b"x-content-type-options"}
                ]
                message["headers"] = headers + [
                    (b"x-request-id", request_id.encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ]
                structlog.get_logger().info(
                    "http_request",
                    method=scope["method"],
                    path=getattr(scope.get("route"), "path", "<unmatched>"),
                    status=message["status"],
                    elapsed_ms=round((time.monotonic() - start) * 1000),
                )
            await send(message)

        async def reject(status, code, message):
            await JSONResponse(
                {"error": {"code": code, "message": message, "details": {}}}, status
            )(scope, receive, with_headers)

        lengths = [v for k, v in scope.get("headers", []) if k.lower() == b"content-length"]
        if len(lengths) > 1 or (lengths and (not lengths[0].isdigit() or len(lengths[0]) > 18)):
            return await reject(400, "invalid_content_length", "Invalid request size.")
        if lengths and int(lengths[0]) > self.max_bytes:
            return await reject(413, "payload_too_large", "Run upload is too large.")
        body = bytearray()
        try:
            # One total deadline: a client cannot extend it by dripping tiny chunks forever.
            async with asyncio.timeout(self.body_timeout_seconds):
                more = True
                while more:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > self.max_bytes:
                        return await reject(413, "payload_too_large", "Run upload is too large.")
                    body.extend(chunk)
                    more = message.get("more_body", False)
        except TimeoutError:
            return await reject(408, "request_timeout", "Upload took too long. Please retry.")
        if lengths and len(body) != int(lengths[0]):
            return await reject(
                400, "invalid_content_length", "Request size did not match its header."
            )
        sent_body = False

        async def replay():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        try:
            await self.app(scope, replay, with_headers)
        except Exception as exc:
            structlog.get_logger().error(
                "unexpected_error",
                path=getattr(scope.get("route"), "path", "<unmatched>"),
                exception_type=type(exc).__name__,
            )
            # Handle before Starlette's outer error middleware rethrows the raw exception
            # to Uvicorn, whose traceback could otherwise expose SQL parameters or GPS data.
            if response_started:
                raise RuntimeError("Response generation failed.") from None
            await reject(500, "internal_error", "Something went wrong. Please retry.")
