package io.swagger.petstore.model;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonSetter;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class AdminUserUpdateRequest {
    private String username;
    private String firstName;
    private String lastName;
    private String email;
    private String phone;
    private Role role;
    private Address address;
    private boolean addressPresent;
    private final Map<String, Object> unsupportedFields = new LinkedHashMap<>();

    public String getUsername() {
        return username;
    }

    public void setUsername(final String username) {
        this.username = username;
    }

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(final String firstName) {
        this.firstName = firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public void setLastName(final String lastName) {
        this.lastName = lastName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(final String email) {
        this.email = email;
    }

    public String getPhone() {
        return phone;
    }

    public void setPhone(final String phone) {
        this.phone = phone;
    }

    public Role getRole() {
        return role;
    }

    public void setRole(final Role role) {
        this.role = role;
    }

    public Address getAddress() {
        return address;
    }

    @JsonSetter("address")
    public void setAddress(final Address address) {
        this.address = address;
        this.addressPresent = true;
    }

    @JsonIgnore
    public boolean isAddressPresent() {
        return addressPresent;
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
