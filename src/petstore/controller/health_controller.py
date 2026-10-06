"""Controllers preserve operation IDs, roles, response codes and service boundaries."""

from datetime import UTC, datetime

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.utils.responses import Responses


class HealthController:
    """Public API and database readiness."""

    def __init__(self, database: Database) -> None:
        """Use the existing PostgreSQL health probe.

        :param database: Application pool.
        """
        self.database = database

    def health(self, context: RequestContext) -> Response:
        """Report service readiness using the original response fields.

        :param context: Incoming request context.
        """
        healthy = self.database.is_healthy()
        state = "UP" if healthy else "DOWN"
        return Responses(
            {
                "status": state,
                "service": "swagger-petstore",
                "database": state,
                "timestamp": datetime.now(UTC),
            },
            status_code=200 if healthy else 503,
        )
