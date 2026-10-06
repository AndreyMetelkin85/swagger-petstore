"""Controllers preserve operation IDs, roles, response codes and service boundaries."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.data.pet_data import PetData
from petstore.model.requests import (
    PetCreateRequest,
    PetUpdateRequest,
)
from petstore.service.exceptions import ApiException
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses


class PetController:
    """Public catalog reads and administrator-managed pet writes."""

    def __init__(self, database: Database) -> None:
        """Configure the pet repository.

        :param database: Application pool.
        """
        self.data = PetData(database)

    def findPetsByStatus(self, context: RequestContext) -> Response:
        """Search the original comma-separated status filter.

        :param context: Public search request.
        """
        status = context.parameters["status"]
        if not status or not status.strip():
            raise ApiException(400, "BAD_REQUEST", "Status is required")
        if any(value not in {"available", "pending", "reserved", "sold"} for value in status.split(",")):
            V.ensure([{"field": "status", "message": "Status must be available, pending, reserved or sold"}])
        return Responses(self.data.find_pet_by_status(status))

    def findPetsByTags(self, context: RequestContext) -> Response:
        """Search pets by their tag names.

        :param context: Public tag query.
        """
        tags = context.parameters["tags"]
        if not tags:
            raise ApiException(400, "BAD_REQUEST", "At least one tag is required")
        return Responses(self.data.find_pet_by_tags(tags))

    def getPetById(self, context: RequestContext) -> Response:
        """Read one public pet by UUID.

        :param context: Catalog path parameter.
        """
        return Responses(self.data.get_pet_by_id(context.identifier("petId")))

    def addPet(self, context: RequestContext) -> Response:
        """Create a pet only as an administrator.

        :param context: Authorized creation request.
        """
        context.authorize("ADMIN")
        return Responses(self.data.create_pet(context.validated(PetCreateRequest, V.pet)), status_code=201)

    def updatePet(self, context: RequestContext) -> Response:
        """Update a pet only with the current optimistic version.

        :param context: Authorized full update.
        """
        context.authorize("ADMIN")
        return Responses(
            self.data.update_pet(context.identifier("petId"), context.validated(PetUpdateRequest, V.pet))
        )

    def deletePet(self, context: RequestContext) -> Response:
        """Delete an unused pet as an administrator.

        :param context: Authorized deletion request.
        """
        context.authorize("ADMIN")
        self.data.delete_pet_if_unused(context.identifier("petId"))
        return Response(status_code=204)
