package io.swagger.petstore.model;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonIgnore;

import javax.xml.bind.annotation.XmlRootElement;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** A single Russian delivery address associated with a user. */
@XmlRootElement(name = "Address")
public class Address {
    private String city;
    private String street;
    private String house;
    private String apartment;
    private String postalCode;
    private final Map<String, Object> unsupportedFields = new LinkedHashMap<>();

    public String getCity() {
        return city;
    }

    public void setCity(final String city) {
        this.city = city;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(final String street) {
        this.street = street;
    }

    public String getHouse() {
        return house;
    }

    public void setHouse(final String house) {
        this.house = house;
    }

    public String getApartment() {
        return apartment;
    }

    public void setApartment(final String apartment) {
        this.apartment = apartment;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(final String postalCode) {
        this.postalCode = postalCode;
    }

    @JsonAnySetter
    public void captureUnsupportedField(final String name, final Object value) {
        unsupportedFields.put(name, value);
    }

    @JsonIgnore
    public Map<String, Object> getUnsupportedFields() {
        return Collections.unmodifiableMap(unsupportedFields);
    }
}
