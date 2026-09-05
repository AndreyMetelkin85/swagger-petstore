package io.swagger.petstore.controller;

import io.swagger.oas.inflector.models.RequestContext;
import io.swagger.oas.inflector.models.ResponseContext;
import io.swagger.petstore.data.PetData;
import io.swagger.petstore.model.ErrorDetail;
import io.swagger.petstore.model.Pet;
import io.swagger.petstore.model.Role;
import io.swagger.petstore.service.AuthResult;
import io.swagger.petstore.service.AuthService;
import io.swagger.petstore.service.ValidationService;
import io.swagger.petstore.utils.Responses;
import io.swagger.petstore.utils.Util;

import javax.ws.rs.core.Response;
import java.io.File;
import java.util.Arrays;
import java.util.List;

public class PetController {
    private static final PetData PET_DATA = new PetData();
    private static final List<String> STATUSES = Arrays.asList("available", "pending", "sold");
    private final AuthService authService = AuthService.getInstance();

    public ResponseContext findPetsByStatus(final RequestContext request, final String status) {
        if (status == null || status.trim().isEmpty()) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST", "Status is required");
        }
        for (String value : status.split(",")) {
            if (!STATUSES.contains(value)) {
                return Responses.validation(Arrays.asList(
                        new ErrorDetail("status", "Status must be available, pending or sold")));
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

    public ResponseContext getPetById(final RequestContext request, final Long petId) {
        if (petId == null || petId < 1) {
            return Responses.error(Response.Status.BAD_REQUEST, "BAD_REQUEST",
                    "Pet id must be a positive integer");
        }
        final Pet pet = PET_DATA.getPetById(petId);
        if (pet == null) {
            return Responses.error(Response.Status.NOT_FOUND, "PET_NOT_FOUND", "Pet was not found");
        }
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(pet);
    }

    public ResponseContext addPet(final RequestContext request, final Pet pet) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final List<ErrorDetail> errors = ValidationService.validatePet(pet, false);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        if (pet.getId() != null && PET_DATA.getPetById(pet.getId()) != null) {
            return Responses.error(Response.Status.CONFLICT, "PET_ALREADY_EXISTS",
                    "A pet with this id already exists");
        }
        PET_DATA.addPet(pet);
        return new ResponseContext()
                .status(Response.Status.CREATED)
                .contentType(Util.getMediaType(request))
                .entity(pet);
    }

    public ResponseContext updatePet(final RequestContext request, final Pet pet) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        final List<ErrorDetail> errors = ValidationService.validatePet(pet, true);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        if (PET_DATA.getPetById(pet.getId()) == null) {
            return Responses.error(Response.Status.NOT_FOUND, "PET_NOT_FOUND", "Pet was not found");
        }
        PET_DATA.addPet(pet);
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(pet);
    }

    public ResponseContext updatePetWithForm(final RequestContext request, final Long petId,
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
            existing.setStatus(status);
        }
        final List<ErrorDetail> errors = ValidationService.validatePet(existing, true);
        if (!errors.isEmpty()) {
            return Responses.validation(errors);
        }
        PET_DATA.addPet(existing);
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(existing);
    }

    public ResponseContext deletePet(final RequestContext request, final Long petId) {
        final AuthResult auth = authService.authorize(request, Role.ADMIN);
        if (!auth.isAuthorized()) {
            return auth.toResponse();
        }
        if (PET_DATA.getPetById(petId) == null) {
            return Responses.error(Response.Status.NOT_FOUND, "PET_NOT_FOUND", "Pet was not found");
        }
        PET_DATA.deletePetById(petId);
        return new ResponseContext().status(Response.Status.NO_CONTENT);
    }

    public ResponseContext uploadFile(final RequestContext request, final Long petId, final File file) {
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
        PET_DATA.addPet(existing);
        return new ResponseContext()
                .contentType(Util.getMediaType(request))
                .entity(existing);
    }
}
