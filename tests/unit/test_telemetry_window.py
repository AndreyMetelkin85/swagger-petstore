from unittest.mock import Mock

import pytest

from petstore.controller.context import RequestContext
from petstore.controller.telemetry_controller import TelemetryController
from petstore.model.commerce import TelemetryCommand, TelemetryEvent
from petstore.service.exceptions import ApiException


def test_rate_window_resets_at_60_seconds_without_real_waiting():
    now = 100.0
    controller = TelemetryController(clock=lambda: now)
    context = RequestContext(Mock(), Mock(), {}, TelemetryCommand(events=[TelemetryEvent(event="checkout")]))
    for _ in range(100):
        assert controller.client_events(context).status_code == 204
    now = 159.999
    with pytest.raises(ApiException) as error:
        controller.client_events(context)
    assert error.value.status == 429
    assert error.value.code == "TELEMETRY_RATE_LIMITED"
    now = 160.0
    assert controller.client_events(context).status_code == 204
    assert controller.count == 1
