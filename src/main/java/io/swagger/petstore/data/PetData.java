package io.swagger.petstore.data;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.petstore.model.Category;
import io.swagger.petstore.model.Pet;
import io.swagger.petstore.model.PetCreateRequest;
import io.swagger.petstore.model.PetStatus;
import io.swagger.petstore.model.PetUpdateRequest;
import io.swagger.petstore.model.Tag;
import io.swagger.petstore.service.PetException;

import javax.ws.rs.core.Response;

import java.io.IOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/** PostgreSQL-backed pet repository. Nested Pet fields are stored as JSON text. */
public class PetData {
    private static final String COLUMNS =
            "id, category_json, name, photo_urls_json, tags_json, status, version";
    private static final ObjectMapper JSON = new ObjectMapper();

    public Pet getPetById(final UUID petId) {
        final String sql = "SELECT " + COLUMNS + " FROM pets WHERE id = ?";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, petId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next() ? map(result) : null;
            }
        } catch (SQLException exception) {
            throw Database.failure("find pet", exception);
        }
    }

    public List<Pet> findPetByStatus(final String status) {
        final Set<String> statuses = new HashSet<>(Arrays.asList(status.split(",")));
        final List<Pet> result = new ArrayList<>();
        for (Pet pet : findAll()) {
            if (statuses.contains(pet.getStatus().getValue())) {
                result.add(pet);
            }
        }
        return result;
    }

    public List<Pet> findPetByTags(final List<String> tags) {
        final Set<String> expected = new HashSet<>(tags);
        final List<Pet> result = new ArrayList<>();
        for (Pet pet : findAll()) {
            if (pet.getTags() == null) {
                continue;
            }
            for (Tag tag : pet.getTags()) {
                if (expected.contains(tag.getName())) {
                    result.add(pet);
                    break;
                }
            }
        }
        return result;
    }

    public Pet createPet(final PetCreateRequest request) {
        final Pet pet = fromRequest(request, null);
        assignNestedIds(pet);
        final String sql = "INSERT INTO pets "
                + "(category_json, name, photo_urls_json, tags_json, status) "
                + "VALUES (?, ?, ?, ?, CAST(? AS pet_status)) RETURNING id, version";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, toJson(pet.getCategory()));
            statement.setString(2, pet.getName());
            statement.setString(3, toJson(pet.getPhotoUrls()));
            statement.setString(4, toJson(pet.getTags()));
            statement.setString(5, pet.getStatus().getValue());
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                pet.setId((UUID) result.getObject("id"));
                pet.setVersion(result.getInt("version"));
            }
            return pet;
        } catch (SQLException exception) {
            throw Database.failure("create pet", exception);
        }
    }

    public Pet updatePet(final UUID petId, final PetUpdateRequest request) {
        try (Connection connection = Database.connect()) {
            connection.setAutoCommit(false);
            try {
                final LockedPet persisted = lockPet(connection, petId);
                if (persisted == null) {
                    throw new PetException(Response.Status.NOT_FOUND, "PET_NOT_FOUND",
                            "Pet was not found");
                }
                if (!request.getVersion().equals(persisted.version)) {
                    throw new PetException(Response.Status.CONFLICT, "PET_VERSION_CONFLICT",
                            "Pet was changed by another request; reload it and retry");
                }
                if (request.getStatus() != null && hasActiveOrder(connection, petId)) {
                    throw new PetException(Response.Status.CONFLICT, "PET_HAS_ACTIVE_ORDER",
                            "Pet status is managed by its active order");
                }
                final Pet pet = fromRequest(request, petId);
                if (request.getStatus() == null) {
                    pet.setStatus(persisted.status);
                }
                assignNestedIds(pet);
                pet.setVersion(updatePet(connection, pet, persisted.version));
                connection.commit();
                return pet;
            } catch (SQLException | RuntimeException exception) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    exception.addSuppressed(rollbackFailure);
                }
                throw exception;
            }
        } catch (SQLException exception) {
            throw Database.failure("update pet", exception);
        }
    }

    public DeleteResult deletePetIfUnused(final UUID petId) {
        if (petId == null) {
            return DeleteResult.NOT_FOUND;
        }
        try (Connection connection = Database.connect()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement lock = connection.prepareStatement(
                        "SELECT 1 FROM pets WHERE id = ? FOR UPDATE")) {
                    lock.setObject(1, petId);
                    try (ResultSet result = lock.executeQuery()) {
                        if (!result.next()) {
                            connection.rollback();
                            return DeleteResult.NOT_FOUND;
                        }
                    }
                }
                try (PreparedStatement orders = connection.prepareStatement(
                        "SELECT 1 FROM store_orders WHERE pet_id = ? LIMIT 1")) {
                    orders.setObject(1, petId);
                    try (ResultSet result = orders.executeQuery()) {
                        if (result.next()) {
                            connection.rollback();
                            return DeleteResult.HAS_ORDERS;
                        }
                    }
                }
                try (PreparedStatement delete = connection.prepareStatement(
                        "DELETE FROM pets WHERE id = ?")) {
                    delete.setObject(1, petId);
                    delete.executeUpdate();
                }
                connection.commit();
                return DeleteResult.DELETED;
            } catch (SQLException | RuntimeException exception) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    exception.addSuppressed(rollbackFailure);
                }
                throw exception;
            }
        } catch (SQLException exception) {
            throw Database.failure("delete pet", exception);
        }
    }

    private List<Pet> findAll() {
        final List<Pet> pets = new ArrayList<>();
        try (Connection connection = Database.connect();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(
                     "SELECT " + COLUMNS + " FROM pets ORDER BY id")) {
            while (result.next()) {
                pets.add(map(result));
            }
            return pets;
        } catch (SQLException exception) {
            throw Database.failure("list pets", exception);
        }
    }

    private static Pet map(final ResultSet result) throws SQLException {
        try {
            return createPet((UUID) result.getObject("id"),
                    JSON.readValue(result.getString("category_json"), Category.class),
                    result.getString("name"),
                    JSON.readValue(result.getString("photo_urls_json"),
                            new TypeReference<List<String>>() { }),
                    JSON.readValue(result.getString("tags_json"),
                            new TypeReference<List<Tag>>() { }),
                    PetStatus.fromValue(result.getString("status")), result.getInt("version"));
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot deserialize pet JSON fields", exception);
        }
    }

    private static String toJson(final Object value) {
        try {
            return JSON.writeValueAsString(value);
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot serialize pet JSON fields", exception);
        }
    }

    public static Pet createPet(final UUID id, final Category category, final String name,
                                final List<String> urls, final List<Tag> tags, final PetStatus status,
                                final int version) {
        final Pet pet = new Pet();
        pet.setId(id);
        pet.setCategory(category);
        pet.setName(name);
        pet.setPhotoUrls(urls);
        pet.setTags(tags);
        pet.setStatus(status);
        pet.setVersion(version);
        return pet;
    }

    private static Pet fromRequest(final PetCreateRequest request, final UUID id) {
        return createPet(id, request.getCategory(), request.getName(),
                request.getPhotoUrls() == null ? new ArrayList<String>() : request.getPhotoUrls(),
                request.getTags() == null ? new ArrayList<Tag>() : request.getTags(),
                request.getStatus() == null
                        ? PetStatus.AVAILABLE : PetStatus.fromValue(request.getStatus()), 0);
    }

    private static LockedPet lockPet(final Connection connection, final UUID petId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT status, version FROM pets WHERE id = ? FOR UPDATE")) {
            statement.setObject(1, petId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next()
                        ? new LockedPet(PetStatus.fromValue(result.getString("status")),
                                result.getInt("version"))
                        : null;
            }
        }
    }

    private static boolean hasActiveOrder(final Connection connection, final UUID petId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT 1 FROM store_orders WHERE pet_id = ? "
                        + "AND status IN ('placed', 'approved', 'shipped') LIMIT 1")) {
            statement.setObject(1, petId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next();
            }
        }
    }

    private static int updatePet(final Connection connection, final Pet pet, final int expectedVersion)
            throws SQLException {
        final String sql = "UPDATE pets SET category_json = ?, name = ?, photo_urls_json = ?, "
                + "tags_json = ?, status = CAST(? AS pet_status), version = version + 1 "
                + "WHERE id = ? AND version = ? RETURNING version";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, toJson(pet.getCategory()));
            statement.setString(2, pet.getName());
            statement.setString(3, toJson(pet.getPhotoUrls()));
            statement.setString(4, toJson(pet.getTags()));
            statement.setString(5, pet.getStatus().getValue());
            statement.setObject(6, pet.getId());
            statement.setInt(7, expectedVersion);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new PetException(Response.Status.CONFLICT, "PET_VERSION_CONFLICT",
                            "Pet was changed by another request; reload it and retry");
                }
                return result.getInt(1);
            }
        }
    }

    private static final class LockedPet {
        private final PetStatus status;
        private final int version;

        private LockedPet(final PetStatus status, final int version) {
            this.status = status;
            this.version = version;
        }
    }

    private static void assignNestedIds(final Pet pet) {
        if (pet.getCategory() != null && pet.getCategory().getId() == null) {
            pet.getCategory().setId(UUID.randomUUID());
        }
        if (pet.getTags() != null) {
            for (Tag tag : pet.getTags()) {
                if (tag != null && tag.getId() == null) {
                    tag.setId(UUID.randomUUID());
                }
            }
        }
    }

    public enum DeleteResult {
        DELETED,
        NOT_FOUND,
        HAS_ORDERS
    }
}
