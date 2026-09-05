package io.swagger.petstore.data;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.petstore.model.Category;
import io.swagger.petstore.model.Pet;
import io.swagger.petstore.model.Tag;

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

/** PostgreSQL-backed pet repository. Nested Pet fields are stored as JSON text. */
public class PetData {
    private static final String COLUMNS =
            "id, category_json, name, photo_urls_json, tags_json, status";
    private static final ObjectMapper JSON = new ObjectMapper();

    public Pet getPetById(final long petId) {
        final String sql = "SELECT " + COLUMNS + " FROM pets WHERE id = ?";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, petId);
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
            if (statuses.contains(pet.getStatus())) {
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

    public void addPet(final Pet pet) {
        final boolean suppliedId = pet.getId() != null && pet.getId() > 0;
        final String sql = suppliedId
                ? "INSERT INTO pets (id, category_json, name, photo_urls_json, tags_json, status) "
                + "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET "
                + "category_json = EXCLUDED.category_json, name = EXCLUDED.name, "
                + "photo_urls_json = EXCLUDED.photo_urls_json, tags_json = EXCLUDED.tags_json, "
                + "status = EXCLUDED.status RETURNING id"
                : "INSERT INTO pets (category_json, name, photo_urls_json, tags_json, status) "
                + "VALUES (?, ?, ?, ?, ?) RETURNING id";
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            int index = 1;
            if (suppliedId) {
                statement.setLong(index++, pet.getId());
            }
            statement.setString(index++, toJson(pet.getCategory()));
            statement.setString(index++, pet.getName());
            statement.setString(index++, toJson(pet.getPhotoUrls()));
            statement.setString(index++, toJson(pet.getTags()));
            statement.setString(index, pet.getStatus());
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                pet.setId(result.getLong(1));
            }
        } catch (SQLException exception) {
            throw Database.failure("upsert pet", exception);
        }
    }

    public void deletePetById(final Long petId) {
        if (petId == null) {
            return;
        }
        try (Connection connection = Database.connect();
             PreparedStatement statement = connection.prepareStatement("DELETE FROM pets WHERE id = ?")) {
            statement.setLong(1, petId);
            statement.executeUpdate();
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
            return createPet(result.getLong("id"),
                    JSON.readValue(result.getString("category_json"), Category.class),
                    result.getString("name"),
                    JSON.readValue(result.getString("photo_urls_json"),
                            new TypeReference<List<String>>() { }),
                    JSON.readValue(result.getString("tags_json"),
                            new TypeReference<List<Tag>>() { }),
                    result.getString("status"));
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

    public static Pet createPet(final Long id, final Category category, final String name,
                                final List<String> urls, final List<Tag> tags, final String status) {
        final Pet pet = new Pet();
        pet.setId(id);
        pet.setCategory(category);
        pet.setName(name);
        pet.setPhotoUrls(urls);
        pet.setTags(tags);
        pet.setStatus(status);
        return pet;
    }
}
