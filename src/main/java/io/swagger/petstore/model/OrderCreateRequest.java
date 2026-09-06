package io.swagger.petstore.model;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonIgnore;

import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

@XmlRootElement(name = "OrderCreateRequest")
public class OrderCreateRequest {
    private UUID petId;
    private Integer quantity;
    private final Map<String, Object> unsupportedFields = new LinkedHashMap<>();

    @XmlElement(name = "petId")
    public UUID getPetId() {
        return petId;
    }

    public void setPetId(final UUID petId) {
        this.petId = petId;
    }

    @XmlElement(name = "quantity")
    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(final Integer quantity) {
        this.quantity = quantity;
    }

    @JsonAnySetter
    public void addUnsupportedField(final String name, final Object value) {
        unsupportedFields.put(name, value);
    }

    @JsonIgnore
    public Map<String, Object> getUnsupportedFields() {
        return unsupportedFields;
    }
}
