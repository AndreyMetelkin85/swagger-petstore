"""Image upload, visibility and deletion HTTP handlers."""

from starlette.responses import Response

from petstore.config import Settings
from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.service.media_service import MediaService
from petstore.utils.responses import Responses


class MediaController:
    """Delegate bounded uploads and owner/public image access to the media service."""

    def __init__(self, database: Database, settings: Settings) -> None:
        """Inject the pool and persistent image directory."""
        self.media = MediaService(database, settings)

    def upload(self, context: RequestContext) -> Response:
        """Persist a verified ADMIN upload; no client filename becomes a storage path."""
        actor = context.authorize("ADMIN")
        assert context.upload is not None
        return Responses(self.media.upload(*context.upload, actor), status_code=201)

    def get(self, context: RequestContext, thumbnail: bool | None = None) -> Response:
        """Return metadata or image bytes only when their visibility permits access."""
        actor = context.authorize("USER", "ADMIN") if context.request.headers.get("Authorization") else None
        result = self.media.get(context.identifier("id"), actor, thumbnail)
        if isinstance(result, tuple):
            return Response(
                result[0],
                media_type=result[1],
                headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"},
            )
        return Responses(result)

    def delete(self, context: RequestContext) -> Response:
        """Delete an unused image as ADMIN, retaining protected order snapshots."""
        context.authorize("ADMIN")
        self.media.delete(context.identifier("id"))
        return Response(status_code=204)
