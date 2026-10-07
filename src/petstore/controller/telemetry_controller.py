"""Bounded, allowlisted operational telemetry; no request payload logging."""

import logging
import time
from threading import Lock

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.model.commerce import TelemetryCommand
from petstore.service.exceptions import ApiException

logger = logging.getLogger("petstore.telemetry")


class TelemetryController:
    """Own rate-limit state for one application instance, not global module state."""

    def __init__(self) -> None:
        """Initialize a thread-safe 100-batch-per-minute window."""
        self.lock = Lock()
        self.window = 0.0
        self.count = 0

    def client_events(self, context: RequestContext) -> Response:
        """Accept only known event names and safe numeric/enumerated metadata."""
        command = context.body
        assert isinstance(command, TelemetryCommand)
        allowed = {
            "api_result",
            "api_failure",
            "client_error",
            "cart_merge",
            "checkout",
            "media_upload",
            "navigation",
        }
        if any(event.event not in allowed for event in command.events):
            raise ApiException(422, "VALIDATION_ERROR", "Unknown telemetry event")
        with self.lock:
            now = time.monotonic()
            if now - self.window >= 60:
                self.window, self.count = now, 0
            if self.count >= 100:
                raise ApiException(429, "TELEMETRY_RATE_LIMITED", "Too many telemetry batches")
            self.count += 1
        logger.info("client_events count=%s", len(command.events))
        for event in command.events:
            logger.info(
                "client_event event=%s method=%s httpStatus=%s durationMs=%s",
                event.event,
                event.method,
                event.http_status,
                event.duration_ms,
            )
        return Response(status_code=204)
