package io.swagger.petstore.model;

import javax.xml.bind.annotation.XmlRootElement;

/** Immutable contact and address snapshot captured when an order is placed. */
@XmlRootElement(name = "DeliveryDetails")
public class DeliveryDetails {
    private String firstName;
    private String lastName;
    private String phone;
    private Address address;

    public DeliveryDetails() {
    }

    public DeliveryDetails(final String firstName, final String lastName, final String phone,
                           final Address address) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.phone = phone;
        this.address = address;
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

    public String getPhone() {
        return phone;
    }

    public void setPhone(final String phone) {
        this.phone = phone;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(final Address address) {
        this.address = address;
    }
}
