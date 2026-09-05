package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.data.OrderData;
import io.swagger.petstore.data.PetData;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.Pet;
import io.swagger.petstore.model.PetCreateRequest;
import io.swagger.petstore.model.PetStatus;
import io.swagger.petstore.model.PetUpdateRequest;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.service.AuthResult;
import io.swagger.petstore.service.AuthService;
import io.swagger.petstore.service.PetException;
import io.swagger.petstore.service.ValidationService;
import io.swagger.petstore.utils.Responses;
import io.swagger.petstore.utils.Util;

import javax.ws.rs.core.Response;
import java.io.File;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;

public class PetController {
    private static final PetData PET_DATA = new PetData();
    private static final OrderData ORDER_DATA = new OrderData();
    private static final List<String> STATUSES =
            Arrays.asList("available", "pending", "reserved", "sold");
    private final AuthService authService = AuthService.getInstance();

    public ResponseContext findPetsByStatus(final RequestContext request, final String status) {
        if (status == null || status.trim().isEmpty()) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST", "Status is required");
        }
        for (String value : status.split(",")) {
            if (!STATUSES.contains(value)) {
                return Responses.validation(Arrays.asList(
                        new ErrorDetail("status", "Status must be available, pending, reserved or sold")));
            }
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(PET_DATA.findPetByStatus(status));
    }

    public ResponseContext findPetsByTags(final RequestContext request, final List<String> tags) {
        if (tags == null || tags.isEmpty()) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST", "At least one tag is required");
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(PET_DATA.findPetByTags(tags));
    }

    public ResponseContext getPetById(final RequestContext request, final UUID petId) {
        if (petId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Pet id must be a valid UUID");
        }
        final Pet pet = PET_DATA.getPetById(petId);
        if (pet == null) {
            return Responses.error(Response.Status.NOT_FOUND, "PET_NOT_FOUND", "Pet was not found");
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(pet);
    }

    public ResponseContext addPet(final RequestContext request, final PetCreateRequest pet) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final List<ErrorDetail> errors = ValidationService.validatePetCreate(pet);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        final Pet created = PET_DATA.createPet(pet);
        return new ResponseContext()
                .status(Response.Status.CREATED)
                .contentType(Util.getMediaType(request))
                .entity(created);
    }

    public ResponseContext updatePet(final RequestContext request, final PetUpdateRequest pet) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final List<ErrorDetail> errors = ValidationService.validatePetUpdate(pet);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        try {
            final Pet updated = PET_DATA.updatePet(pet);
            return new ResponseContext()
                    .contentType(Util.getMediaType(request))
                    .entity(updated);
        } catch (PetException exception) {
            return Responses.error(exception.getStatus(), exception.getCode(), exception.getMessage());
        }
    }

    public ResponseContext updatePetWithForm(final RequestContext request, final UUID petId,
                                             final String name, final String status) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final Pet existing = PET_DATA.getPetById(petId);
        if (existing == null) {
            return Responses.error(Response.Status.NOT_FOUND, "PET_NOT_FOUND", "Pet was not found");
        }
        if (name != null) {
            existing.setName(name);
        }
        if (status != null) {
            try {
                existing.setStatus(PetStatus.fromValue(status));
            } catch (IllegalArgumentException exception) {
                return Responses.validation(Arrays.asList(
                        new ErrorDetail("status", "Pet status must be available, pending or sold")));
            }
        }
        final PetUpdateRequest update = toUpdateRequest(existing);
        final List<ErrorDetail> errors = ValidationService.validatePetUpdate(update);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        if (ORDER_DATA.hasActiveOrderForPet(petId) && status != null
                && existing.getStatus() != PetStatus.RESERVED) {
            return Responses.error(Response.Status.CONFLICT, "PET_HAS_ACTIVE_ORDER",
                    "Pet status is managed by its active order");
        }
        PET_DATA.updatePet(existing);
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(existing);
    }

    public ResponseContext deletePet(final RequestContext request, final UUID petId) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (petId == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Pet id must be a valid UUID");
        }
        final PetData.DeleteResult result = PET_DATA.deletePetIfUnused(petId);
        if (result == PetData.DeleteResult.NOT_FOUND) {
            return Responses.error(Response.Status.NOT_FOUND, "PET_NOT_FOUND", "Pet was not found");
        }
        if (result == PetData.DeleteResult.HAS_ORDERS) {
            return Responses.error(Response.Status.CONFLICT, "PET_HAS_ORDERS",
                    "Pet with order history cannot be deleted");
        }
        return new ResponseContext().status(Response.Status.NO_CONTENT);
    }

    public ResponseContext uploadFile(final RequestContext request, final UUID petId, final File file) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final Pet existing = PET_DATA.getPetById(petId);
        if (existing == null) {
            return Responses.error(Response.Status.NOT_FOUND, "PET_NOT_FOUND", "Pet was not found");
        }
        if (file == null) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST", "Image file is required");
        }
        existing.getPhotoUrls().add(file.getName());
        PET_DATA.updatePet(existing);
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(existing);
    }

    private static PetUpdateRequest toUpdateRequest(final Pet pet) {
        final PetUpdateRequest request = new PetUpdateRequest();
        request.setId(pet.getId());
        request.setCategory(pet.getCategory());
        request.setName(pet.getName());
        request.setPhotoUrls(pet.getPhotoUrls());
        request.setTags(pet.getTags());
        request.setStatus(pet.getStatus().getValue());
        return request;
    }

}
